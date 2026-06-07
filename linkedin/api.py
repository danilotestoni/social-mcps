from __future__ import annotations

import urllib.parse
from pathlib import Path

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from auth import TokenManager
from logger import get_logger
from models import ProfileInfo, UGCPostElement

_BASE_URL = "https://api.linkedin.com"
_API_VERSION = "202401"


def _retried(func):
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        reraise=True,
    )(func)


class LinkedInAPIError(Exception):
    pass


class LinkedInClient:
    def __init__(self, token_manager: TokenManager) -> None:
        self._tm = token_manager
        self._logger = get_logger(__name__)

    async def _headers(self) -> dict[str, str]:
        token = await self._tm.get_valid_token()
        return {
            "Authorization": f"Bearer {token}",
            "LinkedIn-Version": _API_VERSION,
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code >= 400:
            self._logger.error(
                "LinkedIn API error %s: %s", response.status_code, response.text
            )
            response.raise_for_status()

    @_retried
    async def get_profile(self) -> ProfileInfo:
        # OpenID Connect userinfo endpoint — works with the 'profile' scope
        headers = await self._headers()
        async with httpx.AsyncClient(base_url=_BASE_URL) as client:
            response = await client.get("/v2/userinfo", headers=headers)
        self._raise_for_status(response)
        data = response.json()
        # 'sub' is the full person URN: urn:li:person:xxxx
        person_urn = data["sub"]
        person_id = person_urn.split(":")[-1]
        return ProfileInfo(
            id=person_id,
            first_name=data.get("given_name", ""),
            last_name=data.get("family_name", ""),
            person_urn=person_urn,
        )

    @_retried
    async def get_posts(
        self, person_urn: str, count: int = 10
    ) -> list[UGCPostElement]:
        headers = await self._headers()
        async with httpx.AsyncClient(base_url=_BASE_URL) as client:
            response = await client.get(
                "/v2/ugcPosts",
                params={
                    "q": "authors",
                    "authors": f"List({person_urn})",
                    "count": count,
                },
                headers=headers,
            )
        self._raise_for_status(response)
        elements = response.json().get("elements", [])
        posts = []
        for el in elements:
            text = (
                el.get("specificContent", {})
                .get("com.linkedin.ugc.ShareContent", {})
                .get("shareCommentary", {})
                .get("text", "")
            )
            posts.append(
                UGCPostElement(
                    urn=el["id"],
                    text=text,
                    created_at=el.get("created", {}).get("time", 0),
                )
            )
        return posts

    @_retried
    async def delete_post(self, post_urn: str) -> None:
        headers = await self._headers()
        encoded_urn = urllib.parse.quote(post_urn, safe="")
        async with httpx.AsyncClient(base_url=_BASE_URL) as client:
            response = await client.delete(
                f"/v2/ugcPosts/{encoded_urn}", headers=headers
            )
        self._raise_for_status(response)

    @_retried
    async def register_image_upload(self, person_urn: str) -> tuple[str, str]:
        headers = await self._headers()
        body = {
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner": person_urn,
                "serviceRelationships": [
                    {
                        "relationshipType": "OWNER",
                        "identifier": "urn:li:userGeneratedContent",
                    }
                ],
            }
        }
        async with httpx.AsyncClient(base_url=_BASE_URL) as client:
            response = await client.post(
                "/v2/assets",
                params={"action": "registerUpload"},
                json=body,
                headers=headers,
            )
        self._raise_for_status(response)
        value = response.json()["value"]
        upload_url = value["uploadMechanism"][
            "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"
        ]["uploadUrl"]
        asset_urn = value["asset"]
        return upload_url, asset_urn

    async def upload_image_binary(self, upload_url: str, image_bytes: bytes) -> None:
        # LinkedIn presigned upload URLs carry their own credentials — no Authorization header.
        async with httpx.AsyncClient() as client:
            response = await client.put(
                upload_url,
                content=image_bytes,
                headers={"Content-Type": "application/octet-stream"},
                timeout=60.0,
            )
        self._raise_for_status(response)

    @_retried
    async def create_post(
        self,
        person_urn: str,
        text: str,
        asset_urn: str | None = None,
    ) -> str:
        headers = await self._headers()
        share_content: dict = {
            "shareCommentary": {"text": text},
            "shareMediaCategory": "IMAGE" if asset_urn else "NONE",
        }
        if asset_urn:
            share_content["media"] = [
                {
                    "status": "READY",
                    "media": asset_urn,
                }
            ]
        body = {
            "author": person_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {"com.linkedin.ugc.ShareContent": share_content},
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            },
        }
        async with httpx.AsyncClient(base_url=_BASE_URL) as client:
            response = await client.post("/v2/ugcPosts", json=body, headers=headers)
        self._raise_for_status(response)
        return response.headers.get("x-restli-id", "")

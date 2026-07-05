from __future__ import annotations

import urllib.parse

import httpx

from auth.linkedin_auth import LinkedInTokenManager
from core.logger import get_logger
from core.models import ProfileInfo, UGCPostElement
from core.retry import _retried, _retried_publish

_BASE_URL = "https://api.linkedin.com"
_API_VERSION = "202401"


class LinkedInAPIError(Exception):
    pass


class LinkedInClient:
    def __init__(self, token_manager: LinkedInTokenManager) -> None:
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
        headers = await self._headers()
        async with httpx.AsyncClient(base_url=_BASE_URL) as client:
            response = await client.get("/v2/userinfo", headers=headers)
        self._raise_for_status(response)
        data = response.json()
        person_id = data["sub"]
        if person_id.startswith("urn:li:person:"):
            person_urn = person_id
            person_id = person_id.split(":")[-1]
        else:
            person_urn = f"urn:li:person:{person_id}"
        return ProfileInfo(
            id=person_id,
            first_name=data.get("given_name", ""),
            last_name=data.get("family_name", ""),
            person_urn=person_urn,
        )

    @_retried
    async def get_posts(self, person_urn: str, count: int = 10) -> list[UGCPostElement]:
        headers = await self._headers()
        # Rest.li 2.0 requires literal parentheses in List(...) — passing this
        # via httpx params would percent-encode them and LinkedIn returns 400.
        # The URN itself must be encoded, the parentheses must not.
        encoded_urn = urllib.parse.quote(person_urn, safe="")
        url = f"/v2/ugcPosts?q=authors&authors=List({encoded_urn})&count={count}"
        async with httpx.AsyncClient(base_url=_BASE_URL) as client:
            response = await client.get(url, headers=headers)
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

    @_retried_publish
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
            share_content["media"] = [{"status": "READY", "media": asset_urn}]
        body = {
            "author": person_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {"com.linkedin.ugc.ShareContent": share_content},
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        async with httpx.AsyncClient(base_url=_BASE_URL) as client:
            response = await client.post("/v2/ugcPosts", json=body, headers=headers)
        self._raise_for_status(response)
        return response.headers.get("x-restli-id", "")

from __future__ import annotations

import mimetypes
from pathlib import Path

import httpx

from auth.facebook_auth import FacebookTokenManager
from core.logger import get_logger
from core.models import FacebookPostItem, PageInfo
from core.retry import _retried, _retried_publish

_BASE_URL = "https://graph.facebook.com/v21.0"


class FacebookClient:
    def __init__(self, token_manager: FacebookTokenManager, page_id: str) -> None:
        self._tm = token_manager
        self._page_id = page_id
        self._logger = get_logger(__name__)

    async def _token(self) -> str:
        return await self._tm.get_valid_token()

    async def _auth_headers(self) -> dict[str, str]:
        # Token goes in the Authorization header (officially supported by the
        # Graph API) instead of the query string, so it never appears in URLs,
        # error messages, or logs.
        return {"Authorization": f"Bearer {await self._token()}"}

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code >= 400:
            self._logger.error(
                "Facebook API error %s: %s", response.status_code, response.text
            )
            response.raise_for_status()

    @_retried
    async def get_page_info(self) -> PageInfo:
        headers = await self._auth_headers()
        async with httpx.AsyncClient(base_url=_BASE_URL) as client:
            response = await client.get(
                f"/{self._page_id}",
                params={"fields": "id,name,category,fan_count,followers_count"},
                headers=headers,
            )
        self._raise_for_status(response)
        data = response.json()
        return PageInfo(
            id=data["id"],
            name=data["name"],
            category=data.get("category", ""),
            fan_count=data.get("fan_count", 0),
            followers_count=data.get("followers_count", 0),
        )

    @_retried
    async def get_posts(self, count: int = 10) -> list[FacebookPostItem]:
        headers = await self._auth_headers()
        async with httpx.AsyncClient(base_url=_BASE_URL) as client:
            response = await client.get(
                f"/{self._page_id}/posts",
                params={
                    "fields": "id,message,created_time,full_picture,permalink_url",
                    "limit": count,
                },
                headers=headers,
            )
        self._raise_for_status(response)
        posts = []
        for el in response.json().get("data", []):
            posts.append(
                FacebookPostItem(
                    id=el["id"],
                    message=el.get("message", ""),
                    created_time=el.get("created_time", ""),
                    full_picture=el.get("full_picture"),
                    permalink_url=el.get("permalink_url"),
                )
            )
        return posts

    @_retried
    async def delete_post(self, post_id: str) -> None:
        headers = await self._auth_headers()
        async with httpx.AsyncClient(base_url=_BASE_URL) as client:
            response = await client.delete(f"/{post_id}", headers=headers)
        self._raise_for_status(response)

    @_retried_publish
    async def publish_text_post(self, message: str) -> str:
        headers = await self._auth_headers()
        async with httpx.AsyncClient(base_url=_BASE_URL) as client:
            response = await client.post(
                f"/{self._page_id}/feed",
                json={"message": message},
                headers=headers,
            )
        self._raise_for_status(response)
        return response.json()["id"]

    @_retried_publish
    async def publish_photo_url(self, image_url: str, caption: str) -> str:
        headers = await self._auth_headers()
        async with httpx.AsyncClient(base_url=_BASE_URL) as client:
            response = await client.post(
                f"/{self._page_id}/photos",
                json={"url": image_url, "caption": caption},
                headers=headers,
            )
        self._raise_for_status(response)
        data = response.json()
        return data.get("post_id") or data["id"]

    @_retried_publish
    async def publish_photo_file(self, image_path: str, caption: str) -> str:
        headers = await self._auth_headers()
        image_bytes = Path(image_path).read_bytes()
        filename = Path(image_path).name
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        async with httpx.AsyncClient(base_url=_BASE_URL) as client:
            response = await client.post(
                f"/{self._page_id}/photos",
                data={"caption": caption},
                files={"source": (filename, image_bytes, content_type)},
                headers=headers,
            )
        self._raise_for_status(response)
        data = response.json()
        return data.get("post_id") or data["id"]

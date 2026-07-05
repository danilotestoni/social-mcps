from __future__ import annotations

import mimetypes
from pathlib import Path

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from auth import TokenManager
from logger import get_logger
from models import PageInfo, PostItem

_BASE_URL = "https://graph.facebook.com/v21.0"


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError))


def _is_connection_only(exc: BaseException) -> bool:
    return isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout))


def _retried(func):
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        retry=retry_if_exception(_is_transient),
        reraise=True,
    )(func)


def _retried_publish(func):
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        retry=retry_if_exception(_is_connection_only),
        reraise=True,
    )(func)


class FacebookClient:
    def __init__(self, token_manager: TokenManager, page_id: str) -> None:
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
    async def get_posts(self, count: int = 10) -> list[PostItem]:
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
                PostItem(
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

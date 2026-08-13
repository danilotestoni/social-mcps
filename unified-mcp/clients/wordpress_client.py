from __future__ import annotations

import mimetypes
from pathlib import Path

import httpx

from auth.wordpress_auth import WordPressTokenManager
from core.logger import get_logger
from core.models import SiteInfo, WPPostItem
from core.retry import _retried, _retried_publish

_BASE_URL = "https://public-api.wordpress.com/rest/v1.1"
# httpx's default timeout (5s) is too short for media uploads/URL fetches.
_TIMEOUT = httpx.Timeout(60.0)


class WordPressClient:
    def __init__(self, token_manager: WordPressTokenManager, site_id: str) -> None:
        self._tm = token_manager
        self._site_id = site_id
        self._logger = get_logger(__name__)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._tm.get_token()}"}

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code >= 400:
            self._logger.error(
                "WordPress API error %s: %s", response.status_code, response.text
            )
            response.raise_for_status()

    @_retried
    async def get_site_info(self) -> SiteInfo:
        async with httpx.AsyncClient(base_url=_BASE_URL, timeout=_TIMEOUT) as client:
            response = await client.get(
                f"/sites/{self._site_id}",
                headers=self._headers(),
            )
        self._raise_for_status(response)
        data = response.json()
        return SiteInfo(
            id=data["ID"],
            name=data["name"],
            url=data["URL"],
            description=data.get("description", ""),
            post_count=data.get("post_count", 0),
        )

    @_retried
    async def get_posts(self, count: int = 10) -> list[WPPostItem]:
        async with httpx.AsyncClient(base_url=_BASE_URL, timeout=_TIMEOUT) as client:
            response = await client.get(
                f"/sites/{self._site_id}/posts/",
                headers=self._headers(),
                params={
                    "number": count,
                    "fields": "ID,title,URL,short_URL,status,date",
                },
            )
        self._raise_for_status(response)
        posts = []
        for el in response.json().get("posts", []):
            posts.append(
                WPPostItem(
                    id=el["ID"],
                    title=el.get("title", ""),
                    url=el.get("URL", ""),
                    short_url=el.get("short_URL", ""),
                    status=el.get("status", ""),
                    date=el.get("date", ""),
                )
            )
        return posts

    @_retried
    async def delete_post(self, post_id: int) -> None:
        # WordPress.com REST API uses POST /{post_id}/delete, not HTTP DELETE
        async with httpx.AsyncClient(base_url=_BASE_URL, timeout=_TIMEOUT) as client:
            response = await client.post(
                f"/sites/{self._site_id}/posts/{post_id}/delete",
                headers=self._headers(),
            )
        self._raise_for_status(response)

    async def _upload_media_bytes(
        self, data: bytes, filename: str, content_type: str | None = None
    ) -> int:
        content_type = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        async with httpx.AsyncClient(base_url=_BASE_URL, timeout=_TIMEOUT) as client:
            response = await client.post(
                f"/sites/{self._site_id}/media/new",
                headers=self._headers(),
                files={"media[]": (filename, data, content_type)},
            )
        self._raise_for_status(response)
        media_items = response.json().get("media", [])
        if not media_items:
            raise ValueError("Media upload succeeded but returned no media items.")
        return media_items[0]["ID"]

    async def upload_media_from_path(self, image_path: str) -> int:
        image_bytes = Path(image_path).read_bytes()
        filename = Path(image_path).name
        return await self._upload_media_bytes(image_bytes, filename)

    async def upload_media_get_url(self, data: bytes, filename: str) -> dict:
        """Upload media bytes and return {'id': int, 'url': str} with the public URL."""
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        async with httpx.AsyncClient(base_url=_BASE_URL, timeout=_TIMEOUT) as client:
            response = await client.post(
                f"/sites/{self._site_id}/media/new",
                headers=self._headers(),
                files={"media[]": (filename, data, content_type)},
            )
        self._raise_for_status(response)
        media_items = response.json().get("media", [])
        if not media_items:
            raise ValueError("Media upload succeeded but returned no media items.")
        return {"id": media_items[0]["ID"], "url": media_items[0].get("URL", "")}

    async def upload_media_from_url(self, image_url: str) -> int:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(image_url, timeout=30.0)
            response.raise_for_status()
            image_bytes = response.content
        response_content_type = response.headers.get("content-type", "").split(";")[0].strip()
        url_name = image_url.split("/")[-1].split("?")[0]
        url_content_type = mimetypes.guess_type(url_name)[0] if url_name else None

        # Prefer a specific image/* Content-Type reported by the server —
        # the only reliable signal for opaque URLs (notably our own
        # /temp-image/<token> proxy, whose last path segment is a signed
        # token, not a real filename). But plenty of ordinary image hosts
        # send a generic "application/octet-stream" regardless of the
        # actual file, so don't let that override a perfectly good
        # extension already present in the URL.
        if response_content_type.startswith("image/"):
            content_type = response_content_type
        else:
            content_type = url_content_type or response_content_type or None

        if url_content_type:
            filename = url_name
        else:
            ext = mimetypes.guess_extension(content_type) if content_type else None
            filename = f"image{ext}" if ext else (url_name or "image.jpg")

        return await self._upload_media_bytes(image_bytes, filename, content_type)

    @_retried_publish
    async def create_post(
        self,
        title: str,
        content: str,
        status: str = "publish",
        featured_media_id: int | None = None,
    ) -> WPPostItem:
        body: dict = {"title": title, "content": content, "status": status}
        if featured_media_id is not None:
            body["featured_image"] = featured_media_id
        async with httpx.AsyncClient(base_url=_BASE_URL, timeout=_TIMEOUT) as client:
            response = await client.post(
                f"/sites/{self._site_id}/posts/new",
                headers=self._headers(),
                json=body,
            )
        self._raise_for_status(response)
        data = response.json()
        return WPPostItem(
            id=data["ID"],
            title=data.get("title", title),
            url=data.get("URL", ""),
            short_url=data.get("short_URL", ""),
            status=data.get("status", status),
            date=data.get("date", ""),
        )

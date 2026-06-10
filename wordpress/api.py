from __future__ import annotations

import mimetypes
from pathlib import Path

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from auth import TokenManager
from logger import get_logger
from models import PostItem, SiteInfo

_BASE_URL = "https://public-api.wordpress.com/rest/v1.1"


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
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


class WordPressClient:
    def __init__(self, token_manager: TokenManager, site_id: str) -> None:
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
        async with httpx.AsyncClient(base_url=_BASE_URL) as client:
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
    async def get_posts(self, count: int = 10) -> list[PostItem]:
        async with httpx.AsyncClient(base_url=_BASE_URL) as client:
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
                PostItem(
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
        async with httpx.AsyncClient(base_url=_BASE_URL) as client:
            response = await client.post(
                f"/sites/{self._site_id}/posts/{post_id}/delete",
                headers=self._headers(),
            )
        self._raise_for_status(response)

    async def _upload_media_bytes(
        self, data: bytes, filename: str
    ) -> int:
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        async with httpx.AsyncClient(base_url=_BASE_URL) as client:
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

    async def upload_media_from_url(self, image_url: str) -> int:
        async with httpx.AsyncClient() as client:
            response = await client.get(image_url, timeout=30.0)
            response.raise_for_status()
            image_bytes = response.content
        filename = image_url.split("/")[-1].split("?")[0] or "image.jpg"
        return await self._upload_media_bytes(image_bytes, filename)

    @_retried_publish
    async def create_post(
        self,
        title: str,
        content: str,
        status: str = "publish",
        featured_media_id: int | None = None,
    ) -> PostItem:
        body: dict = {"title": title, "content": content, "status": status}
        if featured_media_id is not None:
            body["featured_image"] = featured_media_id
        async with httpx.AsyncClient(base_url=_BASE_URL) as client:
            response = await client.post(
                f"/sites/{self._site_id}/posts/new",
                headers=self._headers(),
                json=body,
            )
        self._raise_for_status(response)
        data = response.json()
        return PostItem(
            id=data["ID"],
            title=data.get("title", title),
            url=data.get("URL", ""),
            short_url=data.get("short_URL", ""),
            status=data.get("status", status),
            date=data.get("date", ""),
        )

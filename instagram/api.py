from __future__ import annotations

import asyncio

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from auth import TokenManager
from logger import get_logger
from models import AccountInfo, MediaItem

_BASE_URL = "https://graph.facebook.com/v21.0"
_CONTAINER_POLL_INTERVAL = 3   # seconds between status checks
_CONTAINER_POLL_MAX = 20       # max polling attempts (~60s total)


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


class InstagramAPIError(Exception):
    pass


class InstagramClient:
    def __init__(self, token_manager: TokenManager, account_id: str) -> None:
        self._tm = token_manager
        self._account_id = account_id
        self._logger = get_logger(__name__)

    async def _token(self) -> str:
        return await self._tm.get_valid_token()

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code >= 400:
            self._logger.error(
                "Instagram API error %s: %s", response.status_code, response.text
            )
            response.raise_for_status()

    @_retried
    async def get_account_info(self) -> AccountInfo:
        token = await self._token()
        async with httpx.AsyncClient(base_url=_BASE_URL) as client:
            response = await client.get(
                f"/{self._account_id}",
                params={
                    "fields": "id,username,name,followers_count,media_count",
                    "access_token": token,
                },
            )
        self._raise_for_status(response)
        data = response.json()
        return AccountInfo(
            id=data["id"],
            username=data.get("username", ""),
            name=data.get("name", ""),
            followers_count=data.get("followers_count", 0),
            media_count=data.get("media_count", 0),
        )

    @_retried
    async def get_media(self, count: int = 10) -> list[MediaItem]:
        token = await self._token()
        async with httpx.AsyncClient(base_url=_BASE_URL) as client:
            response = await client.get(
                f"/{self._account_id}/media",
                params={
                    "fields": "id,caption,media_type,timestamp,permalink",
                    "limit": count,
                    "access_token": token,
                },
            )
        self._raise_for_status(response)
        items = []
        for el in response.json().get("data", []):
            items.append(
                MediaItem(
                    id=el["id"],
                    caption=el.get("caption", ""),
                    media_type=el.get("media_type", ""),
                    timestamp=el.get("timestamp", ""),
                    permalink=el.get("permalink", ""),
                )
            )
        return items

    @_retried
    async def delete_media(self, media_id: str) -> None:
        token = await self._token()
        async with httpx.AsyncClient(base_url=_BASE_URL) as client:
            response = await client.delete(
                f"/{media_id}",
                params={"access_token": token},
            )
        self._raise_for_status(response)

    @_retried
    async def _create_image_container(self, image_url: str, caption: str) -> str:
        token = await self._token()
        async with httpx.AsyncClient(base_url=_BASE_URL) as client:
            response = await client.post(
                f"/{self._account_id}/media",
                params={
                    "image_url": image_url,
                    "caption": caption,
                    "access_token": token,
                },
            )
        self._raise_for_status(response)
        return response.json()["id"]

    async def _wait_for_container(self, container_id: str) -> None:
        token = await self._token()
        for attempt in range(_CONTAINER_POLL_MAX):
            async with httpx.AsyncClient(base_url=_BASE_URL) as client:
                response = await client.get(
                    f"/{container_id}",
                    params={"fields": "status_code", "access_token": token},
                )
            self._raise_for_status(response)
            status = response.json().get("status_code", "")
            if status == "FINISHED":
                return
            if status in ("ERROR", "EXPIRED"):
                raise InstagramAPIError(
                    f"Media container {container_id} failed with status: {status}"
                )
            self._logger.debug(
                "Container %s status: %s (attempt %d/%d)",
                container_id, status, attempt + 1, _CONTAINER_POLL_MAX,
            )
            await asyncio.sleep(_CONTAINER_POLL_INTERVAL)
        raise InstagramAPIError(
            f"Container {container_id} did not reach FINISHED status after "
            f"{_CONTAINER_POLL_MAX} attempts."
        )

    @_retried_publish
    async def _publish_container(self, container_id: str) -> str:
        token = await self._token()
        async with httpx.AsyncClient(base_url=_BASE_URL) as client:
            response = await client.post(
                f"/{self._account_id}/media_publish",
                params={"creation_id": container_id, "access_token": token},
            )
        self._raise_for_status(response)
        return response.json()["id"]

    async def publish_photo(self, image_url: str, caption: str) -> str:
        """
        Two-step Instagram publish: create container → wait for processing → publish.
        Returns the media ID of the published post.
        """
        container_id = await self._create_image_container(image_url, caption)
        self._logger.debug("Media container created: %s", container_id)
        await self._wait_for_container(container_id)
        media_id = await self._publish_container(container_id)
        self._logger.info("Post published successfully: %s", media_id)
        return media_id

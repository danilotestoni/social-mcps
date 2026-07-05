from __future__ import annotations

import asyncio

import httpx

from auth.instagram_auth import InstagramTokenManager
from core.logger import get_logger
from core.models import InstagramAccountInfo, MediaItem
from core.retry import _retried, _retried_publish

_BASE_URL = "https://graph.facebook.com/v21.0"
_CONTAINER_POLL_INTERVAL = 3   # seconds between status checks
_CONTAINER_POLL_MAX = 20       # max polling attempts (~60s total)


class InstagramAPIError(Exception):
    pass


class InstagramClient:
    def __init__(self, token_manager: InstagramTokenManager, account_id: str) -> None:
        self._tm = token_manager
        self._account_id = account_id
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
                "Instagram API error %s: %s", response.status_code, response.text
            )
            response.raise_for_status()

    @_retried
    async def get_account_info(self) -> InstagramAccountInfo:
        headers = await self._auth_headers()
        async with httpx.AsyncClient(base_url=_BASE_URL) as client:
            response = await client.get(
                f"/{self._account_id}",
                params={"fields": "id,username,name,followers_count,media_count"},
                headers=headers,
            )
        self._raise_for_status(response)
        data = response.json()
        return InstagramAccountInfo(
            id=data["id"],
            username=data.get("username", ""),
            name=data.get("name", ""),
            followers_count=data.get("followers_count", 0),
            media_count=data.get("media_count", 0),
        )

    @_retried
    async def get_media(self, count: int = 10) -> list[MediaItem]:
        headers = await self._auth_headers()
        async with httpx.AsyncClient(base_url=_BASE_URL) as client:
            response = await client.get(
                f"/{self._account_id}/media",
                params={
                    "fields": "id,caption,media_type,timestamp,permalink",
                    "limit": count,
                },
                headers=headers,
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
        headers = await self._auth_headers()
        async with httpx.AsyncClient(base_url=_BASE_URL) as client:
            response = await client.delete(f"/{media_id}", headers=headers)
        self._raise_for_status(response)

    @_retried
    async def _create_image_container(self, image_url: str, caption: str) -> str:
        headers = await self._auth_headers()
        async with httpx.AsyncClient(base_url=_BASE_URL) as client:
            response = await client.post(
                f"/{self._account_id}/media",
                params={"image_url": image_url, "caption": caption},
                headers=headers,
            )
        self._raise_for_status(response)
        return response.json()["id"]

    async def _wait_for_container(self, container_id: str) -> None:
        headers = await self._auth_headers()
        for attempt in range(_CONTAINER_POLL_MAX):
            async with httpx.AsyncClient(base_url=_BASE_URL) as client:
                response = await client.get(
                    f"/{container_id}",
                    params={"fields": "status_code"},
                    headers=headers,
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
        headers = await self._auth_headers()
        async with httpx.AsyncClient(base_url=_BASE_URL) as client:
            response = await client.post(
                f"/{self._account_id}/media_publish",
                params={"creation_id": container_id},
                headers=headers,
            )
        self._raise_for_status(response)
        return response.json()["id"]

    async def publish_photo(self, image_url: str, caption: str) -> str:
        container_id = await self._create_image_container(image_url, caption)
        self._logger.debug("Media container created: %s", container_id)
        await self._wait_for_container(container_id)
        media_id = await self._publish_container(container_id)
        self._logger.info("Post published successfully: %s", media_id)
        return media_id

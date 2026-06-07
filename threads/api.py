from __future__ import annotations

import asyncio

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from auth import TokenManager
from logger import get_logger
from models import AccountInfo, ThreadItem

_BASE_URL = "https://graph.threads.net/v1.0"
_CONTAINER_POLL_INTERVAL = 3   # seconds between status checks
_CONTAINER_POLL_MAX = 20       # max polling attempts (~60s total)
_REQUEST_TIMEOUT = 30.0        # seconds — Threads API can be slow on container creation


def _retried(func):
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException)),
        reraise=True,
    )(func)


class ThreadsAPIError(Exception):
    pass


class ThreadsClient:
    def __init__(self, token_manager: TokenManager, user_id: str) -> None:
        self._tm = token_manager
        self._user_id = user_id
        self._logger = get_logger(__name__)

    async def _token(self) -> str:
        return await self._tm.get_valid_token()

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code >= 400:
            self._logger.error(
                "Threads API error %s: %s", response.status_code, response.text
            )
            response.raise_for_status()

    @_retried
    async def get_account_info(self) -> AccountInfo:
        token = await self._token()
        async with httpx.AsyncClient(base_url=_BASE_URL, timeout=_REQUEST_TIMEOUT) as client:
            response = await client.get(
                "/me",
                params={
                    "fields": "id,username,name",
                    "access_token": token,
                },
            )
        self._raise_for_status(response)
        data = response.json()
        return AccountInfo(
            id=data["id"],
            username=data.get("username", ""),
            name=data.get("name", ""),
        )

    @_retried
    async def get_threads(self, count: int = 10) -> list[ThreadItem]:
        token = await self._token()
        async with httpx.AsyncClient(base_url=_BASE_URL, timeout=_REQUEST_TIMEOUT) as client:
            response = await client.get(
                f"/{self._user_id}/threads",
                params={
                    "fields": "id,text,timestamp,media_type,permalink",
                    "limit": count,
                    "access_token": token,
                },
            )
        self._raise_for_status(response)
        items = []
        for el in response.json().get("data", []):
            items.append(
                ThreadItem(
                    id=el["id"],
                    text=el.get("text", ""),
                    media_type=el.get("media_type", ""),
                    timestamp=el.get("timestamp", ""),
                    permalink=el.get("permalink", ""),
                )
            )
        return items

    @_retried
    async def delete_thread(self, thread_id: str) -> None:
        token = await self._token()
        async with httpx.AsyncClient(base_url=_BASE_URL, timeout=_REQUEST_TIMEOUT) as client:
            response = await client.delete(
                f"/{thread_id}",
                params={"access_token": token},
            )
        self._raise_for_status(response)

    @_retried
    async def _create_container(
        self, text: str, image_url: str | None = None
    ) -> str:
        token = await self._token()
        params: dict = {"access_token": token, "text": text}
        if image_url:
            params["media_type"] = "IMAGE"
            params["image_url"] = image_url
        else:
            params["media_type"] = "TEXT"

        async with httpx.AsyncClient(base_url=_BASE_URL, timeout=_REQUEST_TIMEOUT) as client:
            response = await client.post(
                f"/{self._user_id}/threads",
                params=params,
            )
        self._raise_for_status(response)
        return response.json()["id"]

    async def _wait_for_container(self, container_id: str) -> None:
        token = await self._token()
        for attempt in range(_CONTAINER_POLL_MAX):
            async with httpx.AsyncClient(base_url=_BASE_URL, timeout=_REQUEST_TIMEOUT) as client:
                response = await client.get(
                    f"/{container_id}",
                    params={"fields": "status,error_type", "access_token": token},
                )
            self._raise_for_status(response)
            data = response.json()
            status = data.get("status", "")
            if status in ("FINISHED", ""):
                # Empty status means the container is ready (common for TEXT posts)
                return
            if status in ("ERROR", "EXPIRED"):
                error_type = data.get("error_type", "unknown")
                raise ThreadsAPIError(
                    f"Container {container_id} failed with status: {status}, error: {error_type}"
                )
            self._logger.debug(
                "Container %s status: %s (attempt %d/%d)",
                container_id, status, attempt + 1, _CONTAINER_POLL_MAX,
            )
            await asyncio.sleep(_CONTAINER_POLL_INTERVAL)
        raise ThreadsAPIError(
            f"Container {container_id} did not reach FINISHED status after "
            f"{_CONTAINER_POLL_MAX} attempts."
        )

    @_retried
    async def _publish_container(self, container_id: str) -> str:
        token = await self._token()
        async with httpx.AsyncClient(base_url=_BASE_URL, timeout=_REQUEST_TIMEOUT) as client:
            response = await client.post(
                f"/{self._user_id}/threads_publish",
                params={"creation_id": container_id, "access_token": token},
            )
        self._raise_for_status(response)
        return response.json()["id"]

    async def publish_thread(
        self, text: str, image_url: str | None = None
    ) -> str:
        """
        Two-step Threads publish: create container → wait → publish.
        Returns the thread ID of the published post.
        """
        container_id = await self._create_container(text, image_url)
        self._logger.debug("Threads container created: %s", container_id)
        await self._wait_for_container(container_id)
        thread_id = await self._publish_container(container_id)
        self._logger.info("Thread published successfully: %s", thread_id)
        return thread_id

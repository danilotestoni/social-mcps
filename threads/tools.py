from __future__ import annotations

import httpx

from api import ThreadsAPIError, ThreadsClient
from logger import get_logger
from models import ToolResult

_logger = get_logger(__name__)


async def publish_post(
    client: ThreadsClient,
    text: str,
    image_url: str | None = None,
) -> dict:
    try:
        thread_id = await client.publish_thread(text, image_url)
        return ToolResult(success=True, data={"thread_id": thread_id}).model_dump()
    except httpx.HTTPStatusError as exc:
        _logger.error("Threads API error in publish_post: %s", exc.response.text)
        return ToolResult(success=False, error=str(exc)).model_dump()
    except ThreadsAPIError as exc:
        _logger.error("Threads container error in publish_post: %s", exc)
        return ToolResult(success=False, error=str(exc)).model_dump()
    except Exception as exc:
        _logger.exception("Unexpected error in publish_post")
        return ToolResult(success=False, error=str(exc)).model_dump()


async def get_last_posts(client: ThreadsClient, count: int = 10) -> dict:
    try:
        items = await client.get_threads(count)
        return ToolResult(
            success=True, data=[i.model_dump() for i in items]
        ).model_dump()
    except httpx.HTTPStatusError as exc:
        _logger.error("Threads API error in get_last_posts: %s", exc.response.text)
        return ToolResult(success=False, error=str(exc)).model_dump()
    except Exception as exc:
        _logger.exception("Unexpected error in get_last_posts")
        return ToolResult(success=False, error=str(exc)).model_dump()


async def delete_post(client: ThreadsClient, thread_id: str) -> dict:
    try:
        await client.delete_thread(thread_id)
        return ToolResult(success=True, data={"deleted": thread_id}).model_dump()
    except httpx.HTTPStatusError as exc:
        _logger.error("Threads API error in delete_post: %s", exc.response.text)
        return ToolResult(success=False, error=str(exc)).model_dump()
    except Exception as exc:
        _logger.exception("Unexpected error in delete_post")
        return ToolResult(success=False, error=str(exc)).model_dump()


async def get_account_info(client: ThreadsClient) -> dict:
    try:
        info = await client.get_account_info()
        return ToolResult(success=True, data=info.model_dump()).model_dump()
    except httpx.HTTPStatusError as exc:
        _logger.error("Threads API error in get_account_info: %s", exc.response.text)
        return ToolResult(success=False, error=str(exc)).model_dump()
    except Exception as exc:
        _logger.exception("Unexpected error in get_account_info")
        return ToolResult(success=False, error=str(exc)).model_dump()

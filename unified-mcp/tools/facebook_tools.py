from __future__ import annotations

import httpx

from clients.facebook_client import FacebookClient
from core.logger import get_logger
from core.models import ToolResult

_logger = get_logger(__name__)


async def publish_post(
    client: FacebookClient,
    message: str,
    image_url: str | None = None,
    image_path: str | None = None,
    dry_run: bool = False,
) -> dict:
    try:
        if dry_run:
            if image_path:
                mode, payload = "photo_file", {"message": message, "image_path": image_path}
            elif image_url:
                mode, payload = "photo_url", {"message": message, "image_url": image_url}
            else:
                mode, payload = "text", {"message": message}
            return ToolResult(success=True, data={
                "dry_run": True,
                "platform": "facebook",
                "mode": mode,
                "payload": payload,
            }).model_dump()
        if image_path:
            post_id = await client.publish_photo_file(image_path, message)
        elif image_url:
            post_id = await client.publish_photo_url(image_url, message)
        else:
            post_id = await client.publish_text_post(message)
        return ToolResult(success=True, data={"post_id": post_id}).model_dump()
    except httpx.HTTPStatusError as exc:
        _logger.error("Facebook API error in publish_post: %s", exc.response.text)
        return ToolResult(success=False, error=str(exc)).model_dump()
    except Exception as exc:
        _logger.exception("Unexpected error in publish_post")
        return ToolResult(success=False, error=str(exc)).model_dump()


async def get_last_posts(client: FacebookClient, count: int = 10) -> dict:
    try:
        posts = await client.get_posts(count)
        return ToolResult(success=True, data=[p.model_dump() for p in posts]).model_dump()
    except httpx.HTTPStatusError as exc:
        _logger.error("Facebook API error in get_last_posts: %s", exc.response.text)
        return ToolResult(success=False, error=str(exc)).model_dump()
    except Exception as exc:
        _logger.exception("Unexpected error in get_last_posts")
        return ToolResult(success=False, error=str(exc)).model_dump()


async def delete_post(client: FacebookClient, post_id: str) -> dict:
    try:
        await client.delete_post(post_id)
        return ToolResult(success=True, data={"deleted": post_id}).model_dump()
    except httpx.HTTPStatusError as exc:
        _logger.error("Facebook API error in delete_post: %s", exc.response.text)
        return ToolResult(success=False, error=str(exc)).model_dump()
    except Exception as exc:
        _logger.exception("Unexpected error in delete_post")
        return ToolResult(success=False, error=str(exc)).model_dump()


async def get_account_info(client: FacebookClient) -> dict:
    try:
        info = await client.get_page_info()
        return ToolResult(success=True, data=info.model_dump()).model_dump()
    except httpx.HTTPStatusError as exc:
        _logger.error("Facebook API error in get_account_info: %s", exc.response.text)
        return ToolResult(success=False, error=str(exc)).model_dump()
    except Exception as exc:
        _logger.exception("Unexpected error in get_account_info")
        return ToolResult(success=False, error=str(exc)).model_dump()

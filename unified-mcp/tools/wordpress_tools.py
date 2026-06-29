from __future__ import annotations

import httpx

from clients.wordpress_client import WordPressClient
from core.logger import get_logger
from core.models import ToolResult

_logger = get_logger(__name__)


async def publish_post(
    client: WordPressClient,
    title: str,
    content: str,
    status: str = "publish",
    image_url: str | None = None,
    image_path: str | None = None,
    dry_run: bool = False,
) -> dict:
    try:
        if dry_run:
            return ToolResult(success=True, data={
                "dry_run": True,
                "platform": "wordpress",
                "payload": {
                    "title": title,
                    "content_length": len(content),
                    "status": status,
                    "featured_image": image_path or image_url,
                },
            }).model_dump()
        featured_media_id: int | None = None
        if image_path:
            featured_media_id = await client.upload_media_from_path(image_path)
            _logger.debug("Uploaded featured image from path, media ID: %d", featured_media_id)
        elif image_url:
            featured_media_id = await client.upload_media_from_url(image_url)
            _logger.debug("Uploaded featured image from URL, media ID: %d", featured_media_id)
        post = await client.create_post(title, content, status, featured_media_id)
        return ToolResult(success=True, data=post.model_dump()).model_dump()
    except httpx.HTTPStatusError as exc:
        _logger.error("WordPress API error in publish_post: %s", exc.response.text)
        return ToolResult(success=False, error=str(exc)).model_dump()
    except Exception as exc:
        _logger.exception("Unexpected error in publish_post")
        return ToolResult(success=False, error=str(exc)).model_dump()


async def get_last_posts(client: WordPressClient, count: int = 10) -> dict:
    try:
        posts = await client.get_posts(count)
        return ToolResult(success=True, data=[p.model_dump() for p in posts]).model_dump()
    except httpx.HTTPStatusError as exc:
        _logger.error("WordPress API error in get_last_posts: %s", exc.response.text)
        return ToolResult(success=False, error=str(exc)).model_dump()
    except Exception as exc:
        _logger.exception("Unexpected error in get_last_posts")
        return ToolResult(success=False, error=str(exc)).model_dump()


async def delete_post(client: WordPressClient, post_id: int) -> dict:
    try:
        await client.delete_post(post_id)
        return ToolResult(success=True, data={"deleted": post_id}).model_dump()
    except httpx.HTTPStatusError as exc:
        _logger.error("WordPress API error in delete_post: %s", exc.response.text)
        return ToolResult(success=False, error=str(exc)).model_dump()
    except Exception as exc:
        _logger.exception("Unexpected error in delete_post")
        return ToolResult(success=False, error=str(exc)).model_dump()


async def get_account_info(client: WordPressClient) -> dict:
    try:
        info = await client.get_site_info()
        return ToolResult(success=True, data=info.model_dump()).model_dump()
    except httpx.HTTPStatusError as exc:
        _logger.error("WordPress API error in get_account_info: %s", exc.response.text)
        return ToolResult(success=False, error=str(exc)).model_dump()
    except Exception as exc:
        _logger.exception("Unexpected error in get_account_info")
        return ToolResult(success=False, error=str(exc)).model_dump()

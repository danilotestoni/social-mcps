from __future__ import annotations

import httpx

from api import InstagramAPIError, InstagramClient
from logger import get_logger
from models import ToolResult

_logger = get_logger(__name__)

_LOCAL_FILE_ERROR = (
    "Instagram Graph API requires a publicly accessible image URL. "
    "Local file paths cannot be uploaded directly to Instagram. "
    "Please host the image at a public URL and pass it via image_url instead."
)


async def publish_post(
    client: InstagramClient,
    caption: str,
    image_url: str | None = None,
    image_path: str | None = None,
    dry_run: bool = False,
) -> dict:
    if image_path:
        return ToolResult(success=False, error=_LOCAL_FILE_ERROR).model_dump()
    if not image_url:
        return ToolResult(
            success=False,
            error="Instagram requires an image. Provide image_url with a public URL.",
        ).model_dump()
    if dry_run:
        return ToolResult(success=True, data={
            "dry_run": True,
            "platform": "instagram",
            "payload": {
                "caption": caption,
                "image_url": image_url,
                "media_type": "IMAGE",
            },
        }).model_dump()
    try:
        media_id = await client.publish_photo(image_url, caption)
        return ToolResult(success=True, data={"media_id": media_id}).model_dump()
    except httpx.HTTPStatusError as exc:
        _logger.error("Instagram API error in publish_post: %s", exc.response.text)
        return ToolResult(success=False, error=str(exc)).model_dump()
    except InstagramAPIError as exc:
        _logger.error("Instagram container error in publish_post: %s", exc)
        return ToolResult(success=False, error=str(exc)).model_dump()
    except Exception as exc:
        _logger.exception("Unexpected error in publish_post")
        return ToolResult(success=False, error=str(exc)).model_dump()


async def get_last_posts(client: InstagramClient, count: int = 10) -> dict:
    try:
        items = await client.get_media(count)
        return ToolResult(
            success=True, data=[i.model_dump() for i in items]
        ).model_dump()
    except httpx.HTTPStatusError as exc:
        _logger.error("Instagram API error in get_last_posts: %s", exc.response.text)
        return ToolResult(success=False, error=str(exc)).model_dump()
    except Exception as exc:
        _logger.exception("Unexpected error in get_last_posts")
        return ToolResult(success=False, error=str(exc)).model_dump()


async def delete_post(client: InstagramClient, media_id: str) -> dict:
    try:
        await client.delete_media(media_id)
        return ToolResult(success=True, data={"deleted": media_id}).model_dump()
    except httpx.HTTPStatusError as exc:
        _logger.error("Instagram API error in delete_post: %s", exc.response.text)
        return ToolResult(success=False, error=str(exc)).model_dump()
    except Exception as exc:
        _logger.exception("Unexpected error in delete_post")
        return ToolResult(success=False, error=str(exc)).model_dump()


async def get_account_info(client: InstagramClient) -> dict:
    try:
        info = await client.get_account_info()
        return ToolResult(success=True, data=info.model_dump()).model_dump()
    except httpx.HTTPStatusError as exc:
        _logger.error("Instagram API error in get_account_info: %s", exc.response.text)
        return ToolResult(success=False, error=str(exc)).model_dump()
    except Exception as exc:
        _logger.exception("Unexpected error in get_account_info")
        return ToolResult(success=False, error=str(exc)).model_dump()

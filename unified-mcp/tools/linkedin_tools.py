from __future__ import annotations

from pathlib import Path

import httpx

from clients.linkedin_client import LinkedInClient
from core.logger import get_logger
from core.models import ToolResult

_logger = get_logger(__name__)


async def _resolve_image(
    client: LinkedInClient,
    person_urn: str,
    image_url: str | None,
    image_path: str | None,
) -> str | None:
    if not image_path and not image_url:
        return None
    if image_path:
        image_bytes = Path(image_path).read_bytes()
    else:
        async with httpx.AsyncClient() as http:
            response = await http.get(image_url, timeout=30.0)  # type: ignore[arg-type]
            response.raise_for_status()
            image_bytes = response.content
    upload_url, asset_urn = await client.register_image_upload(person_urn)
    await client.upload_image_binary(upload_url, image_bytes)
    return asset_urn


async def publish_post(
    client: LinkedInClient,
    person_urn: str,
    text: str,
    image_url: str | None = None,
    image_path: str | None = None,
    dry_run: bool = False,
) -> dict:
    try:
        if dry_run:
            return ToolResult(success=True, data={
                "dry_run": True,
                "platform": "linkedin",
                "payload": {
                    "person_urn": person_urn,
                    "text": text,
                    "image": image_path or image_url,
                },
            }).model_dump()
        asset_urn = await _resolve_image(client, person_urn, image_url, image_path)
        post_urn = await client.create_post(person_urn, text, asset_urn)
        return ToolResult(success=True, data={"post_urn": post_urn}).model_dump()
    except httpx.HTTPStatusError as exc:
        _logger.error("LinkedIn API error in publish_post: %s", exc.response.text)
        return ToolResult(success=False, error=str(exc)).model_dump()
    except Exception as exc:
        _logger.exception("Unexpected error in publish_post")
        return ToolResult(success=False, error=str(exc)).model_dump()


async def get_last_posts(client: LinkedInClient, person_urn: str, count: int = 10) -> dict:
    try:
        posts = await client.get_posts(person_urn, count)
        return ToolResult(success=True, data=[p.model_dump() for p in posts]).model_dump()
    except httpx.HTTPStatusError as exc:
        _logger.error("LinkedIn API error in get_last_posts: %s", exc.response.text)
        return ToolResult(success=False, error=str(exc)).model_dump()
    except Exception as exc:
        _logger.exception("Unexpected error in get_last_posts")
        return ToolResult(success=False, error=str(exc)).model_dump()


async def delete_post(client: LinkedInClient, post_urn: str) -> dict:
    try:
        await client.delete_post(post_urn)
        return ToolResult(success=True, data={"deleted": post_urn}).model_dump()
    except httpx.HTTPStatusError as exc:
        _logger.error("LinkedIn API error in delete_post: %s", exc.response.text)
        return ToolResult(success=False, error=str(exc)).model_dump()
    except Exception as exc:
        _logger.exception("Unexpected error in delete_post")
        return ToolResult(success=False, error=str(exc)).model_dump()


async def get_account_info(client: LinkedInClient) -> dict:
    try:
        profile = await client.get_profile()
        return ToolResult(success=True, data=profile.model_dump()).model_dump()
    except httpx.HTTPStatusError as exc:
        _logger.error("LinkedIn API error in get_account_info: %s", exc.response.text)
        return ToolResult(success=False, error=str(exc)).model_dump()
    except Exception as exc:
        _logger.exception("Unexpected error in get_account_info")
        return ToolResult(success=False, error=str(exc)).model_dump()

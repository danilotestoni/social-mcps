from __future__ import annotations

import re
import time
from pathlib import Path

import httpx

from clients.gemini_client import GeminiAPIError, GeminiImageClient
from core.logger import get_logger
from core.models import ToolResult

_logger = get_logger(__name__)

_OUTPUT_DIR = Path(__file__).parent.parent / "generated"

_EXT_BY_MIME = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}


def _safe_filename(prompt: str, mime_type: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", prompt.lower()).strip("-")[:40] or "image"
    ext = _EXT_BY_MIME.get(mime_type, "png")
    return f"{slug}-{int(time.time())}.{ext}"


async def generate_image(
    client: GeminiImageClient,
    prompt: str,
    aspect_ratio: str = "1:1",
    wordpress_client=None,
    upload_to_wordpress: bool = True,
    dry_run: bool = False,
) -> dict:
    """
    Generate an image with Gemini and return its local path — plus a public
    WordPress media URL when a WordPress client is available, so the image
    can be used directly by Instagram/Facebook/Threads (they require a
    publicly accessible URL).
    """
    if dry_run:
        return ToolResult(success=True, data={
            "dry_run": True,
            "platform": "gemini",
            "payload": {
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "upload_to_wordpress": upload_to_wordpress and wordpress_client is not None,
            },
        }).model_dump()

    try:
        image_bytes, mime_type = await client.generate_image(prompt, aspect_ratio)
    except GeminiAPIError as exc:
        return ToolResult(success=False, error=f"Gemini error: {exc}").model_dump()
    except httpx.HTTPStatusError as exc:
        return ToolResult(
            success=False, error=f"Gemini API error: {exc.response.status_code}"
        ).model_dump()
    except Exception as exc:
        _logger.error("Unexpected error generating image: %s", exc)
        return ToolResult(success=False, error=f"Unexpected error: {exc}").model_dump()

    filename = _safe_filename(prompt, mime_type)
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    local_path = _OUTPUT_DIR / filename
    local_path.write_bytes(image_bytes)
    _logger.info("Image saved to %s (%d bytes).", local_path, len(image_bytes))

    data: dict = {
        "local_path": str(local_path),
        "mime_type": mime_type,
        "size_bytes": len(image_bytes),
        "provider": "gemini",
    }

    if upload_to_wordpress and wordpress_client is not None:
        try:
            media = await wordpress_client.upload_media_get_url(image_bytes, filename)
            data["public_url"] = media["url"]
            data["wordpress_media_id"] = media["id"]
        except Exception as exc:
            _logger.warning("WordPress media upload failed: %s", exc)
            data["public_url_error"] = (
                f"Image generated but WordPress upload failed: {exc}. "
                "Use local_path or retry the upload."
            )
    elif upload_to_wordpress and wordpress_client is None:
        data["public_url_error"] = (
            "WordPress is not enabled — no public URL available. "
            "Instagram/Threads need a public URL; use local_path for "
            "Facebook/LinkedIn/WordPress (they accept local files)."
        )

    return ToolResult(success=True, data=data).model_dump()

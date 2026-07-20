from __future__ import annotations

import re
import time
from pathlib import Path

from clients.gemini_client import GeminiImageClient
from clients.pollinations_client import PollinationsImageClient
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


async def _try_provider(
    provider_name: str, prompt: str, aspect_ratio: str, client, errors: list[str]
) -> tuple[bytes, str] | None:
    try:
        return await client.generate_image(prompt, aspect_ratio)
    except Exception as exc:
        _logger.warning("%s image generation failed: %s", provider_name, exc)
        errors.append(f"{provider_name}: {exc}")
        return None


async def generate_image(
    gemini_client: GeminiImageClient | None,
    prompt: str,
    aspect_ratio: str = "1:1",
    wordpress_client=None,
    upload_to_wordpress: bool = True,
    dry_run: bool = False,
    pollinations_client: PollinationsImageClient | None = None,
) -> dict:
    """
    Generate an image with Gemini (preferred) or Pollinations.ai — a free,
    keyless provider used as an automatic fallback when Gemini is unavailable
    or fails (missing key, quota exhausted, API error). Returns the local
    file path and, when WordPress is enabled and upload_to_wordpress is true,
    a public media URL usable directly as image_url for Instagram, Facebook,
    and Threads posts.
    """
    if dry_run:
        provider = "gemini" if gemini_client is not None else "pollinations"
        return ToolResult(success=True, data={
            "dry_run": True,
            "platform": provider,
            "payload": {
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "upload_to_wordpress": upload_to_wordpress and wordpress_client is not None,
            },
        }).model_dump()

    errors: list[str] = []
    result: tuple[bytes, str] | None = None
    provider: str | None = None

    if gemini_client is not None:
        result = await _try_provider("Gemini", prompt, aspect_ratio, gemini_client, errors)
        if result is not None:
            provider = "gemini"

    if result is None and pollinations_client is not None:
        result = await _try_provider("Pollinations", prompt, aspect_ratio, pollinations_client, errors)
        if result is not None:
            provider = "pollinations"

    if result is None:
        error_detail = "; ".join(errors) if errors else "No image provider configured."
        return ToolResult(success=False, error=error_detail).model_dump()

    image_bytes, mime_type = result

    filename = _safe_filename(prompt, mime_type)
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    local_path = _OUTPUT_DIR / filename
    local_path.write_bytes(image_bytes)
    _logger.info("Image saved to %s (%d bytes).", local_path, len(image_bytes))

    data: dict = {
        "local_path": str(local_path),
        "mime_type": mime_type,
        "size_bytes": len(image_bytes),
        "provider": provider,
    }
    if errors:
        data["fallback_reason"] = errors[0]

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

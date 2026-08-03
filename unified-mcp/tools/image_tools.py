from __future__ import annotations

import io
import re
import time
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import Image

from clients.cloudflare_worker_image_client import CloudflareWorkerImageClient
from clients.huggingface_flux_client import HuggingFaceFluxClient
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

# mcp.server.fastmcp.Image expects a *format* string ("jpeg", not "jpg") used
# verbatim to build the MIME type it reports to the client.
_IMAGE_FORMAT_BY_MIME = {
    "image/png": "png",
    "image/jpeg": "jpeg",
    "image/webp": "webp",
}

# Soft cap for the MCP-visible preview payload. Base64 inflates raw bytes by
# ~33%, and MCP clients (ChatGPT, claude.ai, etc.) have their own practical
# message-size limits — images above this are downscaled for the *visual*
# preview only. The local file used for publishing/automation is never
# touched or replaced.
_MCP_PREVIEW_MAX_BYTES = 1_500_000
_MCP_PREVIEW_MAX_DIMENSION = 1280


def _safe_filename(prompt: str, mime_type: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", prompt.lower()).strip("-")[:40] or "image"
    ext = _EXT_BY_MIME.get(mime_type, "png")
    return f"{slug}-{int(time.time())}.{ext}"


def _detect_mime_type(image_bytes: bytes, fallback: str) -> str:
    """
    Best-effort real MIME type from the file's magic bytes. Providers
    usually report the correct content-type themselves; this only catches
    the rare mislabeled case, so it falls back to the provider's own value
    for anything it doesn't recognize (e.g. gif, unexpected formats).
    """
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return fallback


def _build_preview_content(image_bytes: bytes, mime_type: str) -> Optional[Image]:
    """
    Builds the MCP ImageContent used purely for chat visualization, reusing
    the already-in-memory bytes (no extra disk read). Downscales large
    images so the preview stays within a practical payload size — the
    original bytes on disk (used for publishing/automation) are never
    modified. Returns None and logs a warning if preview construction fails;
    callers must treat that as non-fatal — the image was still generated
    and saved successfully.
    """
    try:
        preview_bytes = image_bytes
        preview_mime = mime_type

        if len(preview_bytes) > _MCP_PREVIEW_MAX_BYTES:
            from PIL import Image as PILImage

            with PILImage.open(io.BytesIO(image_bytes)) as pil_image:
                pil_image = pil_image.convert("RGB")
                pil_image.thumbnail((_MCP_PREVIEW_MAX_DIMENSION, _MCP_PREVIEW_MAX_DIMENSION))
                buffer = io.BytesIO()
                pil_image.save(buffer, format="JPEG", quality=85)
                preview_bytes = buffer.getvalue()
                preview_mime = "image/jpeg"

            _logger.info(
                "Downscaled MCP preview from %d to %d bytes (file on disk is untouched).",
                len(image_bytes),
                len(preview_bytes),
            )

        image_format = _IMAGE_FORMAT_BY_MIME.get(preview_mime, "png")
        return Image(data=preview_bytes, format=image_format)
    except Exception as exc:
        _logger.warning("Could not build MCP preview image content: %s", exc)
        return None


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
    prompt: str,
    aspect_ratio: str = "1:1",
    *,
    cloudflare_client: CloudflareWorkerImageClient | None = None,
    huggingface_client: HuggingFaceFluxClient | None = None,
    pollinations_client: PollinationsImageClient | None = None,
    wordpress_client=None,
    upload_to_wordpress: bool = True,
    dry_run: bool = False,
) -> tuple[dict, Optional[Image]]:
    """
    Generate an image, trying providers in order: Cloudflare Workers AI
    (FLUX-1-schnell, free) -> Hugging Face FLUX.1-schnell Space (free) ->
    Pollinations.ai (free, keyless) — each is tried only if the previous one
    is unavailable or fails, so this always has a working provider as long
    as at least one client is configured.

    Returns (structured_result, mcp_image_content):
      - structured_result: the same dict shape as before (local_path,
        mime_type, size_bytes, provider, fallback_reason, and — when
        WordPress is enabled and upload_to_wordpress is true — public_url /
        wordpress_media_id). This is what publishing tools (WordPress,
        Facebook, LinkedIn via local_path; Instagram/Threads via public_url)
        should keep consuming — unchanged.
      - mcp_image_content: an mcp.server.fastmcp.Image ready to be returned
        alongside the structured result so MCP clients (ChatGPT, claude.ai)
        render the image inline. None on dry runs, failures, or if building
        the preview itself failed (which never fails the overall operation —
        the image is still generated, saved, and usable via local_path).
    """
    if dry_run:
        if cloudflare_client is not None:
            provider = "cloudflare"
        elif huggingface_client is not None:
            provider = "huggingface"
        else:
            provider = "pollinations"
        result = ToolResult(success=True, data={
            "dry_run": True,
            "platform": provider,
            "payload": {
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "upload_to_wordpress": upload_to_wordpress and wordpress_client is not None,
            },
        }).model_dump()
        return result, None

    errors: list[str] = []
    result: tuple[bytes, str] | None = None
    provider: str | None = None

    if cloudflare_client is not None:
        result = await _try_provider("Cloudflare", prompt, aspect_ratio, cloudflare_client, errors)
        if result is not None:
            provider = "cloudflare"

    if result is None and huggingface_client is not None:
        result = await _try_provider("HuggingFace", prompt, aspect_ratio, huggingface_client, errors)
        if result is not None:
            provider = "huggingface"

    if result is None and pollinations_client is not None:
        result = await _try_provider("Pollinations", prompt, aspect_ratio, pollinations_client, errors)
        if result is not None:
            provider = "pollinations"

    if result is None:
        error_detail = "; ".join(errors) if errors else "No image provider configured."
        return ToolResult(success=False, error=error_detail).model_dump(), None

    image_bytes, reported_mime_type = result
    mime_type = _detect_mime_type(image_bytes, reported_mime_type)

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

    preview_content = _build_preview_content(image_bytes, mime_type)
    if preview_content is None:
        data["mcp_preview_error"] = (
            "Could not build an inline chat preview; the image was generated "
            "and saved successfully — use local_path/public_url."
        )

    return ToolResult(success=True, data=data).model_dump(), preview_content

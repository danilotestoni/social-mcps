from __future__ import annotations

import base64
import binascii
import io
import re

import httpx

from clients.gcs_temp_storage_client import GCSTempStorageClient, GCSTempStorageError
from core.errors import describe_exception
from core.logger import get_logger
from core.models import ToolResult

_logger = get_logger(__name__)

# Accepts a plain base64 string or a data URI ("data:image/jpeg;base64,....").
_DATA_URI_RE = re.compile(r"^data:(?P<mime>[\w./+-]+);base64,(?P<b64>.+)$", re.DOTALL)

# Large base64 strings embedded as a single JSON-RPC tool argument have
# proven unreliable through some MCP client/gateway chains (observed:
# silent corruption of a ~120KB payload through ChatGPT's connector,
# surfacing as a base64 decode error on our end). Cap this path to small
# images and steer larger ones toward image_url, which only transports a
# short string — the actual bytes are fetched server-side instead.
_MAX_BASE64_DECODED_BYTES = 4 * 1024 * 1024  # 4 MB
_MAX_URL_FETCH_BYTES = 20 * 1024 * 1024  # 20 MB
_URL_FETCH_TIMEOUT = 30.0

# Auto-optimization: images above this size or dimension get downscaled and
# re-encoded as JPEG before upload — keeps bucket usage lean and stays
# comfortably within every target platform's own limits (Instagram, etc.).
# Best-effort only: if this fails for any reason, the original bytes are
# uploaded as-is rather than failing the whole operation.
_AUTO_OPTIMIZE_THRESHOLD_BYTES = 1_500_000  # 1.5 MB
_AUTO_OPTIMIZE_MAX_DIMENSION = 1600
_AUTO_OPTIMIZE_JPEG_QUALITY = 85


def _decode_image_base64(image_base64: str, default_mime_type: str) -> tuple[bytes, str]:
    match = _DATA_URI_RE.match(image_base64.strip())
    if match:
        raw_b64 = match.group("b64")
        mime_type = match.group("mime") or default_mime_type
    else:
        raw_b64 = image_base64
        mime_type = default_mime_type

    # Strip ALL whitespace, not just at the ends — base64 strings relayed
    # through some MCP gateways/clients can pick up inserted newlines
    # (MIME-style wrapping) along the way.
    raw_b64 = re.sub(r"\s+", "", raw_b64)

    try:
        data = base64.b64decode(raw_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(
            f"image_base64 is not valid base64 ({exc}). Large base64 "
            "payloads can get corrupted in transit through some MCP "
            "clients — use upload_temp_image with image_url instead if "
            "this keeps happening."
        ) from exc

    if not data:
        raise ValueError("image_base64 decoded to an empty file.")

    if len(data) > _MAX_BASE64_DECODED_BYTES:
        raise ValueError(
            f"Decoded image is {len(data)} bytes, over the "
            f"{_MAX_BASE64_DECODED_BYTES}-byte limit for image_base64 "
            "(large base64 payloads are unreliable through some MCP "
            "clients). Use image_url instead for larger images."
        )

    return data, mime_type


async def _fetch_image_url(image_url: str, default_mime_type: str) -> tuple[bytes, str]:
    try:
        async with httpx.AsyncClient(timeout=_URL_FETCH_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(image_url)
    except httpx.HTTPError as exc:
        raise ValueError(f"Could not fetch image_url: {exc}") from exc

    if response.status_code >= 400:
        raise ValueError(f"image_url returned HTTP {response.status_code}.")

    data = response.content
    if not data:
        raise ValueError("image_url returned an empty response.")

    if len(data) > _MAX_URL_FETCH_BYTES:
        raise ValueError(
            f"Image at image_url is {len(data)} bytes, over the "
            f"{_MAX_URL_FETCH_BYTES}-byte limit."
        )

    content_type = response.headers.get("content-type", "").split(";")[0].strip()
    mime_type = content_type or default_mime_type
    return data, mime_type


def _maybe_optimize(data: bytes, mime_type: str) -> tuple[bytes, str]:
    """
    Downscales and re-encodes as JPEG when the image is larger than
    reasonable for a temp upload — best-effort, never raises: any failure
    just falls back to the original bytes untouched.
    """
    if len(data) <= _AUTO_OPTIMIZE_THRESHOLD_BYTES:
        return data, mime_type

    try:
        from PIL import Image as PILImage

        with PILImage.open(io.BytesIO(data)) as pil_image:
            if max(pil_image.size) <= _AUTO_OPTIMIZE_MAX_DIMENSION and mime_type == "image/jpeg":
                return data, mime_type
            pil_image = pil_image.convert("RGB")
            pil_image.thumbnail((_AUTO_OPTIMIZE_MAX_DIMENSION, _AUTO_OPTIMIZE_MAX_DIMENSION))
            buffer = io.BytesIO()
            pil_image.save(buffer, format="JPEG", quality=_AUTO_OPTIMIZE_JPEG_QUALITY)
            optimized = buffer.getvalue()
    except Exception as exc:
        _logger.warning("Could not auto-optimize image, uploading as-is: %s", exc)
        return data, mime_type

    _logger.info("Auto-optimized image from %d to %d bytes.", len(data), len(optimized))
    return optimized, "image/jpeg"


async def upload_temp_image(
    client: GCSTempStorageClient,
    image_base64: str | None = None,
    image_url: str | None = None,
    mime_type: str = "image/jpeg",
    filename: str | None = None,
    ttl_seconds: int = 900,
    auto_optimize: bool = True,
) -> dict:
    if not image_base64 and not image_url:
        return ToolResult(
            success=False, error="Provide either image_base64 or image_url."
        ).model_dump()
    if image_base64 and image_url:
        return ToolResult(
            success=False,
            error="Provide only one of image_base64 or image_url, not both.",
        ).model_dump()

    try:
        if image_url:
            data, resolved_mime_type = await _fetch_image_url(image_url, mime_type)
        else:
            data, resolved_mime_type = _decode_image_base64(image_base64, mime_type)

        if auto_optimize:
            data, resolved_mime_type = _maybe_optimize(data, resolved_mime_type)

        result = await client.upload_temp_image(
            data, resolved_mime_type, filename=filename, ttl_seconds=ttl_seconds
        )
        return ToolResult(success=True, data=result).model_dump()
    except ValueError as exc:
        return ToolResult(success=False, error=describe_exception(exc)).model_dump()
    except GCSTempStorageError as exc:
        _logger.error("GCS temp storage config error in upload_temp_image: %s", exc)
        return ToolResult(success=False, error=describe_exception(exc)).model_dump()
    except Exception as exc:
        _logger.exception("Unexpected error in upload_temp_image")
        return ToolResult(success=False, error=describe_exception(exc)).model_dump()


async def delete_temp_image(client: GCSTempStorageClient, object_name: str) -> dict:
    try:
        result = await client.delete_temp_image(object_name)
        return ToolResult(success=True, data=result).model_dump()
    except Exception as exc:
        _logger.exception("Unexpected error in delete_temp_image")
        return ToolResult(success=False, error=describe_exception(exc)).model_dump()

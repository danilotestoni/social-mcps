from __future__ import annotations

import base64
import binascii
import re

import httpx

from clients.gcs_temp_storage_client import GCSTempStorageClient, GCSTempStorageError
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


async def upload_temp_image(
    client: GCSTempStorageClient,
    image_base64: str | None = None,
    image_url: str | None = None,
    mime_type: str = "image/jpeg",
    filename: str | None = None,
    ttl_seconds: int = 900,
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
        result = await client.upload_temp_image(
            data, resolved_mime_type, filename=filename, ttl_seconds=ttl_seconds
        )
        return ToolResult(success=True, data=result).model_dump()
    except ValueError as exc:
        return ToolResult(success=False, error=str(exc)).model_dump()
    except GCSTempStorageError as exc:
        _logger.error("GCS temp storage config error in upload_temp_image: %s", exc)
        return ToolResult(success=False, error=str(exc)).model_dump()
    except Exception as exc:
        _logger.exception("Unexpected error in upload_temp_image")
        return ToolResult(success=False, error=str(exc)).model_dump()


async def delete_temp_image(client: GCSTempStorageClient, object_name: str) -> dict:
    try:
        result = await client.delete_temp_image(object_name)
        return ToolResult(success=True, data=result).model_dump()
    except Exception as exc:
        _logger.exception("Unexpected error in delete_temp_image")
        return ToolResult(success=False, error=str(exc)).model_dump()

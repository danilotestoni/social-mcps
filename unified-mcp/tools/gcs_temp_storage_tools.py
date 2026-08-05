from __future__ import annotations

import base64
import binascii
import re

from clients.gcs_temp_storage_client import GCSTempStorageClient, GCSTempStorageError
from core.logger import get_logger
from core.models import ToolResult

_logger = get_logger(__name__)

# Accepts a plain base64 string or a data URI ("data:image/jpeg;base64,....").
_DATA_URI_RE = re.compile(r"^data:(?P<mime>[\w./+-]+);base64,(?P<b64>.+)$", re.DOTALL)


def _decode_image_base64(image_base64: str, default_mime_type: str) -> tuple[bytes, str]:
    match = _DATA_URI_RE.match(image_base64.strip())
    if match:
        raw_b64 = match.group("b64")
        mime_type = match.group("mime") or default_mime_type
    else:
        raw_b64 = image_base64.strip()
        mime_type = default_mime_type

    try:
        data = base64.b64decode(raw_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"image_base64 is not valid base64: {exc}") from exc

    if not data:
        raise ValueError("image_base64 decoded to an empty file.")

    return data, mime_type


async def upload_temp_image(
    client: GCSTempStorageClient,
    image_base64: str,
    mime_type: str = "image/jpeg",
    filename: str | None = None,
    ttl_seconds: int = 900,
) -> dict:
    try:
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

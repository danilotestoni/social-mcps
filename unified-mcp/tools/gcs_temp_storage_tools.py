from __future__ import annotations

import base64
import binascii
import io
import json
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


# ChatGPT attachments/generated images have no fetchable URL of their own,
# but their "Share" page (chatgpt.com/s/...) embeds one: a
# backend-api/estuary/public_content/enc/<token> link that IS publicly
# downloadable with no auth (verified live: plain curl, 200, real image
# bytes). If image_url resolves to an HTML page, we look inside it for
# that link instead of failing — turns "paste the share link" into a
# one-step operation.
_ESTUARY_URL_RE = re.compile(
    r"https://chatgpt\.com/backend-api/estuary/public_content/enc/[A-Za-z0-9+/=_-]+"
)
_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _pick_estuary_url(html: str) -> str | None:
    """
    A share page can embed several enc/<token> links for the same image
    (different renditions — thumbnail, link-unfurl preview, markdown
    embed...). Each token is itself base64 JSON with an "id" field; the
    direct file reference looks like "m_.../file_..." while the other
    renditions have extra "sediment:"/"#unfurl"/"#md" fragments in theirs.
    Prefer a direct reference; fall back to the first match otherwise.
    """
    candidates = _ESTUARY_URL_RE.findall(html)
    if not candidates:
        return None

    def is_direct_file_reference(url: str) -> bool:
        token = url.rsplit("/", 1)[-1]
        try:
            padded = token + "=" * (-len(token) % 4)
            payload = json.loads(base64.b64decode(padded))
        except Exception:
            return False
        return "sediment" not in str(payload.get("id", ""))

    for candidate in candidates:
        if is_direct_file_reference(candidate):
            return candidate
    return candidates[0]


async def _fetch_image_url(
    image_url: str, default_mime_type: str, _following_estuary_link: bool = False
) -> tuple[bytes, str]:
    try:
        async with httpx.AsyncClient(timeout=_URL_FETCH_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(image_url, headers={"User-Agent": _BROWSER_USER_AGENT})
    except httpx.HTTPError as exc:
        raise ValueError(f"Could not fetch image_url: {exc}") from exc

    if response.status_code >= 400:
        raise ValueError(f"image_url returned HTTP {response.status_code}.")

    content_type = response.headers.get("content-type", "").split(";")[0].strip()

    if content_type.startswith("text/html") and not _following_estuary_link:
        estuary_url = _pick_estuary_url(response.text)
        if estuary_url is None:
            raise ValueError(
                "image_url returned an HTML page instead of an image, and no "
                "ChatGPT estuary image link was found inside it. If this is a "
                "ChatGPT 'Share' link, make sure it's the share link for the "
                "image/message itself."
            )
        _logger.info("image_url returned HTML; following the embedded estuary link instead.")
        return await _fetch_image_url(estuary_url, default_mime_type, _following_estuary_link=True)

    data = response.content
    if not data:
        raise ValueError("image_url returned an empty response.")

    if len(data) > _MAX_URL_FETCH_BYTES:
        raise ValueError(
            f"Image at image_url is {len(data)} bytes, over the "
            f"{_MAX_URL_FETCH_BYTES}-byte limit."
        )

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


# ── Chunked upload ──────────────────────────────────────────────────────────
#
# For images with no available URL (e.g. a file that only exists in the
# calling client's own local/sandbox filesystem) where a single
# image_base64 call has failed or is expected to fail — split the transfer
# into many small tool calls instead. Recommended chunk size: ~32KB of raw
# bytes (~44KB base64) per call, comfortably under every failure threshold
# observed so far.


def _decode_chunk_base64(chunk_base64: str) -> bytes:
    raw = re.sub(r"\s+", "", chunk_base64)
    try:
        return base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"chunk_base64 is not valid base64 ({exc}).") from exc


async def start_temp_image_upload(client: GCSTempStorageClient) -> dict:
    try:
        upload_id = await client.start_chunked_upload()
        return ToolResult(success=True, data={"upload_id": upload_id}).model_dump()
    except Exception as exc:
        _logger.exception("Unexpected error in start_temp_image_upload")
        return ToolResult(success=False, error=describe_exception(exc)).model_dump()


async def upload_temp_image_chunk(
    client: GCSTempStorageClient,
    upload_id: str,
    chunk_index: int,
    chunk_base64: str,
) -> dict:
    try:
        data = _decode_chunk_base64(chunk_base64)
        await client.upload_chunk(upload_id, chunk_index, data)
        return ToolResult(
            success=True, data={"upload_id": upload_id, "chunk_index": chunk_index, "bytes": len(data)}
        ).model_dump()
    except ValueError as exc:
        return ToolResult(success=False, error=describe_exception(exc)).model_dump()
    except GCSTempStorageError as exc:
        return ToolResult(success=False, error=describe_exception(exc)).model_dump()
    except Exception as exc:
        _logger.exception("Unexpected error in upload_temp_image_chunk")
        return ToolResult(success=False, error=describe_exception(exc)).model_dump()


async def finish_temp_image_upload(
    client: GCSTempStorageClient,
    upload_id: str,
    total_chunks: int,
    mime_type: str = "image/jpeg",
    filename: str | None = None,
    ttl_seconds: int = 900,
    auto_optimize: bool = True,
) -> dict:
    try:
        data = await client.assemble_chunks(upload_id, total_chunks)
        resolved_mime_type = mime_type
        if auto_optimize:
            data, resolved_mime_type = _maybe_optimize(data, resolved_mime_type)
        result = await client.upload_temp_image(
            data, resolved_mime_type, filename=filename, ttl_seconds=ttl_seconds
        )
        await client.cleanup_chunks(upload_id, total_chunks)
        return ToolResult(success=True, data=result).model_dump()
    except GCSTempStorageError as exc:
        return ToolResult(success=False, error=describe_exception(exc)).model_dump()
    except Exception as exc:
        _logger.exception("Unexpected error in finish_temp_image_upload")
        return ToolResult(success=False, error=describe_exception(exc)).model_dump()

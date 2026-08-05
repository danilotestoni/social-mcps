from __future__ import annotations

import asyncio
import datetime
import mimetypes
import time
import uuid

from google.cloud import storage
from google.cloud.exceptions import NotFound

from core.logger import get_logger
from core.temp_image_tokens import mint

_OBJECT_PREFIX = "tmp"
_MAX_TTL_SECONDS = 7 * 24 * 3600  # 604800s, matched to GCS's own V4 signed URL ceiling


class GCSTempStorageError(Exception):
    pass


class GCSTempStorageClient:
    """
    Temporary object storage for images that did NOT come from
    generate_image — e.g. an image attached or created directly in the
    chat — so publishing tools that require a public image_url (Instagram,
    Threads, ...) have something to point at without ever making the
    bucket itself public.

    The bucket stays private (no allUsers/allAuthenticatedUsers binding).
    Public access is granted per-object through this server's own
    /temp-image/<token> proxy route (see server.py's TempImageProxyMiddleware)
    rather than GCS's native V4 signed URLs: Instagram's Graph API media-
    container endpoint was observed failing every single fetch of a raw V4
    signed URL with a generic "OAuthException code 1" — consistent with an
    intermediate over-decoding the nested percent-encoding V4 signed URLs
    require in X-Goog-Credential (which itself contains pre-encoded "@"
    and "/"), corrupting the signature before it reaches GCS. Routing
    through our own plain, single-segment URL sidesteps that class of bug
    entirely — the actual authenticated GCS read happens server-side, no
    signed URL involved in it at all.

    Objects are meant to be deleted right after publishing via
    delete_temp_image — a bucket lifecycle rule is the safety net for
    anything left behind by a crashed/aborted flow.
    """

    def __init__(self, bucket_name: str, public_base_url: str = "") -> None:
        self._bucket_name = bucket_name
        self._public_base_url = public_base_url.rstrip("/")
        self._logger = get_logger(__name__)
        self._client: storage.Client | None = None

    def _get_client(self) -> storage.Client:
        if self._client is None:
            self._client = storage.Client()
        return self._client

    def _proxy_url(self, object_name: str, expires_at: int) -> str:
        if not self._public_base_url:
            raise GCSTempStorageError(
                "PUBLIC_BASE_URL is not set — cannot build a /temp-image/ proxy "
                "URL. Set it to this server's own public origin (e.g. the Cloud "
                "Run service URL)."
            )
        token = mint(object_name, expires_at)
        return f"{self._public_base_url}/temp-image/{token}"

    def _upload_temp_image_sync(
        self,
        data: bytes,
        mime_type: str,
        filename: str | None,
        ttl_seconds: int,
    ) -> dict:
        ttl_seconds = max(1, min(ttl_seconds, _MAX_TTL_SECONDS))

        client = self._get_client()
        bucket = client.bucket(self._bucket_name)

        ext = mimetypes.guess_extension(mime_type) or ".bin"
        object_name = f"{_OBJECT_PREFIX}/{uuid.uuid4().hex}{ext}"

        blob = bucket.blob(object_name)
        if filename:
            blob.metadata = {"original_filename": filename}
        blob.upload_from_string(data, content_type=mime_type)

        expires_at = int(time.time()) + ttl_seconds
        proxy_url = self._proxy_url(object_name, expires_at)
        expires_at_iso = datetime.datetime.fromtimestamp(
            expires_at, tz=datetime.timezone.utc
        ).isoformat()

        self._logger.info(
            "Uploaded temp image %s to gs://%s/%s (%d bytes, expires in %ds).",
            object_name,
            self._bucket_name,
            object_name,
            len(data),
            ttl_seconds,
        )
        return {
            "object_name": object_name,
            "bucket": self._bucket_name,
            "signed_url": proxy_url,
            "public_url": proxy_url,
            "mime_type": mime_type,
            "size_bytes": len(data),
            "expires_at": expires_at_iso,
        }

    async def upload_temp_image(
        self,
        data: bytes,
        mime_type: str,
        filename: str | None = None,
        ttl_seconds: int = 900,
    ) -> dict:
        """
        Uploads bytes to the private temp bucket and returns a short-lived
        proxy URL (this server's own /temp-image/<token> route — see the
        class docstring for why that's used instead of a raw GCS signed
        URL). Runs the blocking google-cloud-storage calls in a worker
        thread so the async MCP event loop isn't blocked.
        """
        return await asyncio.to_thread(
            self._upload_temp_image_sync, data, mime_type, filename, ttl_seconds
        )

    def _download_temp_image_sync(self, object_name: str) -> tuple[bytes, str]:
        client = self._get_client()
        blob = client.bucket(self._bucket_name).blob(object_name)
        blob.reload()
        data = blob.download_as_bytes()
        return data, blob.content_type or "application/octet-stream"

    async def download_temp_image(self, object_name: str) -> tuple[bytes, str]:
        """
        Fetches an object's bytes and content type directly via the
        authenticated Cloud Storage API — used by the /temp-image/ proxy
        route to serve the file to external fetchers (e.g. Instagram)
        without ever generating a GCS signed URL for them.
        """
        return await asyncio.to_thread(self._download_temp_image_sync, object_name)

    def _delete_temp_image_sync(self, object_name: str) -> dict:
        client = self._get_client()
        bucket = client.bucket(self._bucket_name)
        blob = bucket.blob(object_name)
        try:
            blob.delete()
        except NotFound:
            self._logger.info("Temp image %s already gone (expired or deleted).", object_name)
            return {"deleted": False, "object_name": object_name, "reason": "not_found"}
        self._logger.info("Deleted temp image %s.", object_name)
        return {"deleted": True, "object_name": object_name}

    async def delete_temp_image(self, object_name: str) -> dict:
        return await asyncio.to_thread(self._delete_temp_image_sync, object_name)

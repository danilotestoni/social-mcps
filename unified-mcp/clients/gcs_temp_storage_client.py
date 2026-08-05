from __future__ import annotations

import asyncio
import datetime
import mimetypes
import uuid
from typing import Any

import google.auth
from google.auth.credentials import Signing
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.cloud import storage
from google.cloud.exceptions import NotFound

from core.logger import get_logger

_OBJECT_PREFIX = "tmp"
_MAX_TTL_SECONDS = 7 * 24 * 3600  # 604800s — GCS's own V4 signed URL ceiling

# storage.Client()'s own credentials carry storage-only scopes, which the
# IAM signBlob call rejects with "insufficient authentication scopes" — the
# signing delegation needs its own, separately-scoped credentials.
_SIGNING_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


class GCSTempStorageError(Exception):
    pass


class GCSTempStorageClient:
    """
    Temporary object storage for images that did NOT come from
    generate_image — e.g. an image attached or created directly in the
    chat — so publishing tools that require a public image_url (Instagram,
    Threads, ...) have something to point at without ever making the
    bucket itself public.

    The bucket must stay private (no allUsers/allAuthenticatedUsers
    binding); access is granted per-object through short-lived V4 signed
    URLs. Objects are meant to be deleted right after publishing via
    delete_temp_image — a bucket lifecycle rule is the safety net for
    anything left behind by a crashed/aborted flow.
    """

    def __init__(self, bucket_name: str) -> None:
        self._bucket_name = bucket_name
        self._logger = get_logger(__name__)
        self._client: storage.Client | None = None

    def _get_client(self) -> storage.Client:
        if self._client is None:
            self._client = storage.Client()
        return self._client

    def _signing_kwargs(self) -> dict[str, Any]:
        """
        google-cloud-storage can only sign directly when the active
        credentials carry a private key (e.g. a service-account JSON key
        file via GOOGLE_APPLICATION_CREDENTIALS — the standard local-dev
        setup). On Cloud Run the attached service account has no private
        key, so signing must be delegated to the IAM signBlob API by
        passing service_account_email + access_token explicitly — this is
        google-cloud-storage's own documented mechanism for signing
        without a key file. Requires the "Service Account Token Creator"
        role (roles/iam.serviceAccountTokenCreator) granted to the service
        account on itself.

        Fetches its own credentials (scoped to cloud-platform) rather than
        reusing the storage client's — those carry storage-only scopes,
        which the IAM signBlob call rejects as insufficient.
        """
        credentials, _project = google.auth.default(scopes=_SIGNING_SCOPES)
        if isinstance(credentials, Signing):
            return {}

        credentials.refresh(GoogleAuthRequest())
        service_account_email = getattr(credentials, "service_account_email", None)
        if not service_account_email or not credentials.token:
            raise GCSTempStorageError(
                "Cannot sign URLs with the current credentials — no private key "
                "and no impersonable service account email. Locally, set "
                "GOOGLE_APPLICATION_CREDENTIALS to a service-account JSON key "
                "file; on Cloud Run, grant the attached service account "
                "roles/iam.serviceAccountTokenCreator on itself."
            )
        return {
            "service_account_email": service_account_email,
            "access_token": credentials.token,
        }

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

        expiration = datetime.timedelta(seconds=ttl_seconds)
        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=expiration,
            method="GET",
            **self._signing_kwargs(),
        )
        expires_at = (datetime.datetime.now(datetime.timezone.utc) + expiration).isoformat()

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
            "signed_url": signed_url,
            "public_url": signed_url,
            "mime_type": mime_type,
            "size_bytes": len(data),
            "expires_at": expires_at,
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
        V4 signed GET URL. Runs the blocking google-cloud-storage calls in
        a worker thread so the async MCP event loop isn't blocked.
        """
        return await asyncio.to_thread(
            self._upload_temp_image_sync, data, mime_type, filename, ttl_seconds
        )

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

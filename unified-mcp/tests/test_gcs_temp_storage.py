from __future__ import annotations

import asyncio
import base64
import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from clients.gcs_temp_storage_client import GCSTempStorageClient, GCSTempStorageError
import tools.gcs_temp_storage_tools as gcs_tools


class _FakeSigningCredentials:
    """Stands in for a service-account JSON key credential (has a private key)."""


class _FakeComputeCredentials:
    """Stands in for the Cloud Run attached service account (no private key)."""

    def __init__(self):
        self.token = "fake-access-token"
        self.service_account_email = None  # resolved only after refresh(), like the real thing

    def refresh(self, request):
        self.service_account_email = "817213604469-compute@developer.gserviceaccount.com"


def _fake_blob(store: dict, name: str):
    blob = MagicMock()
    blob.name = name

    def upload_from_string(data, content_type=None):
        store[name] = {"data": data, "content_type": content_type}

    def delete():
        if name not in store:
            from google.cloud.exceptions import NotFound

            raise NotFound("gone")
        del store[name]

    def generate_signed_url(**kwargs):
        # Assert the caller actually tried to authorize the signature somehow.
        assert kwargs.get("version") == "v4"
        assert kwargs.get("method") == "GET"
        return f"https://storage.googleapis.com/fake-bucket/{name}?X-Goog-Signature=fake"

    blob.upload_from_string.side_effect = upload_from_string
    blob.delete.side_effect = delete
    blob.generate_signed_url.side_effect = generate_signed_url
    return blob


class GCSTempStorageClientTests(TestCase):
    def _make_client_with_fake_storage(self, credentials):
        store: dict = {}
        fake_bucket = MagicMock()
        fake_bucket.blob.side_effect = lambda name: _fake_blob(store, name)

        fake_storage_client = MagicMock()
        fake_storage_client._credentials = credentials
        fake_storage_client.bucket.return_value = fake_bucket

        client = GCSTempStorageClient("fake-bucket")
        client._client = fake_storage_client
        return client, store

    def test_upload_with_local_service_account_key_signs_directly(self) -> None:
        with patch(
            "clients.gcs_temp_storage_client.isinstance",
            side_effect=lambda obj, cls: True,  # simulate Signing credentials
        ):
            client, store = self._make_client_with_fake_storage(_FakeSigningCredentials())
            result = asyncio.run(
                client.upload_temp_image(b"fake-jpeg-bytes", "image/jpeg", ttl_seconds=60)
            )

        self.assertTrue(result["object_name"].startswith("tmp/"))
        self.assertTrue(result["object_name"].endswith(".jpg"))
        self.assertEqual(result["signed_url"], result["public_url"])
        self.assertEqual(result["mime_type"], "image/jpeg")
        self.assertEqual(result["size_bytes"], len(b"fake-jpeg-bytes"))
        self.assertIn(result["object_name"], store)
        self.assertEqual(store[result["object_name"]]["data"], b"fake-jpeg-bytes")

    def test_upload_on_cloud_run_delegates_signing_to_iam(self) -> None:
        credentials = _FakeComputeCredentials()
        client, store = self._make_client_with_fake_storage(credentials)

        result = asyncio.run(
            client.upload_temp_image(b"fake-png-bytes", "image/png", ttl_seconds=60)
        )

        # refresh() must have been called to resolve the real service account email
        self.assertEqual(
            credentials.service_account_email,
            "817213604469-compute@developer.gserviceaccount.com",
        )
        self.assertTrue(result["signed_url"].startswith("https://storage.googleapis.com/"))
        self.assertIn(result["object_name"], store)

    def test_upload_raises_clear_error_when_signing_is_impossible(self) -> None:
        credentials = MagicMock()
        credentials.token = None
        credentials.service_account_email = None
        client, _store = self._make_client_with_fake_storage(credentials)

        with self.assertRaises(GCSTempStorageError):
            asyncio.run(client.upload_temp_image(b"data", "image/jpeg"))

    def test_delete_removes_object(self) -> None:
        client, store = self._make_client_with_fake_storage(_FakeComputeCredentials())
        store["tmp/abc.jpg"] = {"data": b"x", "content_type": "image/jpeg"}

        result = asyncio.run(client.delete_temp_image("tmp/abc.jpg"))

        self.assertTrue(result["deleted"])
        self.assertNotIn("tmp/abc.jpg", store)

    def test_delete_is_safe_when_object_already_gone(self) -> None:
        client, _store = self._make_client_with_fake_storage(_FakeComputeCredentials())

        result = asyncio.run(client.delete_temp_image("tmp/does-not-exist.jpg"))

        self.assertFalse(result["deleted"])
        self.assertEqual(result["reason"], "not_found")


class GcsTempStorageToolsTests(TestCase):
    """Tests the MCP-facing tool layer: base64/data-URI decoding, error shape."""

    def _make_fake_client(self):
        client = MagicMock()

        async def upload_temp_image(data, mime_type, filename=None, ttl_seconds=900):
            return {
                "object_name": "tmp/fake.jpg",
                "bucket": "fake-bucket",
                "signed_url": "https://storage.googleapis.com/fake-bucket/tmp/fake.jpg?sig=1",
                "public_url": "https://storage.googleapis.com/fake-bucket/tmp/fake.jpg?sig=1",
                "mime_type": mime_type,
                "size_bytes": len(data),
                "expires_at": "2026-01-01T00:00:00+00:00",
            }

        async def delete_temp_image(object_name):
            return {"deleted": True, "object_name": object_name}

        client.upload_temp_image.side_effect = upload_temp_image
        client.delete_temp_image.side_effect = delete_temp_image
        return client

    def test_upload_temp_image_accepts_plain_base64(self) -> None:
        client = self._make_fake_client()
        raw = base64.b64encode(b"raw-image-bytes").decode()

        result = asyncio.run(gcs_tools.upload_temp_image(client, raw, "image/jpeg"))

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["mime_type"], "image/jpeg")
        self.assertEqual(result["data"]["size_bytes"], len(b"raw-image-bytes"))

    def test_upload_temp_image_accepts_data_uri_and_infers_mime_type(self) -> None:
        client = self._make_fake_client()
        raw = base64.b64encode(b"png-bytes").decode()
        data_uri = f"data:image/png;base64,{raw}"

        result = asyncio.run(gcs_tools.upload_temp_image(client, data_uri, "image/jpeg"))

        self.assertTrue(result["success"])
        # mime_type from the data URI wins over the mime_type argument's default.
        self.assertEqual(result["data"]["mime_type"], "image/png")

    def test_upload_temp_image_rejects_invalid_base64(self) -> None:
        client = self._make_fake_client()

        result = asyncio.run(gcs_tools.upload_temp_image(client, "not-valid-base64!!", "image/jpeg"))

        self.assertFalse(result["success"])
        self.assertIn("base64", result["error"])
        client.upload_temp_image.assert_not_called()

    def test_delete_temp_image_returns_deletion_result(self) -> None:
        client = self._make_fake_client()

        result = asyncio.run(gcs_tools.delete_temp_image(client, "tmp/fake.jpg"))

        self.assertTrue(result["success"])
        self.assertTrue(result["data"]["deleted"])

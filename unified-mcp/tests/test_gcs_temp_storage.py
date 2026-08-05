from __future__ import annotations

import asyncio
import base64
import os
import sys
import time
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from clients.gcs_temp_storage_client import GCSTempStorageClient, GCSTempStorageError
from core.temp_image_tokens import TempImageTokenError, mint, verify
import tools.gcs_temp_storage_tools as gcs_tools


def _fake_blob(store: dict, name: str):
    blob = MagicMock()
    blob.name = name
    blob.content_type = None

    def upload_from_string(data, content_type=None):
        store[name] = {"data": data, "content_type": content_type}
        blob.content_type = content_type

    def reload():
        if name in store:
            blob.content_type = store[name]["content_type"]

    def download_as_bytes():
        return store[name]["data"]

    def delete():
        if name not in store:
            from google.cloud.exceptions import NotFound

            raise NotFound("gone")
        del store[name]

    blob.upload_from_string.side_effect = upload_from_string
    blob.reload.side_effect = reload
    blob.download_as_bytes.side_effect = download_as_bytes
    blob.delete.side_effect = delete
    return blob


class GCSTempStorageClientTests(TestCase):
    def setUp(self) -> None:
        patcher = patch.dict(os.environ, {"MCP_AUTH_TOKEN": "test-signing-secret"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _make_client(self, public_base_url="https://unified-mcp.example.run.app"):
        store: dict = {}
        fake_bucket = MagicMock()
        fake_bucket.blob.side_effect = lambda name: _fake_blob(store, name)

        fake_storage_client = MagicMock()
        fake_storage_client.bucket.return_value = fake_bucket

        client = GCSTempStorageClient("fake-bucket", public_base_url=public_base_url)
        client._client = fake_storage_client
        return client, store

    def test_upload_returns_own_proxy_url_not_a_raw_gcs_url(self) -> None:
        client, store = self._make_client()

        result = asyncio.run(
            client.upload_temp_image(b"fake-jpeg-bytes", "image/jpeg", ttl_seconds=60)
        )

        self.assertTrue(result["object_name"].startswith("tmp/"))
        self.assertTrue(result["object_name"].endswith(".jpg"))
        self.assertEqual(result["signed_url"], result["public_url"])
        self.assertTrue(
            result["public_url"].startswith("https://unified-mcp.example.run.app/temp-image/")
        )
        self.assertNotIn("storage.googleapis.com", result["public_url"])
        self.assertNotIn("X-Goog-Signature", result["public_url"])
        self.assertEqual(result["mime_type"], "image/jpeg")
        self.assertEqual(result["size_bytes"], len(b"fake-jpeg-bytes"))
        self.assertIn(result["object_name"], store)

    def test_upload_without_public_base_url_raises_clear_error(self) -> None:
        client, _store = self._make_client(public_base_url="")

        with self.assertRaises(GCSTempStorageError):
            asyncio.run(client.upload_temp_image(b"data", "image/jpeg"))

    def test_download_returns_bytes_and_content_type(self) -> None:
        client, store = self._make_client()
        upload_result = asyncio.run(
            client.upload_temp_image(b"real-bytes-here", "image/png", ttl_seconds=60)
        )

        data, content_type = asyncio.run(
            client.download_temp_image(upload_result["object_name"])
        )

        self.assertEqual(data, b"real-bytes-here")
        self.assertEqual(content_type, "image/png")

    def test_delete_removes_object(self) -> None:
        client, store = self._make_client()
        store["tmp/abc.jpg"] = {"data": b"x", "content_type": "image/jpeg"}

        result = asyncio.run(client.delete_temp_image("tmp/abc.jpg"))

        self.assertTrue(result["deleted"])
        self.assertNotIn("tmp/abc.jpg", store)

    def test_delete_is_safe_when_object_already_gone(self) -> None:
        client, _store = self._make_client()

        result = asyncio.run(client.delete_temp_image("tmp/does-not-exist.jpg"))

        self.assertFalse(result["deleted"])
        self.assertEqual(result["reason"], "not_found")


class TempImageTokenTests(TestCase):
    def setUp(self) -> None:
        patcher = patch.dict(os.environ, {"MCP_AUTH_TOKEN": "test-signing-secret"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_mint_and_verify_roundtrip(self) -> None:
        token = mint("tmp/abc123.jpg", int(time.time()) + 60)

        object_name = verify(token)

        self.assertEqual(object_name, "tmp/abc123.jpg")

    def test_verify_rejects_expired_token(self) -> None:
        token = mint("tmp/abc123.jpg", int(time.time()) - 1)

        with self.assertRaises(TempImageTokenError):
            verify(token)

    def test_verify_rejects_tampered_object_name(self) -> None:
        token = mint("tmp/abc123.jpg", int(time.time()) + 60)
        payload_b64, signature_b64 = token.split(".", 1)
        tampered = f"{payload_b64}x.{signature_b64}"

        with self.assertRaises(TempImageTokenError):
            verify(tampered)

    def test_verify_rejects_wrong_signing_key(self) -> None:
        token = mint("tmp/abc123.jpg", int(time.time()) + 60)

        with patch.dict(os.environ, {"MCP_AUTH_TOKEN": "a-different-secret"}):
            with self.assertRaises(TempImageTokenError):
                verify(token)

    def test_verify_rejects_malformed_token(self) -> None:
        with self.assertRaises(TempImageTokenError):
            verify("not-a-valid-token")


class GcsTempStorageToolsTests(TestCase):
    """Tests the MCP-facing tool layer: base64/data-URI decoding, error shape."""

    def _make_fake_client(self):
        client = MagicMock()

        async def upload_temp_image(data, mime_type, filename=None, ttl_seconds=900):
            return {
                "object_name": "tmp/fake.jpg",
                "bucket": "fake-bucket",
                "signed_url": "https://unified-mcp.example.run.app/temp-image/abc.def",
                "public_url": "https://unified-mcp.example.run.app/temp-image/abc.def",
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

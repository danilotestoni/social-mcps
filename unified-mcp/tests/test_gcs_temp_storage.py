from __future__ import annotations

import asyncio
import base64
import io
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
        if name not in store:
            from google.cloud.exceptions import NotFound

            raise NotFound("gone")
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

    def test_start_chunked_upload_returns_an_id(self) -> None:
        client, _store = self._make_client()

        upload_id = asyncio.run(client.start_chunked_upload())

        self.assertTrue(upload_id)
        self.assertIsInstance(upload_id, str)

    def test_assemble_chunks_concatenates_in_index_order(self) -> None:
        client, store = self._make_client()
        upload_id = "test-upload"

        asyncio.run(client.upload_chunk(upload_id, 1, b"-world"))
        asyncio.run(client.upload_chunk(upload_id, 0, b"hello"))

        data = asyncio.run(client.assemble_chunks(upload_id, total_chunks=2))

        self.assertEqual(data, b"hello-world")
        # Chunks are staged under tmp/ so the existing lifecycle rule covers them.
        self.assertTrue(all(name.startswith("tmp/_chunks/") for name in store))

    def test_assemble_chunks_raises_clear_error_on_missing_chunk(self) -> None:
        client, _store = self._make_client()
        upload_id = "test-upload"
        asyncio.run(client.upload_chunk(upload_id, 0, b"only-this-one"))

        with self.assertRaises(GCSTempStorageError) as ctx:
            asyncio.run(client.assemble_chunks(upload_id, total_chunks=2))

        self.assertIn("Chunk 1", str(ctx.exception))

    def test_cleanup_chunks_removes_all_staged_chunks(self) -> None:
        client, store = self._make_client()
        upload_id = "test-upload"
        asyncio.run(client.upload_chunk(upload_id, 0, b"a"))
        asyncio.run(client.upload_chunk(upload_id, 1, b"b"))

        asyncio.run(client.cleanup_chunks(upload_id, total_chunks=2))

        self.assertEqual(store, {})


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

        result = asyncio.run(
            gcs_tools.upload_temp_image(client, image_base64=raw, mime_type="image/jpeg")
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["mime_type"], "image/jpeg")
        self.assertEqual(result["data"]["size_bytes"], len(b"raw-image-bytes"))

    def test_upload_temp_image_accepts_data_uri_and_infers_mime_type(self) -> None:
        client = self._make_fake_client()
        raw = base64.b64encode(b"png-bytes").decode()
        data_uri = f"data:image/png;base64,{raw}"

        result = asyncio.run(
            gcs_tools.upload_temp_image(client, image_base64=data_uri, mime_type="image/jpeg")
        )

        self.assertTrue(result["success"])
        # mime_type from the data URI wins over the mime_type argument's default.
        self.assertEqual(result["data"]["mime_type"], "image/png")

    def test_upload_temp_image_rejects_invalid_base64(self) -> None:
        client = self._make_fake_client()

        result = asyncio.run(
            gcs_tools.upload_temp_image(
                client, image_base64="not-valid-base64!!", mime_type="image/jpeg"
            )
        )

        self.assertFalse(result["success"])
        self.assertIn("base64", result["error"])
        client.upload_temp_image.assert_not_called()

    def test_upload_temp_image_strips_embedded_whitespace(self) -> None:
        client = self._make_fake_client()
        raw = base64.b64encode(b"raw-image-bytes-here").decode()
        wrapped = "\n".join(raw[i : i + 8] for i in range(0, len(raw), 8))

        result = asyncio.run(gcs_tools.upload_temp_image(client, image_base64=wrapped))

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["size_bytes"], len(b"raw-image-bytes-here"))

    def test_upload_temp_image_rejects_oversized_base64(self) -> None:
        client = self._make_fake_client()
        huge = base64.b64encode(b"x" * (gcs_tools._MAX_BASE64_DECODED_BYTES + 1)).decode()

        result = asyncio.run(gcs_tools.upload_temp_image(client, image_base64=huge))

        self.assertFalse(result["success"])
        self.assertIn("byte limit", result["error"])
        client.upload_temp_image.assert_not_called()

    def test_upload_temp_image_rejects_when_neither_source_given(self) -> None:
        client = self._make_fake_client()

        result = asyncio.run(gcs_tools.upload_temp_image(client))

        self.assertFalse(result["success"])
        client.upload_temp_image.assert_not_called()

    def test_upload_temp_image_rejects_when_both_sources_given(self) -> None:
        client = self._make_fake_client()
        raw = base64.b64encode(b"data").decode()

        result = asyncio.run(
            gcs_tools.upload_temp_image(
                client, image_base64=raw, image_url="https://example.com/img.jpg"
            )
        )

        self.assertFalse(result["success"])
        client.upload_temp_image.assert_not_called()

    def test_upload_temp_image_fetches_from_image_url(self) -> None:
        import httpx

        client = self._make_fake_client()

        def handler(request):
            return httpx.Response(200, content=b"fetched-bytes", headers={"content-type": "image/webp"})

        transport = httpx.MockTransport(handler)

        async def fake_get(self, url):
            async with httpx.AsyncClient(transport=transport) as c:
                return await c.request("GET", url)

        with patch("httpx.AsyncClient.get", fake_get):
            result = asyncio.run(
                gcs_tools.upload_temp_image(client, image_url="https://example.com/img.webp")
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["mime_type"], "image/webp")
        self.assertEqual(result["data"]["size_bytes"], len(b"fetched-bytes"))

    def test_upload_temp_image_rejects_http_error_from_image_url(self) -> None:
        import httpx

        client = self._make_fake_client()

        def handler(request):
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)

        async def fake_get(self, url):
            async with httpx.AsyncClient(transport=transport) as c:
                return await c.request("GET", url)

        with patch("httpx.AsyncClient.get", fake_get):
            result = asyncio.run(
                gcs_tools.upload_temp_image(client, image_url="https://example.com/missing.jpg")
            )

        self.assertFalse(result["success"])
        self.assertIn("404", result["error"])
        client.upload_temp_image.assert_not_called()

    def test_delete_temp_image_returns_deletion_result(self) -> None:
        client = self._make_fake_client()

        result = asyncio.run(gcs_tools.delete_temp_image(client, "tmp/fake.jpg"))

        self.assertTrue(result["success"])
        self.assertTrue(result["data"]["deleted"])


class AutoOptimizeTests(TestCase):
    def _make_fake_client(self):
        client = MagicMock()
        captured = {}

        async def upload_temp_image(data, mime_type, filename=None, ttl_seconds=900):
            captured["data"] = data
            captured["mime_type"] = mime_type
            return {
                "object_name": "tmp/fake.jpg",
                "bucket": "fake-bucket",
                "signed_url": "https://unified-mcp.example.run.app/temp-image/abc.def",
                "public_url": "https://unified-mcp.example.run.app/temp-image/abc.def",
                "mime_type": mime_type,
                "size_bytes": len(data),
                "expires_at": "2026-01-01T00:00:00+00:00",
            }

        client.upload_temp_image.side_effect = upload_temp_image
        return client, captured

    def _make_noisy_png(self, size):
        import random

        from PIL import Image as PILImage

        rng = random.Random(0)
        width, height = size
        pixel_data = bytes(rng.getrandbits(8) for _ in range(width * height * 3))
        buffer = io.BytesIO()
        PILImage.frombytes("RGB", size, pixel_data).save(buffer, format="PNG")
        return buffer.getvalue()

    def test_small_image_is_uploaded_untouched(self) -> None:
        client, captured = self._make_fake_client()
        small_png = base64.b64encode(b"tiny-fake-png-bytes").decode()

        result = asyncio.run(gcs_tools.upload_temp_image(client, image_base64=small_png))

        self.assertTrue(result["success"])
        self.assertEqual(captured["data"], b"tiny-fake-png-bytes")
        self.assertEqual(captured["mime_type"], "image/jpeg")

    def test_large_image_gets_downscaled_and_reencoded(self) -> None:
        client, captured = self._make_fake_client()
        large_png = self._make_noisy_png((900, 900))
        self.assertGreater(len(large_png), gcs_tools._AUTO_OPTIMIZE_THRESHOLD_BYTES)
        raw = base64.b64encode(large_png).decode()

        result = asyncio.run(
            gcs_tools.upload_temp_image(client, image_base64=raw, mime_type="image/png")
        )

        self.assertTrue(result["success"])
        self.assertLess(len(captured["data"]), len(large_png))
        self.assertEqual(captured["mime_type"], "image/jpeg")

    def test_auto_optimize_false_uploads_original_bytes(self) -> None:
        client, captured = self._make_fake_client()
        large_png = self._make_noisy_png((900, 900))
        raw = base64.b64encode(large_png).decode()

        result = asyncio.run(
            gcs_tools.upload_temp_image(
                client, image_base64=raw, mime_type="image/png", auto_optimize=False
            )
        )

        self.assertTrue(result["success"])
        self.assertEqual(captured["data"], large_png)
        self.assertEqual(captured["mime_type"], "image/png")


class ChunkedUploadToolTests(TestCase):
    """
    Covers the start/upload_chunk/finish flow at the tool layer — the path
    recommended when a file only exists locally to the caller (no URL) and
    a single image_base64 call has failed or is expected to fail.
    """

    def _make_fake_client(self):
        client = MagicMock()
        chunks: dict[tuple[str, int], bytes] = {}
        captured = {}

        async def start_chunked_upload():
            return "upload-abc"

        async def upload_chunk(upload_id, chunk_index, data):
            chunks[(upload_id, chunk_index)] = data

        async def assemble_chunks(upload_id, total_chunks):
            missing = [i for i in range(total_chunks) if (upload_id, i) not in chunks]
            if missing:
                from clients.gcs_temp_storage_client import GCSTempStorageError

                raise GCSTempStorageError(f"Chunk {missing[0]} of {total_chunks} is missing")
            return b"".join(chunks[(upload_id, i)] for i in range(total_chunks))

        async def cleanup_chunks(upload_id, total_chunks):
            for i in range(total_chunks):
                chunks.pop((upload_id, i), None)

        async def upload_temp_image(data, mime_type, filename=None, ttl_seconds=900):
            captured["data"] = data
            captured["mime_type"] = mime_type
            return {
                "object_name": "tmp/assembled.jpg",
                "bucket": "fake-bucket",
                "signed_url": "https://unified-mcp.example.run.app/temp-image/abc.def",
                "public_url": "https://unified-mcp.example.run.app/temp-image/abc.def",
                "mime_type": mime_type,
                "size_bytes": len(data),
                "expires_at": "2026-01-01T00:00:00+00:00",
            }

        client.start_chunked_upload.side_effect = start_chunked_upload
        client.upload_chunk.side_effect = upload_chunk
        client.assemble_chunks.side_effect = assemble_chunks
        client.cleanup_chunks.side_effect = cleanup_chunks
        client.upload_temp_image.side_effect = upload_temp_image
        return client, chunks, captured

    def test_start_returns_an_upload_id(self) -> None:
        client, _chunks, _captured = self._make_fake_client()

        result = asyncio.run(gcs_tools.start_temp_image_upload(client))

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["upload_id"], "upload-abc")

    def test_full_chunked_flow_reassembles_original_bytes(self) -> None:
        client, _chunks, captured = self._make_fake_client()
        original = b"a fairly ordinary fake jpeg payload, split into pieces"
        part_a, part_b, part_c = original[:20], original[20:40], original[40:]

        start = asyncio.run(gcs_tools.start_temp_image_upload(client))
        upload_id = start["data"]["upload_id"]

        for index, part in enumerate([part_a, part_b, part_c]):
            chunk_result = asyncio.run(
                gcs_tools.upload_temp_image_chunk(
                    client, upload_id, index, base64.b64encode(part).decode()
                )
            )
            self.assertTrue(chunk_result["success"])

        finish_result = asyncio.run(
            gcs_tools.finish_temp_image_upload(
                client, upload_id, total_chunks=3, auto_optimize=False
            )
        )

        self.assertTrue(finish_result["success"])
        self.assertEqual(captured["data"], original)
        self.assertEqual(
            finish_result["data"]["public_url"],
            "https://unified-mcp.example.run.app/temp-image/abc.def",
        )

    def test_upload_chunk_rejects_invalid_base64(self) -> None:
        client, chunks, _captured = self._make_fake_client()

        result = asyncio.run(
            gcs_tools.upload_temp_image_chunk(client, "upload-abc", 0, "not-valid-base64!!")
        )

        self.assertFalse(result["success"])
        self.assertIn("base64", result["error"])
        self.assertEqual(chunks, {})

    def test_finish_fails_clearly_when_a_chunk_is_missing(self) -> None:
        client, _chunks, _captured = self._make_fake_client()
        upload_id = "upload-abc"
        asyncio.run(
            gcs_tools.upload_temp_image_chunk(
                client, upload_id, 0, base64.b64encode(b"only-chunk-zero").decode()
            )
        )

        result = asyncio.run(
            gcs_tools.finish_temp_image_upload(client, upload_id, total_chunks=2)
        )

        self.assertFalse(result["success"])
        self.assertIn("Chunk 1", result["error"])
        client.upload_temp_image.assert_not_called()

    def test_finish_applies_auto_optimize_to_assembled_bytes(self) -> None:
        client, _chunks, captured = self._make_fake_client()
        large_png = AutoOptimizeTests()._make_noisy_png((900, 900))
        self.assertGreater(len(large_png), gcs_tools._AUTO_OPTIMIZE_THRESHOLD_BYTES)

        upload_id = "upload-large"
        chunk_size = 40_000
        for index in range(0, len(large_png), chunk_size):
            part = large_png[index : index + chunk_size]
            asyncio.run(
                gcs_tools.upload_temp_image_chunk(
                    client, upload_id, index // chunk_size, base64.b64encode(part).decode()
                )
            )
        total_chunks = (len(large_png) + chunk_size - 1) // chunk_size

        result = asyncio.run(
            gcs_tools.finish_temp_image_upload(
                client, upload_id, total_chunks=total_chunks, mime_type="image/png"
            )
        )

        self.assertTrue(result["success"])
        self.assertLess(len(captured["data"]), len(large_png))
        self.assertEqual(captured["mime_type"], "image/jpeg")

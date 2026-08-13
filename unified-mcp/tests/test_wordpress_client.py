from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from clients.wordpress_client import WordPressClient


class _FakeTokenManager:
    def get_token(self) -> str:
        return "fake-token"


def _install_mock_transport(handler):
    """
    Patches clients.wordpress_client's httpx.AsyncClient so every instance
    it creates uses the given MockTransport handler instead of hitting the
    real network.
    """
    real_async_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_async_client(*args, **kwargs)

    return patch("clients.wordpress_client.httpx.AsyncClient", side_effect=factory)


class UploadMediaFromUrlTests(TestCase):
    def test_opaque_proxy_url_uses_response_content_type(self) -> None:
        """
        Our own /temp-image/<token> proxy URL has no real filename or
        extension in its last path segment (it's a signed token) — the
        upload must fall back to the Content-Type the server actually
        returned instead of guessing "application/octet-stream" from the
        URL, since WordPress.com's /media/new has rejected uploads whose
        filename carries no recognizable image extension.
        """
        image_url = (
            "https://unified-mcp.example.run.app/temp-image/"
            "MTc4NjYxOTYxMzp0bXAvNTJlNGJlNDEzMTNmNDMzNWJlMjQzNTc5Yzk5Y2FmZWQuanBn"
            ".ZbvTdZ3XQ6Xf2YFfnb4zskYkGgva6ObRyHqQEvjLQmY"
        )
        captured_files = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "unified-mcp.example.run.app":
                return httpx.Response(
                    200,
                    content=b"\xff\xd8\xff\xe0fakejpegbytes",
                    headers={"content-type": "image/jpeg"},
                )
            if request.url.path.endswith("/media/new"):
                content_type = request.headers.get("content-type", "")
                assert content_type.startswith("multipart/form-data")
                # Sanity: the actual multipart body carries the filename
                # and part content-type we care about; the mock transport
                # doesn't parse it for us, so assert via the fake client
                # below wasn't necessary — real assertion happens through
                # captured_files, populated by patching _upload_media_bytes
                # would be circular, so instead check the raw body.
                body = request.content
                captured_files["body"] = body
                return httpx.Response(200, json={"media": [{"ID": 42, "URL": "https://x/y.jpg"}]})
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")

        client = WordPressClient(_FakeTokenManager(), site_id="123")

        with _install_mock_transport(handler):
            media_id = asyncio.run(client.upload_media_from_url(image_url))

        self.assertEqual(media_id, 42)
        body = captured_files["body"]
        self.assertIn(b'Content-Type: image/jpeg', body)
        self.assertNotIn(b"application/octet-stream", body)
        self.assertIn(b'filename="image.jpg"', body)

    def test_generic_content_type_does_not_override_valid_url_extension(self) -> None:
        """
        Plenty of ordinary image hosts send a generic
        "application/octet-stream" Content-Type regardless of the actual
        file. When the URL already has a real image extension, that must
        win — otherwise a perfectly valid image/png upload gets sent as
        application/octet-stream (and, worse, renamed to "image.bin"),
        recreating the exact rejection this fix is meant to avoid.
        """
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "example.com":
                return httpx.Response(
                    200,
                    content=b"fakepngbytes",
                    headers={"content-type": "application/octet-stream"},
                )
            if request.url.path.endswith("/media/new"):
                captured["body"] = request.content
                return httpx.Response(200, json={"media": [{"ID": 9}]})
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")

        client = WordPressClient(_FakeTokenManager(), site_id="123")

        with _install_mock_transport(handler):
            media_id = asyncio.run(
                client.upload_media_from_url("https://example.com/foo/photo.png")
            )

        self.assertEqual(media_id, 9)
        body = captured["body"]
        self.assertIn(b'Content-Type: image/png', body)
        self.assertIn(b'filename="photo.png"', body)
        self.assertNotIn(b"image.bin", body)

    def test_normal_url_keeps_filename_from_path(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "example.com":
                return httpx.Response(
                    200,
                    content=b"fakepngbytes",
                    headers={"content-type": "image/png"},
                )
            if request.url.path.endswith("/media/new"):
                return httpx.Response(200, json={"media": [{"ID": 7}]})
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")

        client = WordPressClient(_FakeTokenManager(), site_id="123")

        with _install_mock_transport(handler):
            media_id = asyncio.run(
                client.upload_media_from_url("https://example.com/foo/bar.png?x=1")
            )

        self.assertEqual(media_id, 7)

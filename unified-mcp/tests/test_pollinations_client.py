from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from clients.pollinations_client import PollinationsAPIError, PollinationsImageClient


def _make_response(status_code=200, content=b"fake-image-bytes", content_type="image/jpeg"):
    request = httpx.Request("GET", "https://image.pollinations.ai/prompt/test")
    return httpx.Response(
        status_code=status_code,
        content=content,
        headers={"content-type": content_type},
        request=request,
    )


class _FakeAsyncClient:
    def __init__(self, response: httpx.Response) -> None:
        self._response = response
        self.captured_path = None
        self.captured_params = None

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc_info) -> bool:
        return False

    async def get(self, path, params=None, **kwargs):
        self.captured_path = path
        self.captured_params = params
        return self._response


class PollinationsImageClientTests(TestCase):
    def test_dimensions_default_square(self) -> None:
        self.assertEqual(PollinationsImageClient._dimensions("1:1"), (1024, 1024))

    def test_dimensions_invalid_aspect_ratio_raises(self) -> None:
        with self.assertRaises(PollinationsAPIError):
            PollinationsImageClient._dimensions("5:7")

    def test_generate_image_async_encodes_prompt_and_returns_bytes(self) -> None:
        client = PollinationsImageClient()
        fake_client = _FakeAsyncClient(_make_response())

        with patch("clients.pollinations_client.httpx.AsyncClient", return_value=fake_client):
            image_bytes, mime_type = asyncio.run(
                client._generate_image_async("a red apple, product photo", "16:9")
            )

        self.assertEqual(image_bytes, b"fake-image-bytes")
        self.assertEqual(mime_type, "image/jpeg")
        self.assertIn("a%20red%20apple", fake_client.captured_path)
        self.assertEqual(fake_client.captured_params["width"], 1344)
        self.assertEqual(fake_client.captured_params["height"], 768)
        self.assertEqual(fake_client.captured_params["nologo"], "true")

    def test_generate_image_async_strips_charset_from_mime_type(self) -> None:
        client = PollinationsImageClient()
        fake_client = _FakeAsyncClient(_make_response(content_type="image/jpeg; charset=utf-8"))

        with patch("clients.pollinations_client.httpx.AsyncClient", return_value=fake_client):
            _, mime_type = asyncio.run(client._generate_image_async("prompt", "1:1"))

        self.assertEqual(mime_type, "image/jpeg")

    def test_generate_image_async_raises_on_http_error(self) -> None:
        client = PollinationsImageClient()
        fake_client = _FakeAsyncClient(_make_response(status_code=503, content=b""))

        with patch("clients.pollinations_client.httpx.AsyncClient", return_value=fake_client):
            with self.assertRaises(httpx.HTTPStatusError):
                asyncio.run(client._generate_image_async("prompt", "1:1"))

    def test_generate_image_async_raises_on_empty_body(self) -> None:
        client = PollinationsImageClient()
        fake_client = _FakeAsyncClient(_make_response(status_code=200, content=b""))

        with patch("clients.pollinations_client.httpx.AsyncClient", return_value=fake_client):
            with self.assertRaises(PollinationsAPIError):
                asyncio.run(client._generate_image_async("prompt", "1:1"))

    def test_generate_image_async_rejects_invalid_aspect_ratio(self) -> None:
        client = PollinationsImageClient()
        with self.assertRaises(PollinationsAPIError):
            asyncio.run(client._generate_image_async("prompt", "invalid"))

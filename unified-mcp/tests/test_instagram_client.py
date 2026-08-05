from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from clients.instagram_client import InstagramClient


class _FakeTokenManager:
    async def get_valid_token(self) -> str:
        return "fake-token"


def _install_mock_transport(handler) -> None:
    """
    Patches clients.instagram_client's httpx.AsyncClient so every instance
    it creates uses the given MockTransport handler instead of hitting the
    real network — the module imports `httpx` directly and calls
    httpx.AsyncClient(...), so patching the attribute on the shared httpx
    module object intercepts every call site in that file.
    """
    real_async_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_async_client(*args, **kwargs)

    return patch("clients.instagram_client.httpx.AsyncClient", side_effect=factory)


class InstagramClientPublishPhotoTests(TestCase):
    def test_publish_photo_reports_progress_through_container_wait(self) -> None:
        calls = {"poll": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/media") and request.method == "POST":
                return httpx.Response(200, json={"id": "container-123"})
            if request.url.path.endswith("/container-123") and request.method == "GET":
                calls["poll"] += 1
                status = "IN_PROGRESS" if calls["poll"] < 3 else "FINISHED"
                return httpx.Response(200, json={"status_code": status})
            if request.url.path.endswith("/media_publish") and request.method == "POST":
                return httpx.Response(200, json={"id": "media-999"})
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")

        client = InstagramClient(_FakeTokenManager(), account_id="17800000000000000")

        progress_messages: list[str] = []

        async def on_progress(message: str) -> None:
            progress_messages.append(message)

        with _install_mock_transport(handler):
            # Speed up the test — no need to actually sleep between polls.
            with patch("clients.instagram_client.asyncio.sleep", return_value=None):
                media_id = asyncio.run(
                    client.publish_photo(
                        "https://example.com/img.jpg", "a caption", on_progress=on_progress
                    )
                )

        self.assertEqual(media_id, "media-999")
        self.assertEqual(calls["poll"], 3)
        # At least one progress update per non-finished poll, plus the
        # container-creation and publishing milestones.
        self.assertGreaterEqual(len(progress_messages), 4)
        self.assertIn("Creating the Instagram media container...", progress_messages)
        self.assertIn("Publishing...", progress_messages)
        self.assertTrue(any("attempt 1/" in m for m in progress_messages))
        self.assertTrue(any("attempt 2/" in m for m in progress_messages))

    def test_publish_photo_works_without_progress_callback(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/media") and request.method == "POST":
                return httpx.Response(200, json={"id": "container-1"})
            if request.url.path.endswith("/container-1") and request.method == "GET":
                return httpx.Response(200, json={"status_code": "FINISHED"})
            if request.url.path.endswith("/media_publish") and request.method == "POST":
                return httpx.Response(200, json={"id": "media-1"})
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")

        client = InstagramClient(_FakeTokenManager(), account_id="17800000000000000")

        with _install_mock_transport(handler):
            media_id = asyncio.run(client.publish_photo("https://example.com/img.jpg", "caption"))

        self.assertEqual(media_id, "media-1")

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from clients.threads_client import ThreadsClient
from tools.threads_tools import publish_post


class _FakeTokenManager:
    async def get_valid_token(self) -> str:
        return "fake-token"


def _install_mock_transport(handler):
    real_async_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_async_client(*args, **kwargs)

    return patch("clients.threads_client.httpx.AsyncClient", side_effect=factory)


class ThreadsClientPublishTests(TestCase):
    def test_text_post_waits_for_finished_container_before_publish(self) -> None:
        calls = {"poll": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/threads") and request.method == "POST":
                return httpx.Response(200, json={"id": "container-123"})
            if request.url.path.endswith("/container-123") and request.method == "GET":
                calls["poll"] += 1
                status = "IN_PROGRESS" if calls["poll"] == 1 else "FINISHED"
                return httpx.Response(200, json={"status": status})
            if request.url.path.endswith("/threads_publish") and request.method == "POST":
                return httpx.Response(200, json={"id": "thread-456"})
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")

        client = ThreadsClient(_FakeTokenManager(), user_id="user-123")

        with _install_mock_transport(handler):
            with patch("clients.threads_client.asyncio.sleep", return_value=None):
                thread_id = asyncio.run(client.publish_thread("texto sin imagen"))

        self.assertEqual(thread_id, "thread-456")
        self.assertEqual(calls["poll"], 2)

    def test_ambiguous_publish_400_reuses_the_same_finished_container(self) -> None:
        calls = {"publish": 0, "poll": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/threads") and request.method == "POST":
                return httpx.Response(200, json={"id": "container-123"})
            if request.url.path.endswith("/container-123") and request.method == "GET":
                calls["poll"] += 1
                return httpx.Response(200, json={"status": "FINISHED"})
            if request.url.path.endswith("/threads_publish") and request.method == "POST":
                calls["publish"] += 1
                if calls["publish"] == 1:
                    return httpx.Response(
                        400,
                        json={"error": {"message": "Container is not ready", "code": 190}},
                    )
                return httpx.Response(200, json={"id": "thread-456"})
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")

        client = ThreadsClient(_FakeTokenManager(), user_id="user-123")

        with _install_mock_transport(handler):
            with patch("clients.threads_client.asyncio.sleep", return_value=None):
                thread_id = asyncio.run(client.publish_thread("texto sin imagen"))

        self.assertEqual(thread_id, "thread-456")
        self.assertEqual(calls["publish"], 2)
        self.assertEqual(calls["poll"], 2)

    def test_repeated_ambiguous_publish_400_recovers_existing_matching_post(self) -> None:
        calls = {"publish": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/threads") and request.method == "POST":
                return httpx.Response(200, json={"id": "container-123"})
            if request.url.path.endswith("/container-123") and request.method == "GET":
                return httpx.Response(200, json={"status": "FINISHED"})
            if request.url.path.endswith("/threads_publish") and request.method == "POST":
                calls["publish"] += 1
                return httpx.Response(400, json={"error": {"message": "Ambiguous failure"}})
            if request.url.path.endswith("/user-123/threads") and request.method == "GET":
                return httpx.Response(
                    200,
                    json={
                        "data": [
                            {
                                "id": "thread-existing",
                                "text": "texto sin imagen",
                                "media_type": "TEXT",
                                "timestamp": "2026-09-09T15:00:00+0000",
                                "permalink": "https://www.threads.net/@dani/post/existing",
                            }
                        ]
                    },
                )
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")

        client = ThreadsClient(_FakeTokenManager(), user_id="user-123")

        with _install_mock_transport(handler):
            thread_id = asyncio.run(client.publish_thread("texto sin imagen"))

        self.assertEqual(thread_id, "thread-existing")
        self.assertEqual(calls["publish"], 2)

    def test_recovered_post_result_includes_the_existing_permalink(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/threads") and request.method == "POST":
                return httpx.Response(200, json={"id": "container-123"})
            if request.url.path.endswith("/container-123") and request.method == "GET":
                return httpx.Response(200, json={"status": "FINISHED"})
            if request.url.path.endswith("/threads_publish") and request.method == "POST":
                return httpx.Response(400, json={"error": {"message": "Ambiguous failure"}})
            if request.url.path.endswith("/user-123/threads") and request.method == "GET":
                return httpx.Response(
                    200,
                    json={
                        "data": [
                            {
                                "id": "thread-existing",
                                "text": "texto sin imagen",
                                "media_type": "TEXT",
                                "timestamp": "2026-09-09T15:00:00+0000",
                                "permalink": "https://www.threads.net/@dani/post/existing",
                            }
                        ]
                    },
                )
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")

        client = ThreadsClient(_FakeTokenManager(), user_id="user-123")

        with _install_mock_transport(handler):
            result = asyncio.run(publish_post(client, "texto sin imagen"))

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["thread_id"], "thread-existing")
        self.assertEqual(
            result["data"]["permalink"], "https://www.threads.net/@dani/post/existing"
        )

    def test_published_container_after_400_is_recovered_without_a_second_publish(self) -> None:
        calls = {"poll": 0, "publish": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/threads") and request.method == "POST":
                return httpx.Response(200, json={"id": "container-123"})
            if request.url.path.endswith("/container-123") and request.method == "GET":
                calls["poll"] += 1
                status = "FINISHED" if calls["poll"] == 1 else "PUBLISHED"
                return httpx.Response(200, json={"status": status})
            if request.url.path.endswith("/threads_publish") and request.method == "POST":
                calls["publish"] += 1
                return httpx.Response(400, json={"error": {"message": "Ambiguous failure"}})
            if request.url.path.endswith("/user-123/threads") and request.method == "GET":
                return httpx.Response(
                    200,
                    json={
                        "data": [
                            {
                                "id": "thread-existing",
                                "text": "texto sin imagen",
                                "media_type": "TEXT",
                                "timestamp": "2026-09-09T15:00:00+0000",
                                "permalink": "https://www.threads.net/@dani/post/existing",
                            }
                        ]
                    },
                )
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")

        client = ThreadsClient(_FakeTokenManager(), user_id="user-123")

        with _install_mock_transport(handler):
            with patch("clients.threads_client.asyncio.sleep", return_value=None):
                thread_id = asyncio.run(client.publish_thread("texto sin imagen"))

        self.assertEqual(thread_id, "thread-existing")
        self.assertEqual(calls["publish"], 1)

    def test_real_publish_error_includes_meta_error_payload(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/threads") and request.method == "POST":
                return httpx.Response(200, json={"id": "container-123"})
            if request.url.path.endswith("/container-123") and request.method == "GET":
                return httpx.Response(200, json={"status": "FINISHED"})
            if request.url.path.endswith("/threads_publish") and request.method == "POST":
                return httpx.Response(
                    400,
                    json={
                        "error": {
                            "message": "The container could not be published",
                            "code": 190,
                            "error_subcode": 12345,
                        }
                    },
                )
            if request.url.path.endswith("/user-123/threads") and request.method == "GET":
                return httpx.Response(200, json={"data": []})
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")

        client = ThreadsClient(_FakeTokenManager(), user_id="user-123")

        with _install_mock_transport(handler):
            result = asyncio.run(publish_post(client, "texto sin imagen"))

        self.assertFalse(result["success"])
        self.assertEqual(
            result["data"],
            {
                "meta_error": {
                    "error": {
                        "message": "The container could not be published",
                        "code": 190,
                        "error_subcode": 12345,
                    }
                }
            },
        )

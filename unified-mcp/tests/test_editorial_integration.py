from __future__ import annotations

import asyncio
import io
import sys
import threading
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from google.api_core.exceptions import NotFound, PreconditionFailed
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clients.gcs_queue_client import GCSQueueClient, GCSQueueError, QueueConflictError
from core import editorial as flow
from core.editorial_http import EditorialHTTP, reconcile
from tools.editorial_tools import EditorialService, download_image, guard_generic


class Bucket:
    def __init__(self):
        self.values = {}
        self.lock = threading.Lock()
        self.counter = 0

    def blob(self, name, generation=None):
        return Blob(self, name, generation)


class Blob:
    def __init__(self, bucket, name, generation=None):
        self.bucket, self.name, self.generation = bucket, name, generation

    def reload(self):
        with self.bucket.lock:
            if self.name not in self.bucket.values:
                raise NotFound("missing")
            self.generation = self.bucket.values[self.name][0]

    def upload_from_string(self, data, content_type=None, if_generation_match=None):
        with self.bucket.lock:
            previous = self.bucket.values.get(self.name, (0, b""))[0]
            if if_generation_match is not None and previous != if_generation_match:
                raise PreconditionFailed("CAS")
            self.bucket.counter += 1
            self.generation = self.bucket.counter
            self.bucket.values[self.name] = (self.generation, data.encode() if isinstance(data, str) else data)

    def download_as_bytes(self, if_generation_match=None):
        with self.bucket.lock:
            if self.name not in self.bucket.values:
                raise NotFound("missing")
            gen, data = self.bucket.values[self.name]
            if if_generation_match is not None and gen != if_generation_match:
                raise PreconditionFailed("CAS read")
            return data

    def download_as_text(self, **kwargs):
        return self.download_as_bytes(**kwargs).decode()


@pytest.fixture
def queue():
    client = GCSQueueClient("fake")
    bucket = Bucket()
    client._bucket = lambda: bucket
    return client


async def ready(queue, news_id="nvidia", approved=True):
    item = await queue.create_item(news_id, 1, "2026-10-08", "NVIDIA DGX Spark", None, "editor")
    service = EditorialService(queue, {"facebook": object(), "threads": object()}, "https://test.example")
    item = await service.prepare(news_id, item["version"], {"facebook": {"text": "NVIDIA"},
                                                          "threads": {"text": "NVIDIA"}}, "editor")
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "green").save(buf, "PNG")
    asset = await queue.store_asset(news_id, buf.getvalue(), "image/png", "https://chatgpt.com/s/nvidia")
    item = await queue.transition(news_id, item["version"],
                                 lambda current: flow.bind(current, current["editorial"]["generation_id"], asset, "visual"))
    if approved:
        item = await queue.transition(news_id, item["version"], lambda current: flow.approve(
            current, current["editorial"]["review_id"], "Dani", "Veo el ordenador NVIDIA DGX Spark",
            True, True, ["facebook", "threads"]))
    return service, item


def test_two_concurrent_agents_make_only_one_external_call(queue, monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", "test-key")
    async def scenario():
        service, _ = await ready(queue)
        calls = []
        async def dispatch(*args):
            calls.append(args)
            await asyncio.sleep(.02)
            return {"success": True, "data": {"post_id": "123"}}
        service._dispatch = dispatch
        results = await asyncio.gather(*(service.publish("nvidia", 1, 1, "facebook", "agent")
                                         for _ in range(2)), return_exceptions=True)
        assert len(calls) == 1
        assert sum(isinstance(r, Exception) for r in results) == 1
        assert (await queue.get_item("nvidia"))["canales"]["facebook"]["id"] == "123"
    asyncio.run(scenario())


def test_gcs_cas_rejects_same_generation_and_preserves_hash(queue):
    async def scenario():
        _, item = await ready(queue)
        await queue.transition("nvidia", item["version"], lambda i: i.update(notas="first"))
        with pytest.raises(QueueConflictError):
            await queue.transition("nvidia", item["version"], lambda i: i.update(notas="second"))
        assert (await queue.get_item("nvidia"))["notas"] == "first"
    asyncio.run(scenario())


def test_kolibri_bytes_cannot_be_reused_for_other_news(queue):
    async def scenario():
        await queue.store_asset("kolibri", b"same-real-bytes", "image/png", "https://chatgpt.com/s/a")
        with pytest.raises(GCSQueueError, match="otra noticia"):
            await queue.store_asset("nvidia", b"same-real-bytes", "image/png", "https://chatgpt.com/s/b")
    asyncio.run(scenario())


def test_changed_asset_bytes_block_publish(queue):
    async def scenario():
        service, item = await ready(queue)
        asset = item["editorial"]["image"]
        queue._bucket().values[asset["object_name"]] = (asset["generation"], b"wrong-image")
        service._dispatch = AsyncMock()
        with pytest.raises(GCSQueueError, match="Hash"):
            await service.publish("nvidia", 1, 1, "facebook", "agent")
        service._dispatch.assert_not_called()
    asyncio.run(scenario())


def test_updates_invalidate_approval_and_cannot_forge_publication(queue):
    async def scenario():
        service, item = await ready(queue)
        updated = await queue.update_item("nvidia", item["version"], "editor", contenido_markdown="Claude")
        assert updated["news_revision"] == 2
        assert updated["editorial"]["approval"] is None
        with pytest.raises(flow.EditorialError):
            await service.publish("nvidia", 1, 1, "facebook", "agent")
        with pytest.raises(GCSQueueError):
            await queue.update_item("nvidia", updated["version"], "agent", estado="publicada")
    asyncio.run(scenario())


def test_uncertain_blocks_edits_and_requires_human_reconciliation(queue, monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", "test-key")
    async def scenario():
        service, _ = await ready(queue)
        service._dispatch = AsyncMock(side_effect=TimeoutError())
        result = await service.publish("nvidia", 1, 1, "facebook", "agent")
        assert result["attempt"]["state"] == "uncertain"
        current = await queue.get_item("nvidia")
        with pytest.raises(flow.EditorialError):
            await queue.update_item("nvidia", current["version"], "agent", contenido_markdown="changed")
        with pytest.raises(flow.EditorialError):
            await service.publish("nvidia", 1, 1, "facebook", "agent")
        service._dispatch.assert_awaited_once()
        reconciled = await queue.transition("nvidia", current["version"], lambda i: reconcile(i, "facebook", "Dani",
            "Comprobado personalmente en Facebook, ID 123", True, "123", "https://facebook.com/123"))
        assert reconciled["canales"]["facebook"]["id"] == "123"
    asyncio.run(scenario())


def test_inaccessible_chatgpt_url_blocks_binding(queue):
    async def scenario():
        service, item = await ready(queue, approved=False)
        with patch("tools.editorial_tools.download_image", AsyncMock(side_effect=ValueError("403"))):
            with pytest.raises(ValueError):
                await service.bind("nvidia", item["version"], item["editorial"]["generation_id"],
                                   "https://chatgpt.com/s/unavailable", "agent")
        assert (await queue.get_item("nvidia"))["editorial"]["approval"] is None
    asyncio.run(scenario())


def test_ambiguous_today_and_published_news_stop(queue):
    async def scenario():
        service = EditorialService(queue)
        queue.list_items = AsyncMock(return_value=[{"id": "a", "fecha_prevista": "2026-10-08"},
                                                  {"id": "b", "fecha_prevista": "2026-10-08"}])
        with pytest.raises(flow.EditorialError, match="inequívoca"):
            await service.resolve("2026-10-08")
    asyncio.run(scenario())


def test_generic_unrelated_still_works_and_known_editorial_rejected(queue):
    async def scenario():
        _, item = await ready(queue)
        queue.list_items = AsyncMock(return_value=[{"id": "nvidia"}])
        await guard_generic(queue, True, "Una publicación personal ajena a la cola")
        await guard_generic(None, False, "anything")
        with pytest.raises(flow.EditorialError):
            await guard_generic(queue, False, "anything")
        with pytest.raises(flow.EditorialError):
            await guard_generic(queue, True, "NVIDIA")
        with pytest.raises(flow.EditorialError):
            await guard_generic(queue, True, "other", item["editorial"]["image"]["source_url"])
    asyncio.run(scenario())


def test_human_page_requires_visual_and_publication_confirmation(queue, monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", "test-key")
    async def scenario():
        service, item = await ready(queue, approved=False)
        link = (await service.review_link("nvidia"))["review_url"]
        app = EditorialHTTP(None, service)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://test.example") as client:
            assert (await client.get(link)).status_code == 200
            incomplete = await client.post(link, data={"version": item["version"], "actor": "Dani"})
            assert incomplete.status_code == 409
            assert (await service.queue.get_item("nvidia"))["editorial"]["approval"] is None
            accepted = await client.post(link, data={"version": item["version"], "actor": "Dani",
                "observation": "Veo el ordenador NVIDIA correspondiente a la noticia", "semantic_match": "yes",
                "authorized": "yes", "channel": "facebook"})
            assert accepted.status_code == 200
            assert (await client.post(link, data={"version": item["version"]})).status_code == 409
            assert (await client.get(service.asset_url(item))).content.startswith(b"\x89PNG")
    asyncio.run(scenario())


def test_local_or_untrusted_source_rejected_without_request():
    async def scenario():
        for url in ("http://127.0.0.1/image", "https://evil.example/image", "https://chatgpt.com@127.0.0.1/x"):
            with pytest.raises(flow.EditorialError):
                await download_image(url)
    asyncio.run(scenario())

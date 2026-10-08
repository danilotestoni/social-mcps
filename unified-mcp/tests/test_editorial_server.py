"""Exercise the real registered tools with no network or platform credentials."""
from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setenv("QUEUE_GCS_BUCKET", "fake-test-bucket")
    monkeypatch.setenv("ENABLE_FACEBOOK", "true")
    monkeypatch.setenv("ENABLE_IMAGE_GEN", "true")
    for platform in ("LINKEDIN", "INSTAGRAM", "THREADS", "WORDPRESS", "X", "FB_SHARE"):
        monkeypatch.setenv("ENABLE_" + platform, "false")
    module = importlib.import_module("server")
    return module


def test_tools_registered_without_approval_tool(server):
    async def scenario():
        tools = {t.name: t for t in await server.mcp.list_tools()}
        assert {"editorial_resolve", "editorial_prepare", "editorial_bind_image",
                "editorial_request_review", "editorial_publish"} <= tools.keys()
        assert not any("approve" in name for name in tools)
        assert "non_editorial" in tools["facebook_publish_post"].inputSchema["properties"]
    asyncio.run(scenario())


def test_legacy_tool_cannot_accidentally_publish_queue_content(server, monkeypatch):
    async def scenario():
        context = SimpleNamespace(request_context=SimpleNamespace(lifespan_context={"queue": object()}))
        monkeypatch.setattr(server.mcp, "get_context", lambda: context)
        publisher = AsyncMock()
        monkeypatch.setattr(server.fb, "publish_post", publisher)
        result = await server.facebook_publish_post("NVIDIA")
        assert result["success"] is False
        publisher.assert_not_awaited()
    asyncio.run(scenario())


def test_generic_non_editorial_and_dry_run_preserved(server, monkeypatch):
    async def scenario():
        queue = SimpleNamespace(list_items=AsyncMock(return_value=[]))
        context = SimpleNamespace(request_context=SimpleNamespace(lifespan_context={"queue": queue, "facebook": object()}),
                                  report_progress=AsyncMock())
        monkeypatch.setattr(server.mcp, "get_context", lambda: context)
        publisher = AsyncMock(return_value={"success": True})
        monkeypatch.setattr(server.fb, "publish_post", publisher)
        assert (await server.facebook_publish_post("Personal", non_editorial=True))["success"]
        assert (await server.facebook_publish_post("Preview", dry_run=True))["success"]
        assert publisher.await_count == 2
    asyncio.run(scenario())


def test_generation_without_news_binding_stops(server, monkeypatch):
    async def scenario():
        context = SimpleNamespace(request_context=SimpleNamespace(lifespan_context={"queue": object()}),
                                  report_progress=AsyncMock())
        monkeypatch.setattr(server.mcp, "get_context", lambda: context)
        generator = AsyncMock()
        monkeypatch.setattr(server.img, "generate_image", generator)
        assert (await server.generate_image("Claude"))["success"] is False
        generator.assert_not_awaited()
    asyncio.run(scenario())

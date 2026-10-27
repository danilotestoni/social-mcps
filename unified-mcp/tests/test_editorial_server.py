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
    monkeypatch.setenv("GCS_TEMP_BUCKET", "fake-temp-bucket")
    monkeypatch.setenv("ENABLE_FACEBOOK", "true")
    monkeypatch.setenv("ENABLE_IMAGE_GEN", "true")
    for platform in ("LINKEDIN", "INSTAGRAM", "THREADS", "WORDPRESS", "X", "FB_SHARE"):
        monkeypatch.setenv("ENABLE_" + platform, "false")
    module = importlib.import_module("server")
    return module


def test_http_transport_is_stateless_json_without_sse_streams(server, monkeypatch):
    import httpx

    monkeypatch.setenv("FACEBOOK_PAGE_ID", "page-1")
    monkeypatch.setattr(server, "_CONTEXT", None)
    headers = {"accept": "application/json, text/event-stream", "content-type": "application/json",
               "host": "localhost:8000"}

    async def scenario():
        app = server.NoStandaloneSSEMiddleware(server.mcp.streamable_http_app())
        async with server.mcp.session_manager.run():
            transport = httpx.ASGITransport(app)
            async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8000") as client:
                init = await client.post("/mcp", headers=headers, json={
                    "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                        "protocolVersion": "2025-03-26", "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1"}}})
                assert init.status_code == 200
                assert init.headers["content-type"].startswith("application/json")
                assert "mcp-session-id" not in init.headers
                context_after_first = server._CONTEXT
                for request_id in (2, 3):  # no session header needed between requests
                    call = await client.post("/mcp", headers=headers, json={
                        "jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                        "params": {"name": "list_enabled_platforms", "arguments": {}}})
                    assert call.status_code == 200 and call.json()["result"]["isError"] is False
                assert server._CONTEXT is context_after_first  # clients built once per process
                stream = await client.get("/mcp", headers={"accept": "text/event-stream", "host": "localhost:8000"})
                assert stream.status_code == 405  # no long-lived SSE stream to hold a Cloud Run slot

    asyncio.run(scenario())


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

def test_native_attachment_tool_descriptor(server):
    async def scenario():
        tools = {t.name: t for t in await server.mcp.list_tools()}
        tool = tools['upload_chat_image']
        assert tool.meta['openai/fileParams'] == ['file']
        schema = tool.inputSchema
        file = schema['properties']['file']
        if '$ref' in file:
            file = schema['$defs'][file['$ref'].split('/')[-1]]
        assert set(file['properties']) == {'download_url', 'file_id', 'mime_type', 'file_name'}
        assert set(file['required']) == {'download_url', 'file_id'}
        assert 'file' in schema['required']
    asyncio.run(scenario())

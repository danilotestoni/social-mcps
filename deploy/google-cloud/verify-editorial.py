"""Read-only live MCP smoke test. Never creates queue items or publishes content.

Reads a configured gateway URL/header from the user's Claude config without printing credentials.
Usage: python deploy/google-cloud/verify-editorial.py [--baseline] [--expected-revision REV]
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


def connection():
    config = json.loads((Path.home() / ".claude.json").read_text(encoding="utf-8"))
    def find(value):
        if isinstance(value, dict):
            for name, entry in value.get("mcpServers", {}).items():
                if isinstance(entry, dict) and entry.get("url") == "https://social-mcps.danilo-testoni.workers.dev/mcp":
                    return entry
            for child in value.values():
                result = find(child)
                if result:
                    return result
        return None
    entry = find(config)
    if not entry:
        raise RuntimeError("Gateway configuration not found; configure the existing MCP connection.")
    return entry["url"], entry["headers"]


def data(result):
    if result.isError:
        raise RuntimeError("MCP tool error")
    for content in result.content:
        if content.type == "text":
            return json.loads(content.text)
    raise RuntimeError("Missing structured response")


async def main(args):
    url, headers = connection()
    async with httpx.AsyncClient(timeout=30) as http:
        rejected = await http.post(url, json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert rejected.status_code == 401, "Unauthenticated gateway must reject"
        print("gateway_without_token: 401")
        probe = await http.get("https://unified-mcp.adasnova.com/editorial-review/invalid")
        assert probe.status_code == (401 if args.baseline else 409), "Unexpected review route status"
        print("public_review_invalid_token:", probe.status_code)
    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            names = {tool.name for tool in (await session.list_tools()).tools}
            print("authenticated_tools:", len(names))
            state = data(await session.call_tool("list_enabled_platforms", {}))
            print("serving_revision:", state.get("revision", "not exposed by baseline"))
            if args.expected_revision:
                assert state.get("revision") == args.expected_revision, "Gateway serving wrong revision"
            items = data(await session.call_tool("queue_list", {}))
            assert items["success"], "Queue unavailable"
            entries = items["data"]["items"]
            print("queue_readable_items:", len(entries))
            if entries:
                item = data(await session.call_tool("queue_get", {"id": entries[0]["id"]}))
                assert item["success"], "Queue item unreadable"
                print("queue_get: success")
            if not args.baseline:
                required = {"editorial_resolve", "editorial_prepare", "editorial_bind_image",
                            "editorial_request_review", "editorial_publish"}
                assert required <= names
                rejected = data(await session.call_tool("editorial_publish", {
                    "news_id": "smoke-nonexistent-editorial-validation-only", "news_revision": 1,
                    "image_revision": 1, "channel": "facebook", "actor": "readonly-smoke", "dry_run": True}))
                assert rejected["success"] is False
                print("missing_news_rejected: true")
                for summary in entries:
                    item = data(await session.call_tool("queue_get", {"id": summary["id"]}))["data"]
                    if not (item.get("editorial", {}).get("approval")):
                        rejected = data(await session.call_tool("editorial_publish", {
                            "news_id": item["id"], "news_revision": 1, "image_revision": 1,
                            "channel": "facebook", "actor": "readonly-smoke", "dry_run": True}))
                        assert rejected["success"] is False
                        print("existing_unapproved_or_terminal_news_rejected: true")
                        break
                else:
                    print("existing_unapproved_news: no suitable fixture; not mutated")
    print("read_only_smoke: PASS; no publication or queue mutation requested")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--expected-revision")
    asyncio.run(main(parser.parse_args()))

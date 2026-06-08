from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

import tools as tool_handlers
from api import ThreadsClient
from auth import AuthError, TokenManager

_ENV_PATH = Path(__file__).parent / ".env"


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[dict]:
    load_dotenv(_ENV_PATH)
    token_manager = TokenManager(_ENV_PATH)
    env = token_manager.load()
    client = ThreadsClient(token_manager, env["THREADS_USER_ID"])
    yield {"client": client}


mcp = FastMCP("threads", lifespan=lifespan)


@mcp.tool()
async def publish_post(
    text: str,
    image_url: str | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Publish a post to Threads.

    Args:
        text: The post text content (required).
        image_url: Optional public URL of an image to attach (JPEG recommended).
        dry_run: If True, validates and returns the payload without publishing.
    """
    ctx = mcp.get_context()
    return await tool_handlers.publish_post(
        ctx.request_context.lifespan_context["client"],
        text,
        image_url,
        dry_run,
    )


@mcp.tool()
async def get_last_posts(count: int = 10) -> dict:
    """
    Retrieve the most recent posts from the authenticated Threads account.

    Args:
        count: Number of posts to retrieve (default 10).
    """
    ctx = mcp.get_context()
    return await tool_handlers.get_last_posts(
        ctx.request_context.lifespan_context["client"],
        count,
    )


@mcp.tool()
async def delete_post(thread_id: str) -> dict:
    """
    Delete a Threads post by its ID.

    Args:
        thread_id: The ID of the thread to delete.
    """
    ctx = mcp.get_context()
    return await tool_handlers.delete_post(
        ctx.request_context.lifespan_context["client"],
        thread_id,
    )


@mcp.tool()
async def get_account_info() -> dict:
    """Return profile information for the authenticated Threads account."""
    ctx = mcp.get_context()
    return await tool_handlers.get_account_info(
        ctx.request_context.lifespan_context["client"],
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")

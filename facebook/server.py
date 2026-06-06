from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

import tools as tool_handlers
from api import FacebookClient
from auth import TokenManager

_ENV_PATH = Path(__file__).parent / ".env"


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[dict]:
    load_dotenv(_ENV_PATH)
    token_manager = TokenManager(_ENV_PATH)
    env = token_manager.load()
    client = FacebookClient(token_manager, env["FACEBOOK_PAGE_ID"])
    yield {"client": client}


mcp = FastMCP("facebook", lifespan=lifespan)


@mcp.tool()
async def publish_post(
    message: str,
    image_url: str | None = None,
    image_path: str | None = None,
) -> dict:
    """
    Publish a post to the Facebook Page.

    Args:
        message: Post text (already formatted for Facebook).
        image_url: Optional public URL of an image to attach.
        image_path: Optional local file path of an image to upload and attach.
                    Takes priority over image_url when both are provided.
    """
    ctx = mcp.get_context()
    return await tool_handlers.publish_post(
        ctx.request_context.lifespan_context["client"],
        message,
        image_url,
        image_path,
    )


@mcp.tool()
async def get_last_posts(count: int = 10) -> dict:
    """
    Retrieve the most recent posts from the Facebook Page.

    Args:
        count: Number of posts to retrieve (default 10).
    """
    ctx = mcp.get_context()
    return await tool_handlers.get_last_posts(
        ctx.request_context.lifespan_context["client"],
        count,
    )


@mcp.tool()
async def delete_post(post_id: str) -> dict:
    """
    Delete a Facebook Page post by its ID.

    Args:
        post_id: The ID of the post to delete (e.g. 123456789_987654321).
    """
    ctx = mcp.get_context()
    return await tool_handlers.delete_post(
        ctx.request_context.lifespan_context["client"],
        post_id,
    )


@mcp.tool()
async def get_account_info() -> dict:
    """Return information about the Facebook Page (name, category, fan count, followers)."""
    ctx = mcp.get_context()
    return await tool_handlers.get_account_info(
        ctx.request_context.lifespan_context["client"],
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")

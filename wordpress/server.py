from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

import tools as tool_handlers
from api import WordPressClient
from auth import TokenManager

_ENV_PATH = Path(__file__).parent / ".env"


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[dict]:
    load_dotenv(_ENV_PATH)
    token_manager = TokenManager(_ENV_PATH)
    env = token_manager.load()
    client = WordPressClient(token_manager, env["WP_SITE_ID"])
    yield {"client": client}


mcp = FastMCP("wordpress", lifespan=lifespan)


@mcp.tool()
async def publish_post(
    title: str,
    content: str,
    status: str = "publish",
    image_url: str | None = None,
    image_path: str | None = None,
) -> dict:
    """
    Create a post on the WordPress.com site.

    Args:
        title: Post title.
        content: Post body (HTML or plain text, already formatted for WordPress).
        status: Publication status — 'publish', 'draft', or 'private'. Default: 'publish'.
        image_url: Optional public URL of an image to set as the featured image.
        image_path: Optional local file path of an image to upload as the featured image.
                    Takes priority over image_url when both are provided.
    """
    ctx = mcp.get_context()
    return await tool_handlers.publish_post(
        ctx.request_context.lifespan_context["client"],
        title,
        content,
        status,
        image_url,
        image_path,
    )


@mcp.tool()
async def get_last_posts(count: int = 10) -> dict:
    """
    Retrieve the most recent posts from the WordPress.com site.

    Args:
        count: Number of posts to retrieve (default 10).
    """
    ctx = mcp.get_context()
    return await tool_handlers.get_last_posts(
        ctx.request_context.lifespan_context["client"],
        count,
    )


@mcp.tool()
async def delete_post(post_id: int) -> dict:
    """
    Delete a WordPress post by its numeric ID.

    Args:
        post_id: The numeric ID of the post to delete.
    """
    ctx = mcp.get_context()
    return await tool_handlers.delete_post(
        ctx.request_context.lifespan_context["client"],
        post_id,
    )


@mcp.tool()
async def get_account_info() -> dict:
    """Return information about the WordPress.com site (name, URL, description, post count)."""
    ctx = mcp.get_context()
    return await tool_handlers.get_account_info(
        ctx.request_context.lifespan_context["client"],
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")

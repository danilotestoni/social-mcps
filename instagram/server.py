from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

import tools as tool_handlers
from api import InstagramClient
from auth import TokenManager

_ENV_PATH = Path(__file__).parent / ".env"


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[dict]:
    load_dotenv(_ENV_PATH)
    token_manager = TokenManager(_ENV_PATH)
    env = token_manager.load()
    client = InstagramClient(token_manager, env["INSTAGRAM_ACCOUNT_ID"])
    yield {"client": client}


mcp = FastMCP("instagram", lifespan=lifespan)


@mcp.tool()
async def publish_post(
    caption: str,
    image_url: str | None = None,
    image_path: str | None = None,
) -> dict:
    """
    Publish a photo post to Instagram.

    Args:
        caption: Post caption (already formatted for Instagram, including hashtags).
        image_url: Public URL of the image to post. Required unless image_path is given.
        image_path: Local file path — note: Instagram Graph API requires a public URL,
                    so this will return an error. Use image_url instead.
    """
    ctx = mcp.get_context()
    return await tool_handlers.publish_post(
        ctx.request_context.lifespan_context["client"],
        caption,
        image_url,
        image_path,
    )


@mcp.tool()
async def get_last_posts(count: int = 10) -> dict:
    """
    Retrieve the most recent posts from the authenticated Instagram account.

    Args:
        count: Number of posts to retrieve (default 10).
    """
    ctx = mcp.get_context()
    return await tool_handlers.get_last_posts(
        ctx.request_context.lifespan_context["client"],
        count,
    )


@mcp.tool()
async def delete_post(media_id: str) -> dict:
    """
    Delete an Instagram post by its media ID.

    Args:
        media_id: The media ID of the post to delete.
    """
    ctx = mcp.get_context()
    return await tool_handlers.delete_post(
        ctx.request_context.lifespan_context["client"],
        media_id,
    )


@mcp.tool()
async def get_account_info() -> dict:
    """Return profile information for the authenticated Instagram Business account."""
    ctx = mcp.get_context()
    return await tool_handlers.get_account_info(
        ctx.request_context.lifespan_context["client"],
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")

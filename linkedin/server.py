from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

# Ensure imports resolve from this file's directory when launched from any cwd.
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

import tools as tool_handlers
from api import LinkedInClient
from auth import AuthError, TokenManager

_ENV_PATH = Path(__file__).parent / ".env"


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[dict]:
    load_dotenv(_ENV_PATH)
    token_manager = TokenManager(_ENV_PATH)
    client = LinkedInClient(token_manager)
    env = token_manager.load()
    yield {
        "client": client,
        "person_urn": env["LINKEDIN_PERSON_URN"],
    }


mcp = FastMCP("linkedin", lifespan=lifespan)


@mcp.tool()
async def publish_post(
    text: str,
    image_url: str | None = None,
    image_path: str | None = None,
) -> dict:
    """
    Publish a post to LinkedIn.

    Args:
        text: The post text content (already formatted for LinkedIn).
        image_url: Optional public URL of an image to attach.
        image_path: Optional local file path of an image to upload and attach.
                    Takes priority over image_url when both are provided.
    """
    ctx = mcp.get_context()
    return await tool_handlers.publish_post(
        ctx.request_context.lifespan_context["client"],
        ctx.request_context.lifespan_context["person_urn"],
        text,
        image_url,
        image_path,
    )


@mcp.tool()
async def get_last_posts(count: int = 10) -> dict:
    """
    Retrieve the most recent posts from the authenticated LinkedIn account.

    Args:
        count: Number of posts to retrieve (default 10).
    """
    ctx = mcp.get_context()
    return await tool_handlers.get_last_posts(
        ctx.request_context.lifespan_context["client"],
        ctx.request_context.lifespan_context["person_urn"],
        count,
    )


@mcp.tool()
async def delete_post(post_urn: str) -> dict:
    """
    Delete a LinkedIn post by its URN.

    Args:
        post_urn: The URN of the post to delete (e.g. urn:li:ugcPost:123456789).
    """
    ctx = mcp.get_context()
    return await tool_handlers.delete_post(
        ctx.request_context.lifespan_context["client"],
        post_urn,
    )


@mcp.tool()
async def get_account_info() -> dict:
    """Return profile information for the authenticated LinkedIn account."""
    ctx = mcp.get_context()
    return await tool_handlers.get_account_info(
        ctx.request_context.lifespan_context["client"],
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")

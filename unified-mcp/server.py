from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

# Ensure the package root is on sys.path when run directly
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import dotenv_values, load_dotenv
from mcp.server.fastmcp import FastMCP

from auth.facebook_auth import FacebookTokenManager
from auth.instagram_auth import InstagramTokenManager
from auth.linkedin_auth import LinkedInTokenManager
from auth.threads_auth import ThreadsTokenManager
from auth.wordpress_auth import WordPressTokenManager
from auth.x_auth import XCredentials
from clients.facebook_client import FacebookClient
from clients.instagram_client import InstagramClient
from clients.linkedin_client import LinkedInClient
from clients.threads_client import ThreadsClient
from clients.wordpress_client import WordPressClient
from clients.x_client import XClient
import tools.facebook_tools as fb
import tools.instagram_tools as ig
import tools.linkedin_tools as li
import tools.threads_tools as th
import tools.wordpress_tools as wp
import tools.x_tools as x_tools
import tools.fb_share_tools as fb_share

_ENV_PATH = Path(__file__).parent / ".env"


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[dict]:
    load_dotenv(_ENV_PATH)
    env = dotenv_values(_ENV_PATH)

    li_tm = LinkedInTokenManager(_ENV_PATH)
    fb_tm = FacebookTokenManager(_ENV_PATH)
    ig_tm = InstagramTokenManager(_ENV_PATH)
    th_tm = ThreadsTokenManager(_ENV_PATH)
    wp_tm = WordPressTokenManager(_ENV_PATH)
    x_creds = XCredentials(_ENV_PATH)

    x_env = x_creds.load()

    yield {
        "linkedin": LinkedInClient(li_tm),
        "facebook": FacebookClient(fb_tm, env["FACEBOOK_PAGE_ID"]),
        "instagram": InstagramClient(ig_tm, env["INSTAGRAM_ACCOUNT_ID"]),
        "threads": ThreadsClient(th_tm, env["THREADS_USER_ID"]),
        "wordpress": WordPressClient(wp_tm, env["WP_SITE_ID"]),
        "x": XClient(x_env["X_USERNAME"], x_env["X_PASSWORD"], x_env["X_EMAIL"]),
        "linkedin_person_urn": env["LINKEDIN_PERSON_URN"],
    }


mcp = FastMCP("social-unified", lifespan=lifespan)


# ── LinkedIn ─────────────────────────────────────────────────────────────────

@mcp.tool()
async def linkedin_publish_post(
    text: str,
    image_url: str | None = None,
    image_path: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Publish a post to LinkedIn. Supports plain text or image (URL or local path)."""
    ctx = mcp.get_context()
    lc = ctx.request_context.lifespan_context
    return await li.publish_post(lc["linkedin"], lc["linkedin_person_urn"], text, image_url, image_path, dry_run)


@mcp.tool()
async def linkedin_get_last_posts(count: int = 10) -> dict:
    """Retrieve the most recent LinkedIn posts from the authenticated account."""
    ctx = mcp.get_context()
    lc = ctx.request_context.lifespan_context
    return await li.get_last_posts(lc["linkedin"], lc["linkedin_person_urn"], count)


@mcp.tool()
async def linkedin_delete_post(post_urn: str) -> dict:
    """Delete a LinkedIn post by its URN."""
    ctx = mcp.get_context()
    return await li.delete_post(ctx.request_context.lifespan_context["linkedin"], post_urn)


@mcp.tool()
async def linkedin_get_account_info() -> dict:
    """Return profile information for the authenticated LinkedIn account."""
    ctx = mcp.get_context()
    return await li.get_account_info(ctx.request_context.lifespan_context["linkedin"])


# ── Facebook ──────────────────────────────────────────────────────────────────

@mcp.tool()
async def facebook_publish_post(
    message: str,
    image_url: str | None = None,
    image_path: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Publish a post to the Facebook Page. Supports text, image URL, or local image file."""
    ctx = mcp.get_context()
    return await fb.publish_post(ctx.request_context.lifespan_context["facebook"], message, image_url, image_path, dry_run)


@mcp.tool()
async def facebook_get_last_posts(count: int = 10) -> dict:
    """Retrieve the most recent posts from the Facebook Page."""
    ctx = mcp.get_context()
    return await fb.get_last_posts(ctx.request_context.lifespan_context["facebook"], count)


@mcp.tool()
async def facebook_delete_post(post_id: str) -> dict:
    """Delete a Facebook Page post by its ID."""
    ctx = mcp.get_context()
    return await fb.delete_post(ctx.request_context.lifespan_context["facebook"], post_id)


@mcp.tool()
async def facebook_get_account_info() -> dict:
    """Return information about the authenticated Facebook Page."""
    ctx = mcp.get_context()
    return await fb.get_account_info(ctx.request_context.lifespan_context["facebook"])


# ── Instagram ─────────────────────────────────────────────────────────────────

@mcp.tool()
async def instagram_publish_post(
    caption: str,
    image_url: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Publish a photo post to Instagram. Requires a public image URL."""
    ctx = mcp.get_context()
    return await ig.publish_post(ctx.request_context.lifespan_context["instagram"], caption, image_url, None, dry_run)


@mcp.tool()
async def instagram_get_last_posts(count: int = 10) -> dict:
    """Retrieve the most recent posts from the authenticated Instagram account."""
    ctx = mcp.get_context()
    return await ig.get_last_posts(ctx.request_context.lifespan_context["instagram"], count)


@mcp.tool()
async def instagram_delete_post(media_id: str) -> dict:
    """Delete an Instagram post by its media ID."""
    ctx = mcp.get_context()
    return await ig.delete_post(ctx.request_context.lifespan_context["instagram"], media_id)


@mcp.tool()
async def instagram_get_account_info() -> dict:
    """Return profile information for the authenticated Instagram Business account."""
    ctx = mcp.get_context()
    return await ig.get_account_info(ctx.request_context.lifespan_context["instagram"])


# ── Threads ───────────────────────────────────────────────────────────────────

@mcp.tool()
async def threads_publish_post(
    text: str,
    image_url: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Publish a thread to Threads. Optionally include a public image URL."""
    ctx = mcp.get_context()
    return await th.publish_post(ctx.request_context.lifespan_context["threads"], text, image_url, dry_run)


@mcp.tool()
async def threads_get_last_posts(count: int = 10) -> dict:
    """Retrieve the most recent threads from the authenticated account."""
    ctx = mcp.get_context()
    return await th.get_last_posts(ctx.request_context.lifespan_context["threads"], count)


@mcp.tool()
async def threads_delete_post(thread_id: str) -> dict:
    """Delete a thread by its ID."""
    ctx = mcp.get_context()
    return await th.delete_post(ctx.request_context.lifespan_context["threads"], thread_id)


@mcp.tool()
async def threads_get_account_info() -> dict:
    """Return profile information for the authenticated Threads account."""
    ctx = mcp.get_context()
    return await th.get_account_info(ctx.request_context.lifespan_context["threads"])


# ── WordPress ─────────────────────────────────────────────────────────────────

@mcp.tool()
async def wordpress_publish_post(
    title: str,
    content: str,
    status: str = "publish",
    image_url: str | None = None,
    image_path: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Publish a post to WordPress.com. Optionally include a featured image."""
    ctx = mcp.get_context()
    return await wp.publish_post(ctx.request_context.lifespan_context["wordpress"], title, content, status, image_url, image_path, dry_run)


@mcp.tool()
async def wordpress_get_last_posts(count: int = 10) -> dict:
    """Retrieve the most recent posts from the WordPress.com site."""
    ctx = mcp.get_context()
    return await wp.get_last_posts(ctx.request_context.lifespan_context["wordpress"], count)


@mcp.tool()
async def wordpress_delete_post(post_id: int) -> dict:
    """Delete a WordPress post by its numeric ID."""
    ctx = mcp.get_context()
    return await wp.delete_post(ctx.request_context.lifespan_context["wordpress"], post_id)


@mcp.tool()
async def wordpress_get_account_info() -> dict:
    """Return information about the authenticated WordPress.com site."""
    ctx = mcp.get_context()
    return await wp.get_account_info(ctx.request_context.lifespan_context["wordpress"])


# ── X (Twitter) ───────────────────────────────────────────────────────────────

@mcp.tool()
async def x_post_tweet(text: str, dry_run: bool = False) -> dict:
    """
    Post a tweet to X (Twitter) via Twikit (no official API key required).
    If Twikit fails, returns a notifier payload instructing to use social-automation-mcp locally.
    Maximum 280 characters.
    """
    ctx = mcp.get_context()
    return await x_tools.post_to_x(ctx.request_context.lifespan_context["x"], text, dry_run)


# ── Facebook Personal Feed ────────────────────────────────────────────────────

@mcp.tool()
async def facebook_share_to_personal_feed(
    post_url: str,
    message: str | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Share a Facebook Page post to the personal feed.
    Requires Playwright (not available on Render) — always returns a notifier payload
    instructing to invoke share_to_fb_feed from social-automation-mcp locally.
    """
    return await fb_share.share_to_fb_feed(post_url, message, dry_run)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)

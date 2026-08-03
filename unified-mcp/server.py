from __future__ import annotations

import hmac
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

# Ensure the package root is on sys.path when run directly
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

_ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(_ENV_PATH)

from core.config import env_values  # noqa: E402
from core.logger import get_logger  # noqa: E402

_logger = get_logger(__name__)

_TRUE_VALUES = ("1", "true", "yes", "on")


def _enabled(platform: str) -> bool:
    """
    Platform toggle via ENABLE_<PLATFORM> (env var or .env). Defaults to
    enabled. Disabled platforms register no tools and load no credentials.
    """
    raw = env_values(_ENV_PATH).get(f"ENABLE_{platform}", "true")
    return (raw or "true").strip().lower() in _TRUE_VALUES


_ENABLED = {
    name: _enabled(name)
    for name in ("LINKEDIN", "FACEBOOK", "INSTAGRAM", "THREADS", "WORDPRESS", "X", "FB_SHARE")
}


def _image_gen_enabled() -> bool:
    """
    IMAGE_GEN defaults to enabled: all three providers (Cloudflare Workers
    AI, Hugging Face FLUX.1-schnell, Pollinations.ai) are free and need no
    credentials, so generate_image always has a working provider.
    An explicit ENABLE_IMAGE_GEN=true/false always wins.
    """
    values = env_values(_ENV_PATH)
    raw = values.get("ENABLE_IMAGE_GEN")
    if raw is not None and raw.strip():
        return raw.strip().lower() in _TRUE_VALUES
    return True


_ENABLED["IMAGE_GEN"] = _image_gen_enabled()
_logger.info(
    "Enabled platforms: %s",
    ", ".join(k for k, v in _ENABLED.items() if v) or "none",
)


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[dict]:
    env = env_values(_ENV_PATH)
    context: dict = {}

    if _ENABLED["LINKEDIN"]:
        from auth.linkedin_auth import LinkedInTokenManager
        from clients.linkedin_client import LinkedInClient

        context["linkedin"] = LinkedInClient(LinkedInTokenManager(_ENV_PATH))
        context["linkedin_person_urn"] = env["LINKEDIN_PERSON_URN"]

    if _ENABLED["FACEBOOK"]:
        from auth.facebook_auth import FacebookTokenManager
        from clients.facebook_client import FacebookClient

        context["facebook"] = FacebookClient(
            FacebookTokenManager(_ENV_PATH), env["FACEBOOK_PAGE_ID"]
        )

    if _ENABLED["INSTAGRAM"]:
        from auth.instagram_auth import InstagramTokenManager
        from clients.instagram_client import InstagramClient

        context["instagram"] = InstagramClient(
            InstagramTokenManager(_ENV_PATH), env["INSTAGRAM_ACCOUNT_ID"]
        )

    if _ENABLED["THREADS"]:
        from auth.threads_auth import ThreadsTokenManager
        from clients.threads_client import ThreadsClient

        context["threads"] = ThreadsClient(
            ThreadsTokenManager(_ENV_PATH), env["THREADS_USER_ID"]
        )

    if _ENABLED["WORDPRESS"]:
        from auth.wordpress_auth import WordPressTokenManager
        from clients.wordpress_client import WordPressClient

        context["wordpress"] = WordPressClient(
            WordPressTokenManager(_ENV_PATH), env["WP_SITE_ID"]
        )

    if _ENABLED["X"]:
        from auth.x_auth import XCredentials
        from clients.x_client import XClient

        x_env = XCredentials(_ENV_PATH).load()
        context["x"] = XClient(
            x_env["X_USERNAME"], x_env["X_PASSWORD"], x_env["X_EMAIL"]
        )

    if _ENABLED["IMAGE_GEN"]:
        from clients.cloudflare_worker_image_client import CloudflareWorkerImageClient
        from clients.huggingface_flux_client import HuggingFaceFluxClient
        from clients.pollinations_client import PollinationsImageClient

        # Free-tier fallback chain, all keyless: Cloudflare Workers AI first
        # (no per-image cost to us), then the Hugging Face FLUX.1-schnell
        # Space, then Pollinations.ai as the last resort.
        context["cloudflare_image"] = CloudflareWorkerImageClient(
            base_url=env.get(
                "CLOUDFLARE_IMAGE_WORKER_URL",
                "https://image-burn.danilo-testoni.workers.dev",
            )
        )
        context["huggingface_image"] = HuggingFaceFluxClient()
        context["pollinations"] = PollinationsImageClient()

    yield context


def _transport_security() -> TransportSecuritySettings:
    """
    DNS-rebinding protection. Defaults to loopback-only, matching FastMCP's
    own default. Set MCP_ALLOWED_HOSTS (comma-separated Host header values,
    e.g. the Cloud Run service domain) to allow the server to be reached
    through its public hostname; access is still gated by MCP_AUTH_TOKEN
    via BearerAuthMiddleware below.
    """
    hosts = [h.strip() for h in os.getenv("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
    if not hosts:
        return TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"],
            allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"],
        )
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=[],
    )


mcp = FastMCP("social-unified", lifespan=lifespan, transport_security=_transport_security())


@mcp.tool()
def list_enabled_platforms() -> dict:
    """
    Lists which social platforms/tools are active on this deployment and
    which are disabled. Configured at deploy time via ENABLE_<PLATFORM>
    environment variables (LINKEDIN, FACEBOOK, INSTAGRAM, THREADS,
    WORDPRESS, X, FB_SHARE, IMAGE_GEN) — call this before publishing
    anything if you're unsure which networks a request could reach.
    Disabled platforms register no tools at all, so this only reports the
    current state; it does not change it.
    """
    return {
        "enabled": sorted(k for k, v in _ENABLED.items() if v),
        "disabled": sorted(k for k, v in _ENABLED.items() if not v),
    }


# ── LinkedIn ─────────────────────────────────────────────────────────────────

if _ENABLED["LINKEDIN"]:
    import tools.linkedin_tools as li

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

if _ENABLED["FACEBOOK"]:
    import tools.facebook_tools as fb

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

if _ENABLED["INSTAGRAM"]:
    import tools.instagram_tools as ig

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

if _ENABLED["THREADS"]:
    import tools.threads_tools as th

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

if _ENABLED["WORDPRESS"]:
    import tools.wordpress_tools as wp

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

if _ENABLED["X"]:
    import tools.x_tools as x_tools

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

if _ENABLED["FB_SHARE"]:
    import tools.fb_share_tools as fb_share

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


# ── Image generation ──────────────────────────────────────────────────────────

if _ENABLED["IMAGE_GEN"]:
    import tools.image_tools as img

    @mcp.tool()
    async def generate_image(
        prompt: str,
        aspect_ratio: str = "1:1",
        upload_to_wordpress: bool = False,
        dry_run: bool = False,
    ):
        """
        Generate an image from an English text prompt. Tries providers in
        order — Cloudflare Workers AI (FLUX-1-schnell) first, then the
        Hugging Face FLUX.1-schnell Space, then Pollinations.ai — all free,
        so this tool always has a working provider.
        Shows the generated image inline in the chat. Set upload_to_wordpress
        to true only when the image needs a public media URL for a follow-up
        cross-post (e.g. Instagram/Threads, which require image_url rather
        than a local file) — a plain "generate an image" request should NOT
        touch WordPress.
        Aspect ratios: 1:1, 2:3, 3:2, 3:4, 4:3, 4:5, 5:4, 9:16, 16:9, 21:9
        (Cloudflare/Hugging Face currently ignore this and always produce a
        square image; Pollinations honors it).
        The prompt can include short text to render inside the image.
        """
        ctx = mcp.get_context()
        lc = ctx.request_context.lifespan_context
        data, preview_content = await img.generate_image(
            prompt,
            aspect_ratio,
            cloudflare_client=lc.get("cloudflare_image"),
            huggingface_client=lc.get("huggingface_image"),
            pollinations_client=lc.get("pollinations"),
            wordpress_client=lc.get("wordpress"),
            upload_to_wordpress=upload_to_wordpress,
            dry_run=dry_run,
        )

        if preview_content is None:
            return data
        return [data, preview_content]


# ── HTTP auth (public deployments) ────────────────────────────────────────────

class BearerAuthMiddleware:
    """
    Pure-ASGI bearer-token check for public HTTP deployments. Rejects any
    request whose Authorization header does not match MCP_AUTH_TOKEN.
    Implemented as raw ASGI (not BaseHTTPMiddleware) so SSE streaming
    responses pass through untouched.
    """

    def __init__(self, app, token: str) -> None:
        self._app = app
        self._expected = f"Bearer {token}"

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = {
                k.decode("latin-1").lower(): v.decode("latin-1")
                for k, v in scope.get("headers", [])
            }
            provided = headers.get("authorization", "")
            if not hmac.compare_digest(provided, self._expected):
                await send({
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"www-authenticate", b"Bearer"),
                    ],
                })
                await send({
                    "type": "http.response.body",
                    "body": b'{"error":"unauthorized"}',
                })
                return
        await self._app(scope, receive, send)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio").strip().lower()
    if transport == "stdio":
        # Local use: launched by an MCP client (claude_desktop_config.json).
        mcp.run(transport="stdio")
    else:
        # Remote use (Render): streamable-http behind optional bearer auth.
        import uvicorn

        app = mcp.streamable_http_app()
        auth_token = os.getenv("MCP_AUTH_TOKEN", "").strip()
        if auth_token:
            app = BearerAuthMiddleware(app, auth_token)
        else:
            _logger.warning(
                "MCP_AUTH_TOKEN is not set — the HTTP endpoint is UNAUTHENTICATED. "
                "Anyone who discovers the URL can use these tools."
            )
        port = int(os.getenv("PORT", "8000"))
        uvicorn.run(app, host="0.0.0.0", port=port)

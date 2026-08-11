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


def _gcs_temp_storage_enabled() -> bool:
    """
    Enabled only when GCS_TEMP_BUCKET is set — there's no free/keyless
    fallback here (unlike IMAGE_GEN), so upload_temp_image/delete_temp_image
    simply don't get registered until a bucket is configured.
    """
    return bool((env_values(_ENV_PATH).get("GCS_TEMP_BUCKET") or "").strip())


_ENABLED["GCS_TEMP_STORAGE"] = _gcs_temp_storage_enabled()


def _queue_enabled() -> bool:
    """
    Enabled only when QUEUE_GCS_BUCKET is set — the shared content queue is
    opt-in infrastructure, not part of every deployment.
    """
    return bool((env_values(_ENV_PATH).get("QUEUE_GCS_BUCKET") or "").strip())


_ENABLED["QUEUE"] = _queue_enabled()
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

    if _ENABLED["GCS_TEMP_STORAGE"]:
        from clients.gcs_temp_storage_client import GCSTempStorageClient

        context["gcs_temp_storage"] = GCSTempStorageClient(
            env["GCS_TEMP_BUCKET"], public_base_url=env.get("PUBLIC_BASE_URL", "")
        )

    if _ENABLED["QUEUE"]:
        from clients.gcs_queue_client import GCSQueueClient

        context["queue"] = GCSQueueClient(env["QUEUE_GCS_BUCKET"])

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
        if not dry_run:
            await ctx.report_progress(0, 100, "Publishing to LinkedIn...")
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
        if not dry_run:
            await ctx.report_progress(0, 100, "Publishing to Facebook...")
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
        if dry_run:
            return await ig.publish_post(
                ctx.request_context.lifespan_context["instagram"], caption, image_url, None, dry_run
            )

        await ctx.report_progress(0, 100, "Publishing to Instagram...")
        _step = {"n": 0}

        async def _on_progress(message: str) -> None:
            _step["n"] += 1
            await ctx.report_progress(min(_step["n"] * 5, 95), 100, message)

        return await ig.publish_post(
            ctx.request_context.lifespan_context["instagram"],
            caption,
            image_url,
            None,
            dry_run,
            on_progress=_on_progress,
        )

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
        if not dry_run:
            await ctx.report_progress(0, 100, "Publishing to Threads...")
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
        if not dry_run:
            await ctx.report_progress(0, 100, "Publishing to WordPress...")
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
        if not dry_run:
            await ctx.report_progress(0, 100, "Generating image...")
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


# ── Temporary storage (GCS) — for images NOT generated by generate_image ──────

if _ENABLED["GCS_TEMP_STORAGE"]:
    import tools.gcs_temp_storage_tools as gcs_tmp

    @mcp.tool()
    async def upload_temp_image(
        image_base64: str | None = None,
        image_url: str | None = None,
        mime_type: str = "image/jpeg",
        filename: str | None = None,
        ttl_seconds: int = 900,
        auto_optimize: bool = True,
    ) -> dict:
        """
        Uploads an image (e.g. one attached or created directly in the
        chat — NOT necessarily from generate_image) to a private,
        temporary Cloud Storage location and returns a short-lived public
        URL usable as image_url for Instagram, Threads, or any other
        publishing tool that requires a public URL rather than a local
        file.
        Provide exactly ONE of:
          - image_url: a URL the server fetches directly. STRONGLY
            PREFERRED whenever the image is already reachable at a URL —
            it avoids transporting any image bytes through the tool call
            at all, which is the fragile part. If you're in ChatGPT and
            the image (attached OR generated natively) has no URL you
            know of, use its "Share" feature on that image/message and
            pass the resulting chatgpt.com/s/... link here directly — this
            tool detects the HTML share page and automatically extracts
            and fetches the real public image URL embedded in it (a
            chatgpt.com/backend-api/estuary/public_content/... link,
            confirmed genuinely public with no auth needed). No base64,
            no chunking, no manual link-hunting required.
          - image_base64: a plain base64 string or a data URI
            (data:image/png;base64,...). LAST RESORT — only when no URL
            exists at all (not even a Share link) for a genuinely local
            file. Keep the underlying FILE under ~50KB if at all possible;
            if that's still not reliable, use
            start_temp_image_upload/upload_temp_image_chunk/
            finish_temp_image_upload instead of one big call — but note
            that in practice even chunking has been observed stalling for
            minutes inside ChatGPT's own sandbox while it prepares the
            base64 chunks, before any call reaches this server at all.
            Exhaust the image_url/Share-link route first.
        auto_optimize (default true): if the received image is large
        (>1.5MB or a large resolution), it's automatically downscaled and
        re-encoded as JPEG before upload — keeps things fast and within
        every platform's limits. Set to false to upload the exact original
        bytes untouched.
        Call delete_temp_image once you're done publishing — don't rely
        on ttl_seconds/the bucket's cleanup rule for prompt deletion,
        those are just safety nets. ttl_seconds defaults to 900 (15 min).
        """
        ctx = mcp.get_context()
        await ctx.report_progress(0, 100, "Uploading image to temporary storage...")
        lc = ctx.request_context.lifespan_context
        return await gcs_tmp.upload_temp_image(
            lc["gcs_temp_storage"],
            image_base64,
            image_url,
            mime_type,
            filename,
            ttl_seconds,
            auto_optimize,
        )

    @mcp.tool()
    async def delete_temp_image(object_name: str) -> dict:
        """
        Deletes a temporary image previously uploaded via upload_temp_image
        (use the object_name it returned). Safe to call even if it was
        already deleted or expired via the bucket's lifecycle rule.
        """
        ctx = mcp.get_context()
        lc = ctx.request_context.lifespan_context
        return await gcs_tmp.delete_temp_image(lc["gcs_temp_storage"], object_name)

    @mcp.tool()
    async def start_temp_image_upload() -> dict:
        """
        Starts a CHUNKED upload for an image, for the case where the file
        only exists locally to you (e.g. a chat attachment) with no
        reachable URL, AND a single upload_temp_image(image_base64=...)
        call has failed or is expected to fail — some MCP clients corrupt
        or truncate large base64 strings embedded in one tool call.
        Returns an upload_id. Then:
          1. Split the file's base64 into small chunks — ~32KB of RAW
             bytes per chunk (so ~44KB of base64 text) is a safe size.
          2. Call upload_temp_image_chunk once per chunk, in order,
             starting chunk_index at 0.
          3. Call finish_temp_image_upload with the total chunk count to
             assemble everything and get the same result shape as
             upload_temp_image (signed_url/public_url, object_name, etc.).
        Prefer plain upload_temp_image (image_url or a single small
        image_base64) when possible — only use this chunked flow when
        those don't work.
        """
        ctx = mcp.get_context()
        lc = ctx.request_context.lifespan_context
        return await gcs_tmp.start_temp_image_upload(lc["gcs_temp_storage"])

    @mcp.tool()
    async def upload_temp_image_chunk(
        upload_id: str,
        chunk_index: int,
        chunk_base64: str,
    ) -> dict:
        """
        Uploads one chunk of a file started with start_temp_image_upload.
        chunk_index is 0-based and chunks must be uploaded in order
        starting from 0 (finish_temp_image_upload reassembles them by
        index). Keep each chunk small — around 32KB of raw bytes
        (~44KB of base64 text) per call.
        """
        ctx = mcp.get_context()
        await ctx.report_progress(0, 100, f"Uploading chunk {chunk_index}...")
        lc = ctx.request_context.lifespan_context
        return await gcs_tmp.upload_temp_image_chunk(
            lc["gcs_temp_storage"], upload_id, chunk_index, chunk_base64
        )

    @mcp.tool()
    async def finish_temp_image_upload(
        upload_id: str,
        total_chunks: int,
        mime_type: str = "image/jpeg",
        filename: str | None = None,
        ttl_seconds: int = 900,
        auto_optimize: bool = True,
    ) -> dict:
        """
        Assembles all chunks uploaded via upload_temp_image_chunk (indices
        0..total_chunks-1 must all have been uploaded) into the final
        image and uploads it to temporary storage — same result shape as
        upload_temp_image (signed_url/public_url, object_name, mime_type,
        size_bytes, expires_at). auto_optimize behaves the same as in
        upload_temp_image. The staged chunks are deleted after this
        succeeds.
        """
        ctx = mcp.get_context()
        await ctx.report_progress(0, 100, "Assembling uploaded chunks...")
        lc = ctx.request_context.lifespan_context
        return await gcs_tmp.finish_temp_image_upload(
            lc["gcs_temp_storage"],
            upload_id,
            total_chunks,
            mime_type,
            filename,
            ttl_seconds,
            auto_optimize,
        )


# ── Content queue (shared pipeline state, GCS-backed) ──────────────────────────
#
# Shared operational state for the weekly news pipeline: both Claude
# (this server, local stdio) and ChatGPT (this same server, remote, via the
# Social-Mcps-Cloud connector over Cloud Run) call these tools against the
# ONE bucket, so there is a single source of truth for the queue instead of
# two local copies that inevitably diverge. See core/models.py for the
# QUEUE_ESTADOS/QUEUE_CANALES contract and clients/gcs_queue_client.py for
# the optimistic-concurrency (expected_version) design.

if _ENABLED["QUEUE"]:
    import tools.queue_tools as queue

    @mcp.tool()
    async def queue_list(estado: str | None = None) -> dict:
        """
        Lists queue items (metadata only, not full content), ordered by
        `orden` ascending. Pass estado to filter — one of: pendiente,
        preparada, publicada, descartada, error. Omit for all items.
        Each item includes its current `version` — pass that exact value
        as expected_version to queue_update/queue_mark_published/
        queue_mark_discarded to avoid clobbering a concurrent edit.
        """
        ctx = mcp.get_context()
        return await queue.queue_list(ctx.request_context.lifespan_context["queue"], estado)

    @mcp.tool()
    async def queue_get(id: str) -> dict:
        """
        Returns the full frontmatter (estado, orden, fechas, imagen,
        resultados por canal, version...) plus the complete Markdown
        content (analysis + per-platform copy + image prompt) for one
        queue item by id.
        """
        ctx = mcp.get_context()
        return await queue.queue_get(ctx.request_context.lifespan_context["queue"], id)

    @mcp.tool()
    async def queue_create(
        id: str,
        orden: int,
        fecha_prevista: str,
        contenido_markdown: str,
        updated_by: str,
        imagen: dict | None = None,
    ) -> dict:
        """
        Creates a new queue item with estado=pendiente. Fails if id already
        exists (ids must be unique — recommended format:
        YYYY-MM-DD-noticia-N, matching the weekly scan's Monday date and
        the item's priority order).
        contenido_markdown is the self-contained body: title, source,
        analysis, and the finished copy for every social platform, plus
        the image prompt — exactly what a daily publish run needs, with no
        dependency on the weekly report.
        imagen (optional) is {proveedor, url, canva_id} — all null if the
        image isn't generated yet.
        updated_by identifies the calling agent (e.g. "claude" or
        "chatgpt") for the audit trail.
        """
        ctx = mcp.get_context()
        return await queue.queue_create(
            ctx.request_context.lifespan_context["queue"],
            id, orden, fecha_prevista, contenido_markdown, updated_by, imagen,
        )

    @mcp.tool()
    async def queue_update(
        id: str,
        expected_version: int,
        updated_by: str,
        estado: str | None = None,
        orden: int | None = None,
        fecha_prevista: str | None = None,
        contenido_markdown: str | None = None,
        imagen: dict | None = None,
        notas: str | None = None,
    ) -> dict:
        """
        Partial update of a queue item — only pass the fields that changed
        (text correction, new image, reordering, moving to estado=
        preparada, etc.). expected_version MUST be the `version` you most
        recently got from queue_get/queue_list for this id: if another
        agent wrote to it in the meantime, this call fails with a conflict
        error instead of silently overwriting their change — re-read with
        queue_get and retry. For marking a publish result or a discard,
        use queue_mark_published / queue_mark_discarded instead (they set
        several related fields atomically and correctly). notas is free
        text for context that doesn't fit elsewhere (e.g. "redundante con
        publicación previa") — every other field stays strict on purpose.
        """
        ctx = mcp.get_context()
        return await queue.queue_update(
            ctx.request_context.lifespan_context["queue"],
            id, expected_version, updated_by, estado, orden, fecha_prevista, contenido_markdown, imagen, notas,
        )

    @mcp.tool()
    async def queue_mark_published(
        id: str,
        expected_version: int,
        updated_by: str,
        url_wordpress: str,
        fecha_publicada: str,
        canales: dict,
    ) -> dict:
        """
        Marks a queue item as published: sets estado=publicada,
        url_wordpress, fecha_publicada, and REPLACES the whole per-channel
        results map with `canales` (pass a result for every channel this
        publish run attempted — e.g.
        {"wordpress": {"estado": "publicado", "id": "123", "url": "..."},
         "linkedin": {"estado": "error", "error": "OAuth expired"}, ...}).
        Same expected_version conflict protection as queue_update.
        """
        ctx = mcp.get_context()
        return await queue.queue_mark_published(
            ctx.request_context.lifespan_context["queue"],
            id, expected_version, updated_by, url_wordpress, fecha_publicada, canales,
        )

    @mcp.tool()
    async def queue_mark_discarded(
        id: str,
        expected_version: int,
        updated_by: str,
        motivo: str,
        fecha_descartada: str | None = None,
    ) -> dict:
        """
        Marks a queue item as descartada (no longer worth publishing —
        e.g. the news went stale) with a required reason. Same
        expected_version conflict protection as queue_update.
        """
        ctx = mcp.get_context()
        return await queue.queue_mark_discarded(
            ctx.request_context.lifespan_context["queue"],
            id, expected_version, updated_by, motivo, fecha_descartada,
        )

    @mcp.tool()
    async def queue_archive_week(week_start: str, updated_by: str) -> dict:
        """
        Moves every item currently in the queue to archive/<week_start>/,
        clearing the queue for the new week's scan. week_start should be
        the ISO date (YYYY-MM-DD) of the Monday that just ran. Intended
        for the weekly scan pipeline, not the daily publisher.
        """
        ctx = mcp.get_context()
        return await queue.queue_archive_week(
            ctx.request_context.lifespan_context["queue"], week_start, updated_by
        )


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


class TempImageProxyMiddleware:
    """
    Serves gs://<GCS_TEMP_BUCKET>/tmp/... objects at a plain, single-segment
    URL (/temp-image/<token>) instead of exposing GCS's own V4 signed URL to
    external fetchers — see GCSTempStorageClient's docstring for why (in
    short: Instagram's Graph API media-container endpoint reliably failed
    to fetch raw V4 signed URLs).

    Deliberately NOT behind BearerAuthMiddleware — external services (e.g.
    Meta's own fetcher) can't send our internal bearer token. Access
    control instead comes from the token itself: HMAC-signed, short-lived,
    naming exactly one object (see core/temp_image_tokens.py).
    """

    def __init__(self, app, gcs_client) -> None:
        self._app = app
        self._gcs_client = gcs_client

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith("/temp-image/"):
            await self._handle(scope, send)
            return
        await self._app(scope, receive, send)

    async def _handle(self, scope, send) -> None:
        from core.temp_image_tokens import TempImageTokenError, verify

        async def not_found() -> None:
            await send({
                "type": "http.response.start",
                "status": 404,
                "headers": [(b"content-type", b"text/plain")],
            })
            await send({"type": "http.response.body", "body": b"Not found or expired."})

        token = scope["path"][len("/temp-image/"):]
        try:
            object_name = verify(token)
        except TempImageTokenError as exc:
            _logger.info("Rejected /temp-image/ request: %s", exc)
            await not_found()
            return

        try:
            data, content_type = await self._gcs_client.download_temp_image(object_name)
        except Exception as exc:
            _logger.warning("Could not serve temp image %s: %s", object_name, exc)
            await not_found()
            return

        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", content_type.encode("latin-1"))],
        })
        await send({"type": "http.response.body", "body": data})


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
        if _ENABLED["GCS_TEMP_STORAGE"]:
            from clients.gcs_temp_storage_client import GCSTempStorageClient

            _env = env_values(_ENV_PATH)
            _temp_image_client = GCSTempStorageClient(
                _env["GCS_TEMP_BUCKET"], public_base_url=_env.get("PUBLIC_BASE_URL", "")
            )
            app = TempImageProxyMiddleware(app, _temp_image_client)
        port = int(os.getenv("PORT", "8000"))
        uvicorn.run(app, host="0.0.0.0", port=port)

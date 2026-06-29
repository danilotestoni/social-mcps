from __future__ import annotations

from core.logger import get_logger
from core.models import ToolResult
from notifier import notify_browser_needed

_logger = get_logger(__name__)


async def share_to_fb_feed(
    post_url: str,
    message: str | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Sharing to the personal Facebook feed requires Playwright (browser automation).
    There is no public API for this action.
    On Render this always routes to the notifier; invoke social-automation-mcp locally instead.
    """
    if dry_run:
        return ToolResult(success=True, data={
            "dry_run": True,
            "platform": "facebook_personal",
            "payload": {"post_url": post_url, "message": message},
        }).model_dump()
    return await notify_browser_needed(
        platform="Facebook Feed Personal",
        action="share_to_fb_feed",
        payload={"post_url": post_url, "message": message},
        error="share_to_fb_feed requiere Playwright (no disponible en Render). Usa social-automation-mcp en local.",
    )

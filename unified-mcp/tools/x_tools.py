from __future__ import annotations

from clients.x_client import XClient
from core.logger import get_logger
from core.models import ToolResult
from notifier import notify_browser_needed

_logger = get_logger(__name__)


async def post_to_x(
    client: XClient,
    text: str,
    dry_run: bool = False,
) -> dict:
    if dry_run:
        return ToolResult(success=True, data={
            "dry_run": True,
            "platform": "x",
            "payload": {"text": text, "length": len(text)},
        }).model_dump()
    try:
        tweet_id = await client.post_tweet(text)
        url = f"https://x.com/i/web/status/{tweet_id}"
        return ToolResult(success=True, data={"tweet_id": tweet_id, "url": url}).model_dump()
    except Exception as exc:
        _logger.error("Twikit error in post_to_x: %s", exc)
        return await notify_browser_needed(
            platform="X (Twitter)",
            action="post_to_x",
            payload={"text": text},
            error=str(exc),
        )

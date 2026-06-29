from __future__ import annotations

import json
import os

import httpx

from core.logger import get_logger
from core.models import ToolResult

_logger = get_logger(__name__)


async def notify_browser_needed(
    platform: str,
    action: str,
    payload: dict,
    error: str,
) -> dict:
    """
    Returns a structured ToolResult that the AI agent can read and relay to the user.
    Optionally sends an external notification if NOTIFY_WEBHOOK_URL is configured.

    Use this when an action requires Playwright (not available on Render):
    - post_to_x when Twikit fails
    - share_to_fb_feed always (no API alternative)
    """
    message = (
        f"[ACCIÓN MANUAL REQUERIDA] {platform}: '{action}' no puede completarse desde Render.\n"
        f"Error: {error}\n"
        f"Payload: {json.dumps(payload, ensure_ascii=False)}\n"
        f"Solución: Invoca '{action}' desde social-automation-mcp en local (usa Playwright)."
    )
    _logger.warning(message)

    webhook_url = os.getenv("NOTIFY_WEBHOOK_URL")
    if webhook_url:
        try:
            async with httpx.AsyncClient() as client:
                await client.post(webhook_url, json={"text": message}, timeout=5.0)
            _logger.info("Webhook notification sent to %s", webhook_url)
        except Exception as exc:
            _logger.warning("Failed to send webhook notification: %s", exc)

    return ToolResult(
        success=False,
        error=message,
        data={
            "requires_local_playwright": True,
            "platform": platform,
            "action": action,
            "payload": payload,
        },
    ).model_dump()

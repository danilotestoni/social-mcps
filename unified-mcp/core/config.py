from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values, set_key

from core.logger import get_logger

_logger = get_logger(__name__)


def env_values(env_path: Path) -> dict[str, str]:
    """
    Merged credential source: .env file values overridden by process
    environment variables. The same code path works with a local .env file,
    the "env" block of claude_desktop_config.json, and the Render dashboard.
    """
    values: dict[str, str] = {
        k: v for k, v in dotenv_values(env_path).items() if v is not None
    }
    values.update(os.environ)
    return values


def persist_value(env_path: Path, key: str, value: str) -> None:
    """
    Persist a refreshed credential. Always updates the running process env;
    writes to .env only when the filesystem allows it. On Render the disk is
    ephemeral — the process env keeps the new token alive until restart, and
    the dashboard env var should be updated for a permanent change.
    """
    os.environ[key] = value
    try:
        set_key(str(env_path), key, value)
    except OSError as exc:
        _logger.warning("Could not write %s to %s: %s", key, env_path, exc)

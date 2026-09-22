from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import dotenv_values, set_key

from core.logger import get_logger

_logger = get_logger(__name__)

CONSOLIDATED_SECRETS_ENV_VAR = "SOCIAL_MCPS_SECRETS_JSON"


def load_consolidated_secrets(raw: str | None = None) -> None:
    """
    Cloud Run injects every platform credential as ONE JSON-encoded secret
    (SOCIAL_MCPS_SECRETS_JSON) instead of one Secret Manager secret per
    credential, to stay within GCP's free tier of active secret versions.
    Populates os.environ from it so the rest of the app (env_values, auth
    managers) keeps reading credentials exactly as before. Local runs never
    set this var and keep reading unified-mcp/.env unchanged — this is a
    no-op when the var is absent.
    """
    raw_value = raw if raw is not None else os.environ.get(CONSOLIDATED_SECRETS_ENV_VAR)
    if not raw_value:
        return
    try:
        secrets = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        _logger.error("%s is not valid JSON: %s", CONSOLIDATED_SECRETS_ENV_VAR, exc)
        return
    for key, secret_value in secrets.items():
        os.environ.setdefault(key, str(secret_value))


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

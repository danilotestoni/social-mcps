from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import dotenv_values, set_key

from core.logger import get_logger

_logger = get_logger(__name__)

CONSOLIDATED_SECRETS_ENV_VAR = "SOCIAL_MCPS_SECRETS_JSON"
CONSOLIDATED_SECRET_NAME_ENV_VAR = "SOCIAL_MCPS_SECRET_NAME"
GCP_PROJECT_ENV_VARS = ("GOOGLE_CLOUD_PROJECT", "GCP_PROJECT")


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
    """Return .env values overridden by process environment variables."""
    values: dict[str, str] = {
        k: v for k, v in dotenv_values(env_path).items() if v is not None
    }
    values.update(os.environ)
    return values


def _persist_consolidated_secret(key: str, value: str) -> bool:
    raw = os.environ.get(CONSOLIDATED_SECRETS_ENV_VAR)
    secret_name = os.environ.get(CONSOLIDATED_SECRET_NAME_ENV_VAR)
    project_id = next((os.environ.get(k) for k in GCP_PROJECT_ENV_VARS if os.environ.get(k)), None)
    if not raw or not secret_name or not project_id:
        return False

    try:
        from google.cloud import secretmanager

        secrets = json.loads(raw)
        secrets[key] = value
        payload = json.dumps(secrets, separators=(",", ":"), ensure_ascii=False)
        client = secretmanager.SecretManagerServiceClient()
        parent = f"projects/{project_id}/secrets/{secret_name}"
        client.add_secret_version(
            request={"parent": parent, "payload": {"data": payload.encode("utf-8")}}
        )
        os.environ[CONSOLIDATED_SECRETS_ENV_VAR] = payload
        _logger.info("Persisted %s in consolidated Secret Manager secret.", key)
        return True
    except Exception as exc:
        _logger.error("Could not persist %s in consolidated Secret Manager secret: %s", key, exc)
        return False


def persist_value(env_path: Path, key: str, value: str) -> None:
    """
    Persist a refreshed credential.

    Cloud Run keeps all credentials in one consolidated Secret Manager secret.
    When its name and project are configured, add a new version of that same
    secret with only the requested key changed. Local development continues to
    use .env.
    """
    os.environ[key] = value
    if _persist_consolidated_secret(key, value):
        return

    try:
        set_key(str(env_path), key, value)
    except OSError as exc:
        _logger.warning("Could not write %s to %s: %s", key, env_path, exc)

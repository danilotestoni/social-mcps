from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping

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


def _project_id() -> str | None:
    return next((os.environ.get(k) for k in GCP_PROJECT_ENV_VARS if os.environ.get(k)), None)


def _secret_client():
    from google.cloud import secretmanager

    return secretmanager.SecretManagerServiceClient()


def _read_latest_secret(client, project_id: str, secret_name: str) -> str:
    version_name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    response = client.access_secret_version(request={"name": version_name})
    return response.payload.data.decode("utf-8")


def persist_values(env_path: Path, updates: Mapping[str, str]) -> None:
    """Persist a set of values atomically as one version of the consolidated secret.

    Cloud Run reads the latest secret JSON immediately before writing so fields
    changed by other instances are preserved. Local development continues to
    update the process environment and .env file.
    """
    if not updates:
        return

    os.environ.update(updates)
    secret_name = os.environ.get(CONSOLIDATED_SECRET_NAME_ENV_VAR)
    project_id = _project_id()
    if not secret_name or not project_id or not os.environ.get(CONSOLIDATED_SECRETS_ENV_VAR):
        _persist_env_file(env_path, updates)
        return

    try:
        client = _secret_client()
        secrets = json.loads(_read_latest_secret(client, project_id, secret_name))
        secrets.update(updates)
        payload = json.dumps(secrets, separators=(",", ":"), ensure_ascii=False)
        parent = f"projects/{project_id}/secrets/{secret_name}"
        client.add_secret_version(
            request={"parent": parent, "payload": {"data": payload.encode("utf-8")}}
        )
        os.environ[CONSOLIDATED_SECRETS_ENV_VAR] = payload
        _logger.info("Persisted %d credential value(s) in consolidated Secret Manager secret.", len(updates))
    except Exception as exc:
        _logger.error("Could not persist credential set in consolidated Secret Manager secret: %s", exc)
        _persist_env_file(env_path, updates)


def persist_value(env_path: Path, key: str, value: str) -> None:
    """Backward-compatible wrapper for persisting a single credential."""
    persist_values(env_path, {key: value})


def _persist_env_file(env_path: Path, updates: Mapping[str, str]) -> None:
    for key, value in updates.items():
        try:
            set_key(str(env_path), key, value)
        except OSError as exc:
            _logger.warning("Could not write %s to %s: %s", key, env_path, exc)

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
_REQUIRED_SECRET_PERMISSIONS = (
    "secretmanager.versions.access",
    "secretmanager.versions.add",
    "secretmanager.versions.destroy",
    "secretmanager.versions.list",
)


class SecretPersistenceError(RuntimeError):
    """A refreshed credential set could not be safely persisted and rotated."""


def load_consolidated_secrets(raw: str | None = None) -> None:
    """
    Cloud Run injects every platform credential as ONE JSON-encoded secret
    (SOCIAL_MCPS_SECRETS_JSON). Populate os.environ so auth managers keep
    reading credentials as before. Local runs without this variable use .env.
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


def _access_secret_version(client, version_name: str):
    return client.access_secret_version(request={"name": version_name})


def _assert_secret_permissions(client, parent: str) -> None:
    response = client.test_iam_permissions(
        request={"resource": parent, "permissions": list(_REQUIRED_SECRET_PERMISSIONS)}
    )
    missing = set(_REQUIRED_SECRET_PERMISSIONS) - set(response.permissions)
    if missing:
        raise SecretPersistenceError(
            "Cloud Run's service account lacks required permissions on the existing "
            f"consolidated secret: {', '.join(sorted(missing))}"
        )


def _assert_latest_version(client, parent: str, expected_version: str) -> None:
    latest = _access_secret_version(client, f"{parent}/versions/latest")
    if latest.name != expected_version:
        raise SecretPersistenceError(
            "The consolidated secret changed concurrently; refusing to destroy "
            "versions based on a stale refresh."
        )


def _version_number(version_name: str) -> int:
    try:
        return int(version_name.rsplit("/", 1)[1])
    except (IndexError, ValueError) as exc:
        raise SecretPersistenceError(
            f"Unexpected Secret Manager version resource name: {version_name}"
        ) from exc


def _destroy_obsolete_versions(client, parent: str, keep_version: str) -> None:
    # Never destroy the kept version or anything created after it. A manual
    # rotation may add a newer version immediately after our latest check.
    keep_number = _version_number(keep_version)
    for version in client.list_secret_versions(request={"parent": parent}):
        if version.state == 3:  # DESTROYED
            continue
        version_number = _version_number(version.name)
        if version_number < keep_number:
            client.destroy_secret_version(request={"name": version.name})


def preflight_persistence() -> dict[str, str] | None:
    """Validate Cloud Run Secret Manager access before requesting token rotation."""
    if not os.environ.get(CONSOLIDATED_SECRETS_ENV_VAR):
        return None

    secret_name = os.environ.get(CONSOLIDATED_SECRET_NAME_ENV_VAR)
    project_id = _project_id()
    if not secret_name or not project_id:
        raise SecretPersistenceError(
            "Cloud Run has SOCIAL_MCPS_SECRETS_JSON but is missing "
            "SOCIAL_MCPS_SECRET_NAME or GOOGLE_CLOUD_PROJECT/GCP_PROJECT; "
            "refusing to rotate credentials that cannot be durably stored."
        )

    parent = f"projects/{project_id}/secrets/{secret_name}"
    try:
        client = _secret_client()
        _assert_secret_permissions(client, parent)
        latest = _access_secret_version(client, f"{parent}/versions/latest")
        secrets = json.loads(latest.payload.data.decode("utf-8"))
        if not isinstance(secrets, dict):
            raise SecretPersistenceError("The consolidated secret JSON must be an object.")
        return {key: str(value) for key, value in secrets.items()}
    except SecretPersistenceError:
        raise
    except Exception as exc:
        _logger.exception("Could not validate Secret Manager before rotating credentials.")
        raise SecretPersistenceError(
            "Could not verify Secret Manager access before rotating credentials."
        ) from exc


def persist_values(env_path: Path, updates: Mapping[str, str]) -> None:
    """Persist credential updates together in one version of the existing secret.

    In Cloud Run, fail closed if consolidated-secret metadata is missing.
    Verify the new JSON before destroying older versions. Locally, retain the
    existing .env behavior.
    """
    if not updates:
        return

    raw_secret = os.environ.get(CONSOLIDATED_SECRETS_ENV_VAR)
    if not raw_secret:
        os.environ.update(updates)
        _persist_env_file(env_path, updates)
        return

    secret_name = os.environ.get(CONSOLIDATED_SECRET_NAME_ENV_VAR)
    project_id = _project_id()
    if not secret_name or not project_id:
        raise SecretPersistenceError(
            "Cloud Run has SOCIAL_MCPS_SECRETS_JSON but is missing "
            "SOCIAL_MCPS_SECRET_NAME or GOOGLE_CLOUD_PROJECT/GCP_PROJECT; "
            "refusing to fall back to ephemeral .env storage."
        )

    client = _secret_client()
    parent = f"projects/{project_id}/secrets/{secret_name}"
    try:
        _assert_secret_permissions(client, parent)
        latest = _access_secret_version(client, f"{parent}/versions/latest")
        secrets = json.loads(latest.payload.data.decode("utf-8"))
        if not isinstance(secrets, dict):
            raise SecretPersistenceError("The consolidated secret JSON must be an object.")
        secrets.update(updates)
        payload = json.dumps(secrets, separators=(",", ":"), ensure_ascii=False)
        created = client.add_secret_version(
            request={"parent": parent, "payload": {"data": payload.encode("utf-8")}}
        )
        if not created.name:
            raise SecretPersistenceError("Secret Manager did not return the created version name.")

        saved = _access_secret_version(client, created.name)
        if saved.name != created.name or json.loads(saved.payload.data.decode("utf-8")) != secrets:
            raise SecretPersistenceError(
                "The new consolidated secret version did not match the refreshed credentials."
            )
        _assert_latest_version(client, parent, created.name)

        # Use verified rotated tokens in this instance before cleanup. If
        # cleanup fails, do not retry with a refresh token LinkedIn may revoke.
        os.environ.update(updates)
        os.environ[CONSOLIDATED_SECRETS_ENV_VAR] = payload
        _destroy_obsolete_versions(client, parent, created.name)
        _logger.info(
            "Persisted credential updates in one version and destroyed superseded versions."
        )
    except SecretPersistenceError:
        raise
    except Exception as exc:
        _logger.exception("Could not safely persist/rotate the consolidated Secret Manager version.")
        raise SecretPersistenceError(
            "Could not safely persist or clean up the consolidated Secret Manager version."
        ) from exc


def persist_value(env_path: Path, key: str, value: str) -> None:
    """Backward-compatible wrapper for persisting a single credential."""
    persist_values(env_path, {key: value})


def _persist_env_file(env_path: Path, updates: Mapping[str, str]) -> None:
    for key, value in updates.items():
        try:
            set_key(str(env_path), key, value)
        except OSError as exc:
            _logger.warning("Could not write %s to %s: %s", key, env_path, exc)

from __future__ import annotations

import argparse
import contextvars
import os
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator

from core.logger import get_logger

_logger = get_logger(__name__)
_LOCK_OBJECT = "_locks/social-mcps-secret-rotation.lock"
_LOCK_LEASE_SECONDS = 900
_ACQUIRE_TIMEOUT_SECONDS = 120
_HELD_OWNER: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "secret_rotation_lock_owner", default=None
)


class SecretRotationLockError(RuntimeError):
    """Could not acquire or release the shared secret rotation lock."""


@dataclass(frozen=True)
class RotationLease:
    bucket_name: str
    owner: str
    generation: int


def _storage_client(use_gcloud_auth: bool = False):
    from google.cloud import storage

    credentials = None
    if use_gcloud_auth:
        from google.oauth2.credentials import Credentials

        token = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if not token:
            raise SecretRotationLockError("gcloud returned an empty access token.")
        credentials = Credentials(token=token)

    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("SOCIALMCPS_GCP_PROJECT")
    return storage.Client(project=project, credentials=credentials)


def _bucket_name() -> str:
    name = os.environ.get("QUEUE_GCS_BUCKET", "").strip()
    if not name:
        raise SecretRotationLockError(
            "QUEUE_GCS_BUCKET must name the existing shared queue bucket "
            "to serialize secret rotations."
        )
    return name


def acquire_rotation_lock(use_gcloud_auth: bool = False) -> RotationLease:
    from google.api_core.exceptions import NotFound, PreconditionFailed

    bucket_name = _bucket_name()
    bucket = _storage_client(use_gcloud_auth).bucket(bucket_name)
    owner = uuid.uuid4().hex
    deadline = time.monotonic() + _ACQUIRE_TIMEOUT_SECONDS

    while True:
        blob = bucket.blob(_LOCK_OBJECT)
        try:
            blob.upload_from_string(owner, if_generation_match=0)
            return RotationLease(bucket_name, owner, int(blob.generation))
        except PreconditionFailed:
            try:
                blob.reload()
            except NotFound:
                continue
            created = blob.time_created
            stale = bool(
                created
                and (datetime.now(timezone.utc) - created).total_seconds() > _LOCK_LEASE_SECONDS
            )
            if stale:
                try:
                    blob.delete(if_generation_match=int(blob.generation))
                except (NotFound, PreconditionFailed):
                    pass
                continue
            if time.monotonic() >= deadline:
                raise SecretRotationLockError(
                    "Timed out waiting for another secret rotation to finish."
                )
            time.sleep(0.25)
        except Exception as exc:
            raise SecretRotationLockError(
                "Could not acquire the shared secret rotation lock."
            ) from exc


def release_rotation_lock(lease: RotationLease, use_gcloud_auth: bool = False) -> None:
    from google.api_core.exceptions import NotFound

    blob = _storage_client(use_gcloud_auth).bucket(lease.bucket_name).blob(_LOCK_OBJECT)
    try:
        blob.reload()
    except NotFound:
        return
    if blob.download_as_text() != lease.owner:
        raise SecretRotationLockError(
            "The shared rotation lock changed owners before it could be released."
        )
    blob.delete(if_generation_match=lease.generation)


@contextmanager
def secret_rotation_lock() -> Iterator[None]:
    if _HELD_OWNER.get() is not None or not os.environ.get("SOCIAL_MCPS_SECRETS_JSON"):
        yield
        return
    lease = acquire_rotation_lock()
    token = _HELD_OWNER.set(lease.owner)
    try:
        yield
    finally:
        _HELD_OWNER.reset(token)
        try:
            release_rotation_lock(lease)
        except Exception:
            _logger.exception(
                "Could not release shared Secret Manager rotation lock; "
                "it will expire after its lease."
            )


def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("acquire", "release"))
    parser.add_argument("owner", nargs="?")
    parser.add_argument("--gcloud", action="store_true")
    args = parser.parse_args()
    if args.action == "acquire":
        print(acquire_rotation_lock(use_gcloud_auth=args.gcloud).owner)
        return
    if not args.owner:
        parser.error("release requires the lock owner token")

    blob = _storage_client(args.gcloud).bucket(_bucket_name()).blob(_LOCK_OBJECT)
    blob.reload()
    if blob.download_as_text() != args.owner:
        raise SecretRotationLockError("Refusing to release a lock owned by another process.")
    blob.delete(if_generation_match=int(blob.generation))


if __name__ == "__main__":
    try:
        _main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

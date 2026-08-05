from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time


class TempImageTokenError(Exception):
    pass


def _signing_key() -> bytes:
    key = os.getenv("MCP_AUTH_TOKEN", "").strip()
    if not key:
        raise TempImageTokenError(
            "MCP_AUTH_TOKEN must be set to mint or verify /temp-image/ proxy tokens."
        )
    return key.encode("utf-8")


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def mint(object_name: str, expires_at: int) -> str:
    """
    Stateless, tamper-proof token binding one GCS object name to an
    expiry timestamp. Unlike an in-memory token map, this survives across
    Cloud Run instances and cold starts, since the token itself carries
    its own signed claims — no shared storage needed to verify it later.
    """
    payload_b64 = _b64url_encode(f"{expires_at}:{object_name}".encode("utf-8"))
    signature = hmac.new(_signing_key(), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return f"{payload_b64}.{_b64url_encode(signature)}"


def verify(token: str) -> str:
    """Returns the object_name if the token is valid and unexpired; raises
    TempImageTokenError otherwise (bad signature, malformed, expired)."""
    try:
        payload_b64, signature_b64 = token.split(".", 1)
    except ValueError as exc:
        raise TempImageTokenError("Malformed token.") from exc

    expected_signature = hmac.new(
        _signing_key(), payload_b64.encode("ascii"), hashlib.sha256
    ).digest()
    try:
        actual_signature = _b64url_decode(signature_b64)
    except Exception as exc:
        raise TempImageTokenError("Malformed token signature.") from exc

    if not hmac.compare_digest(expected_signature, actual_signature):
        raise TempImageTokenError("Invalid token signature.")

    try:
        expires_at_str, object_name = _b64url_decode(payload_b64).decode("utf-8").split(":", 1)
        expires_at = int(expires_at_str)
    except Exception as exc:
        raise TempImageTokenError("Malformed token payload.") from exc

    if time.time() >= expires_at:
        raise TempImageTokenError("Token has expired.")

    return object_name

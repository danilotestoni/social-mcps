from __future__ import annotations

import time
from pathlib import Path

import httpx

from core.config import env_values, persist_value
from core.logger import get_logger
from core.models import ThreadsTokenData

_THREADS_URL = "https://graph.threads.net/v1.0"
_WARNING_WINDOW = 7 * 24 * 3600  # 7 days in seconds

_REQUIRED_KEYS = (
    "THREADS_APP_ID",
    "THREADS_APP_SECRET",
    "THREADS_ACCESS_TOKEN",
    "THREADS_TOKEN_EXPIRY",
    "THREADS_USER_ID",
)


class AuthError(Exception):
    pass


class ThreadsTokenManager:
    def __init__(self, env_path: Path) -> None:
        self._env_path = env_path
        self._logger = get_logger(__name__)

    def load(self) -> dict[str, str]:
        values = env_values(self._env_path)
        missing = [k for k in _REQUIRED_KEYS if not (values.get(k) or "").strip()]
        if missing:
            raise AuthError(
                f"Missing required credentials: {', '.join(missing)}. "
                "Set them as environment variables or in .env."
            )
        return {k: values[k] for k in _REQUIRED_KEYS}  # type: ignore[return-value]

    def _never_expires(self, expiry: int) -> bool:
        return expiry == 0

    def is_expired(self, expiry: int) -> bool:
        if self._never_expires(expiry):
            return False
        return int(time.time()) >= expiry

    def expiring_soon(self, expiry: int) -> bool:
        if self._never_expires(expiry):
            return False
        seconds_remaining = expiry - int(time.time())
        return 0 < seconds_remaining < _WARNING_WINDOW

    async def refresh(self, current_token: str) -> ThreadsTokenData:
        self._logger.info("Refreshing Threads long-lived token.")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{_THREADS_URL}/refresh_access_token",
                params={
                    "grant_type": "th_refresh_token",
                    "access_token": current_token,
                },
            )
        if response.status_code != 200:
            raise AuthError(
                f"Token refresh failed ({response.status_code}): {response.text}"
            )
        payload = response.json()
        expires_in = payload.get("expires_in", 5183999)
        token_data = ThreadsTokenData(
            access_token=payload["access_token"],
            token_expiry=int(time.time()) + expires_in,
        )
        self._logger.info("Threads access token refreshed successfully.")
        return token_data

    def persist(self, token_data: ThreadsTokenData) -> None:
        persist_value(self._env_path, "THREADS_ACCESS_TOKEN", token_data.access_token)
        persist_value(self._env_path, "THREADS_TOKEN_EXPIRY", str(token_data.token_expiry))
        self._logger.debug("Updated Threads token persisted.")

    async def get_valid_token(self) -> str:
        env = self.load()
        expiry = int(env["THREADS_TOKEN_EXPIRY"])
        if self.is_expired(expiry):
            # th_refresh_token requires a still-valid token, so once expired
            # the refresh is guaranteed to fail — surface a clear error instead.
            raise AuthError(
                "Threads access token has expired and can no longer be refreshed "
                "automatically. Run oauth_setup.py (or the Meta panel) to obtain "
                "a new token and update THREADS_ACCESS_TOKEN / THREADS_TOKEN_EXPIRY."
            )
        if self.expiring_soon(expiry):
            try:
                token_data = await self.refresh(env["THREADS_ACCESS_TOKEN"])
                self.persist(token_data)
                return token_data.access_token
            except Exception as exc:
                self._logger.warning(
                    "Proactive Threads token refresh failed (%s); "
                    "current token is still valid, continuing with it.", exc
                )
        return env["THREADS_ACCESS_TOKEN"]

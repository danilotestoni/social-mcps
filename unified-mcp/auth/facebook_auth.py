from __future__ import annotations

import time
from pathlib import Path

import httpx

from core.config import env_values, persist_value
from core.logger import get_logger
from core.models import FacebookTokenData

_GRAPH_URL = "https://graph.facebook.com/v21.0"
_WARNING_WINDOW = 7 * 24 * 3600  # 7 days in seconds

_REQUIRED_KEYS = (
    "FACEBOOK_APP_ID",
    "FACEBOOK_APP_SECRET",
    "FACEBOOK_ACCESS_TOKEN",
    "FACEBOOK_TOKEN_EXPIRY",
    "FACEBOOK_PAGE_ID",
)


class AuthError(Exception):
    pass


class FacebookTokenManager:
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

    async def refresh(self, app_id: str, app_secret: str, current_token: str) -> FacebookTokenData:
        self._logger.info("Refreshing Facebook long-lived token.")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{_GRAPH_URL}/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": app_id,
                    "client_secret": app_secret,
                    "fb_exchange_token": current_token,
                },
            )
        if response.status_code != 200:
            raise AuthError(
                f"Token refresh failed ({response.status_code}): {response.text}"
            )
        payload = response.json()
        expires_in = payload.get("expires_in", 5183999)
        token_data = FacebookTokenData(
            access_token=payload["access_token"],
            token_expiry=int(time.time()) + expires_in,
        )
        self._logger.info("Access token refreshed successfully.")
        return token_data

    def persist(self, token_data: FacebookTokenData) -> None:
        persist_value(self._env_path, "FACEBOOK_ACCESS_TOKEN", token_data.access_token)
        persist_value(self._env_path, "FACEBOOK_TOKEN_EXPIRY", str(token_data.token_expiry))
        self._logger.debug("Updated tokens persisted.")

    async def get_valid_token(self) -> str:
        env = self.load()
        expiry = int(env["FACEBOOK_TOKEN_EXPIRY"])
        if self.is_expired(expiry):
            # fb_exchange_token requires a still-valid token, so once expired
            # the refresh is guaranteed to fail — surface a clear error instead.
            raise AuthError(
                "Facebook access token has expired and can no longer be refreshed "
                "automatically. Generate a new token via Graph API Explorer and "
                "update FACEBOOK_ACCESS_TOKEN / FACEBOOK_TOKEN_EXPIRY."
            )
        if self.expiring_soon(expiry):
            try:
                token_data = await self.refresh(
                    env["FACEBOOK_APP_ID"],
                    env["FACEBOOK_APP_SECRET"],
                    env["FACEBOOK_ACCESS_TOKEN"],
                )
                self.persist(token_data)
                return token_data.access_token
            except Exception as exc:
                self._logger.warning(
                    "Proactive Facebook token refresh failed (%s); "
                    "current token is still valid, continuing with it.", exc
                )
        return env["FACEBOOK_ACCESS_TOKEN"]

from __future__ import annotations

import time
from pathlib import Path

import httpx
from dotenv import dotenv_values, set_key

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
        values = dotenv_values(self._env_path)
        missing = [k for k in _REQUIRED_KEYS if not values.get(k, "").strip()]
        if missing:
            raise AuthError(
                f"Missing required .env keys: {', '.join(missing)}. "
                "Run oauth_setup.py to initialize credentials."
            )
        return {k: values[k] for k in _REQUIRED_KEYS}  # type: ignore[return-value]

    def _never_expires(self, expiry: int) -> bool:
        return expiry == 0

    def is_expired(self, expiry: int) -> bool:
        if self._never_expires(expiry):
            return False
        return int(time.time()) >= expiry

    def warn_if_expiring_soon(self, expiry: int) -> None:
        if self._never_expires(expiry):
            return
        seconds_remaining = expiry - int(time.time())
        if 0 < seconds_remaining < _WARNING_WINDOW:
            days = seconds_remaining // 86400
            self._logger.warning(
                "Facebook access token expires in %d day(s). "
                "Run oauth_setup.py to renew before it expires.",
                days,
            )

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
        set_key(str(self._env_path), "FACEBOOK_ACCESS_TOKEN", token_data.access_token)
        set_key(str(self._env_path), "FACEBOOK_TOKEN_EXPIRY", str(token_data.token_expiry))
        self._logger.debug("Updated tokens written to .env.")

    async def get_valid_token(self) -> str:
        env = self.load()
        expiry = int(env["FACEBOOK_TOKEN_EXPIRY"])
        self.warn_if_expiring_soon(expiry)
        if self.is_expired(expiry):
            token_data = await self.refresh(
                env["FACEBOOK_APP_ID"],
                env["FACEBOOK_APP_SECRET"],
                env["FACEBOOK_ACCESS_TOKEN"],
            )
            self.persist(token_data)
            return token_data.access_token
        return env["FACEBOOK_ACCESS_TOKEN"]

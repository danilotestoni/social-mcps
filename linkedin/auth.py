from __future__ import annotations

import time
from pathlib import Path

import httpx
from dotenv import dotenv_values, set_key

from logger import get_logger
from models import TokenData

_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
_WARNING_WINDOW = 7 * 24 * 3600  # 7 days in seconds

_REQUIRED_KEYS = (
    "LINKEDIN_CLIENT_ID",
    "LINKEDIN_CLIENT_SECRET",
    "LINKEDIN_ACCESS_TOKEN",
    "LINKEDIN_TOKEN_EXPIRY",
    "LINKEDIN_PERSON_URN",
)
_OPTIONAL_KEYS = ("LINKEDIN_REFRESH_TOKEN",)


class AuthError(Exception):
    pass


class TokenManager:
    def __init__(self, env_path: Path) -> None:
        self._env_path = env_path
        self._logger = get_logger(__name__)

    def load(self) -> dict[str, str]:
        values = dotenv_values(self._env_path)
        missing = [k for k in _REQUIRED_KEYS if not values.get(k)]
        if missing:
            raise AuthError(
                f"Missing required .env keys: {', '.join(missing)}. "
                f"Run oauth_setup.py to initialize credentials."
            )
        return {k: values[k] for k in _REQUIRED_KEYS} | {k: values.get(k, "") for k in _OPTIONAL_KEYS}  # type: ignore[return-value]

    def is_expired(self, expiry: int) -> bool:
        return int(time.time()) >= expiry

    def warn_if_expiring_soon(self, expiry: int) -> None:
        seconds_remaining = expiry - int(time.time())
        if 0 < seconds_remaining < _WARNING_WINDOW:
            days = seconds_remaining // 86400
            self._logger.warning(
                "LinkedIn access token expires in %d day(s). "
                "Run oauth_setup.py to renew before it expires.",
                days,
            )

    async def refresh(
        self, client_id: str, client_secret: str, refresh_token: str
    ) -> TokenData:
        self._logger.info("Refreshing LinkedIn access token.")
        async with httpx.AsyncClient() as client:
            response = await client.post(
                _TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if response.status_code != 200:
            raise AuthError(
                f"Token refresh failed ({response.status_code}): {response.text}"
            )
        payload = response.json()
        token_data = TokenData(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token", refresh_token),
            expires_in=payload["expires_in"],
            token_expiry=int(time.time()) + payload["expires_in"],
        )
        self._logger.info("Access token refreshed successfully.")
        return token_data

    def persist(self, token_data: TokenData) -> None:
        set_key(str(self._env_path), "LINKEDIN_ACCESS_TOKEN", token_data.access_token)
        set_key(str(self._env_path), "LINKEDIN_REFRESH_TOKEN", token_data.refresh_token)
        set_key(str(self._env_path), "LINKEDIN_TOKEN_EXPIRY", str(token_data.token_expiry))
        self._logger.debug("Updated tokens written to .env.")

    async def get_valid_token(self) -> str:
        env = self.load()
        expiry = int(env["LINKEDIN_TOKEN_EXPIRY"])
        self.warn_if_expiring_soon(expiry)
        if self.is_expired(expiry):
            refresh_token = env.get("LINKEDIN_REFRESH_TOKEN", "")
            if not refresh_token:
                raise AuthError(
                    "LinkedIn access token has expired and no refresh token is available. "
                    "Run oauth_setup.py to obtain a new access token."
                )
            token_data = await self.refresh(
                env["LINKEDIN_CLIENT_ID"],
                env["LINKEDIN_CLIENT_SECRET"],
                refresh_token,
            )
            self.persist(token_data)
            return token_data.access_token
        return env["LINKEDIN_ACCESS_TOKEN"]

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import httpx

from core.config import SecretPersistenceError, env_values, persist_values, preflight_persistence
from core.logger import get_logger
from core.models import LinkedInTokenData
from core.secret_rotation_lock import secret_rotation_lock

_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
_WARNING_WINDOW = 7 * 24 * 3600  # 7 days in seconds
_TOKEN_REFRESH_LOCK = asyncio.Lock()

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


class LinkedInTokenManager:
    def __init__(self, env_path: Path) -> None:
        self._env_path = env_path
        self._logger = get_logger(__name__)

    def load(self) -> dict[str, str]:
        values = env_values(self._env_path)
        missing = [k for k in _REQUIRED_KEYS if not values.get(k)]
        if missing:
            raise AuthError(
                f"Missing required credentials: {', '.join(missing)}. "
                "Set them as environment variables or in .env."
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
    ) -> LinkedInTokenData:
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
        token_data = LinkedInTokenData(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token", refresh_token),
            expires_in=payload["expires_in"],
            token_expiry=int(time.time()) + payload["expires_in"],
        )
        self._logger.info("Access token refreshed successfully.")
        return token_data

    def persist(self, token_data: LinkedInTokenData) -> None:
        persist_values(
            self._env_path,
            {
                "LINKEDIN_ACCESS_TOKEN": token_data.access_token,
                "LINKEDIN_REFRESH_TOKEN": token_data.refresh_token,
                "LINKEDIN_TOKEN_EXPIRY": str(token_data.token_expiry),
            },
        )
        self._logger.debug("Updated tokens persisted.")

    async def get_valid_token(self) -> str:
        # One Cloud Run instance is configured for one request at a time; this
        # process-wide lock also protects multiple managers in that instance.
        async with _TOKEN_REFRESH_LOCK:
            env = self.load()
            expiry = int(env["LINKEDIN_TOKEN_EXPIRY"])
            self.warn_if_expiring_soon(expiry)
            if self.is_expired(expiry):
                # A manual rotation may have updated Secret Manager without
                # restarting this instance. Reload it while holding the shared lock.
                with secret_rotation_lock():
                    latest_secrets = preflight_persistence()
                    refresh_env = env
                    if latest_secrets is not None:
                        required_latest_keys = (
                            "LINKEDIN_ACCESS_TOKEN",
                            "LINKEDIN_TOKEN_EXPIRY",
                            "LINKEDIN_CLIENT_ID",
                            "LINKEDIN_CLIENT_SECRET",
                        )
                        missing = [key for key in required_latest_keys if not latest_secrets.get(key)]
                        if missing:
                            raise AuthError(
                                "The latest consolidated secret is missing LinkedIn credentials: "
                                + ", ".join(missing)
                            )
                        linked_in_keys = (
                            "LINKEDIN_ACCESS_TOKEN",
                            "LINKEDIN_REFRESH_TOKEN",
                            "LINKEDIN_TOKEN_EXPIRY",
                            "LINKEDIN_CLIENT_ID",
                            "LINKEDIN_CLIENT_SECRET",
                        )
                        latest_linkedin = {
                            key: latest_secrets[key]
                            for key in linked_in_keys
                            if key in latest_secrets
                        }
                        refresh_env = env | latest_linkedin
                        os.environ.update(latest_linkedin)

                    latest_expiry = int(refresh_env["LINKEDIN_TOKEN_EXPIRY"])
                    if not self.is_expired(latest_expiry):
                        return refresh_env["LINKEDIN_ACCESS_TOKEN"]

                    refresh_token = refresh_env.get("LINKEDIN_REFRESH_TOKEN", "")
                    if not refresh_token:
                        raise AuthError(
                            "LinkedIn access token has expired and no refresh token is available. "
                            "Run oauth_setup.py to obtain a new access token."
                        )

                    token_data = await self.refresh(
                        refresh_env["LINKEDIN_CLIENT_ID"],
                        refresh_env["LINKEDIN_CLIENT_SECRET"],
                        refresh_token,
                    )
                    try:
                        self.persist(token_data)
                    except SecretPersistenceError:
                        os.environ.update(
                            {
                                "LINKEDIN_ACCESS_TOKEN": token_data.access_token,
                                "LINKEDIN_REFRESH_TOKEN": token_data.refresh_token,
                                "LINKEDIN_TOKEN_EXPIRY": str(token_data.token_expiry),
                            }
                        )
                        self._logger.exception(
                            "LinkedIn returned rotated credentials but persistence failed; "
                            "retaining them in process memory."
                        )
                    return token_data.access_token
            return env["LINKEDIN_ACCESS_TOKEN"]

from __future__ import annotations

from pathlib import Path

from dotenv import dotenv_values

from logger import get_logger

# WordPress.com access tokens are permanent and never expire.
# There is no refresh mechanism — the token stays valid until manually revoked.

_REQUIRED_KEYS = (
    "WP_CLIENT_ID",
    "WP_CLIENT_SECRET",
    "WP_ACCESS_TOKEN",
    "WP_SITE_ID",
)


class AuthError(Exception):
    pass


class TokenManager:
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

    def get_token(self) -> str:
        return self.load()["WP_ACCESS_TOKEN"]

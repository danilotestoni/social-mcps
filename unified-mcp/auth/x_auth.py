from __future__ import annotations

from pathlib import Path

from dotenv import dotenv_values

from core.logger import get_logger

_REQUIRED_KEYS = (
    "X_USERNAME",
    "X_PASSWORD",
    "X_EMAIL",
)


class AuthError(Exception):
    pass


class XCredentials:
    def __init__(self, env_path: Path) -> None:
        self._env_path = env_path
        self._logger = get_logger(__name__)

    def load(self) -> dict[str, str]:
        values = dotenv_values(self._env_path)
        missing = [k for k in _REQUIRED_KEYS if not values.get(k, "").strip()]
        if missing:
            raise AuthError(
                f"Missing required .env keys: {', '.join(missing)}. "
                "Add your X (Twitter) username, password, and email to .env."
            )
        return {k: values[k] for k in _REQUIRED_KEYS}  # type: ignore[return-value]

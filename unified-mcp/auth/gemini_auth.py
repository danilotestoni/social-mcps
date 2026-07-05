from __future__ import annotations

from pathlib import Path

from core.config import env_values
from core.logger import get_logger

_REQUIRED_KEYS = ("GEMINI_API_KEY",)


class AuthError(Exception):
    pass


class GeminiCredentials:
    def __init__(self, env_path: Path) -> None:
        self._env_path = env_path
        self._logger = get_logger(__name__)

    def load(self) -> dict[str, str]:
        values = env_values(self._env_path)
        missing = [k for k in _REQUIRED_KEYS if not (values.get(k) or "").strip()]
        if missing:
            raise AuthError(
                f"Missing required credentials: {', '.join(missing)}. "
                "Get a free API key at https://aistudio.google.com/apikey and set "
                "GEMINI_API_KEY as an environment variable or in .env."
            )
        return {k: values[k] for k in _REQUIRED_KEYS}  # type: ignore[return-value]

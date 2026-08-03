from __future__ import annotations

import asyncio
from pathlib import Path

from core.logger import get_logger

_DEFAULT_SPACE = "black-forest-labs/FLUX.1-schnell"

_EXT_TO_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class HuggingFaceFluxError(Exception):
    pass


class HuggingFaceFluxClient:
    """
    Image generation via the public black-forest-labs/FLUX.1-schnell Gradio
    Space on Hugging Face (called through gradio_client). Free, no API key.
    Second choice in the fallback chain — used only when the Cloudflare
    Worker fails or is unavailable.
    """

    def __init__(self, space: str = _DEFAULT_SPACE) -> None:
        self._space = space
        self._logger = get_logger(__name__)
        self._client = None

    def _get_client(self):
        if self._client is None:
            from gradio_client import Client

            self._client = Client(self._space)
        return self._client

    def _generate_image_sync(self, prompt: str) -> tuple[bytes, str]:
        client = self._get_client()
        # Confirmed live against the Space's /infer signature:
        # (prompt, seed, randomize_seed, width, height, num_inference_steps)
        # -> (local_file_path, seed)
        result = client.predict(
            prompt,
            0,
            True,
            1024,
            1024,
            4,
            api_name="/infer",
        )
        path = Path(result[0] if isinstance(result, (list, tuple)) else result)
        data = path.read_bytes()
        mime_type = _EXT_TO_MIME.get(path.suffix.lower(), "image/png")
        return data, mime_type

    async def generate_image(self, prompt: str, aspect_ratio: str = "1:1") -> tuple[bytes, str]:
        """
        Generate one image from a text prompt via the FLUX.1-schnell Space.
        aspect_ratio is accepted for interface parity but this Space's
        /infer signature only exposes width/height (not aspect-ratio
        presets) — a fixed 1024x1024 is requested regardless.
        Returns (image_bytes, mime_type).
        """
        self._logger.info("Generating image with Hugging Face Space %s.", self._space)
        try:
            return await asyncio.to_thread(self._generate_image_sync, prompt)
        except Exception as exc:
            raise HuggingFaceFluxError(str(exc)) from exc

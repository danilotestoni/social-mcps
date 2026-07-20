from __future__ import annotations

from urllib.parse import quote

import httpx

from core.logger import get_logger
from core.retry import _retried_with_timeout

_VALID_ASPECT_RATIOS = ("1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9")

_DIMENSIONS_BY_ASPECT_RATIO = {
    "1:1": (1024, 1024),
    "2:3": (832, 1248),
    "3:2": (1248, 832),
    "3:4": (896, 1152),
    "4:3": (1152, 896),
    "4:5": (928, 1152),
    "5:4": (1152, 928),
    "9:16": (768, 1344),
    "16:9": (1344, 768),
    "21:9": (1536, 672),
}


class PollinationsAPIError(Exception):
    pass


class PollinationsImageClient:
    """
    Image generation via the public Pollinations.ai API (image.pollinations.ai).
    No API key, no signup, no expiring trial — used as an automatic, always-on
    fallback when Gemini is unavailable or out of quota.
    """

    def __init__(self, base_url: str = "https://image.pollinations.ai", model: str = "flux") -> None:
        self._base_url = base_url
        self._model = model
        self._logger = get_logger(__name__)

    @staticmethod
    def _dimensions(aspect_ratio: str) -> tuple[int, int]:
        if aspect_ratio not in _DIMENSIONS_BY_ASPECT_RATIO:
            raise PollinationsAPIError(
                f"Invalid aspect_ratio '{aspect_ratio}'. "
                f"Valid values: {', '.join(_VALID_ASPECT_RATIOS)}"
            )
        return _DIMENSIONS_BY_ASPECT_RATIO[aspect_ratio]

    @staticmethod
    def _mime_type(response: httpx.Response) -> str:
        content_type = response.headers.get("content-type", "image/jpeg")
        return content_type.split(";")[0].strip() or "image/jpeg"

    async def _generate_image_async(self, prompt: str, aspect_ratio: str) -> tuple[bytes, str]:
        width, height = self._dimensions(aspect_ratio)
        self._logger.info("Generating image with Pollinations.ai (aspect %s).", aspect_ratio)

        async with httpx.AsyncClient(base_url=self._base_url, timeout=90.0) as client:
            response = await client.get(
                f"/prompt/{quote(prompt, safe='')}",
                params={
                    "width": width,
                    "height": height,
                    "model": self._model,
                    "nologo": "true",
                },
            )

        response.raise_for_status()

        image_bytes = response.content
        if not image_bytes:
            raise PollinationsAPIError("Pollinations returned an empty response.")

        mime_type = self._mime_type(response)
        self._logger.info("Image generated successfully (%s, %d bytes).", mime_type, len(image_bytes))
        return image_bytes, mime_type

    @_retried_with_timeout
    async def generate_image(self, prompt: str, aspect_ratio: str = "1:1") -> tuple[bytes, str]:
        """
        Generate one image from a text prompt.
        Returns (image_bytes, mime_type).
        """
        return await self._generate_image_async(prompt, aspect_ratio)

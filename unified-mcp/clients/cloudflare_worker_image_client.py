from __future__ import annotations

import httpx

from core.logger import get_logger
from core.retry import _retried_with_timeout


class CloudflareWorkerImageError(Exception):
    pass


class CloudflareWorkerImageClient:
    """
    Image generation via a personal Cloudflare Worker running FLUX-1-schnell
    on Workers AI (image-burn.danilo-testoni.workers.dev by default). Free
    to us — the Worker holds its own Workers AI binding, so this client
    needs no API key. First choice in the fallback chain since it has no
    per-image cost.
    """

    def __init__(self, base_url: str = "https://image-burn.danilo-testoni.workers.dev") -> None:
        self._base_url = base_url
        self._logger = get_logger(__name__)

    @staticmethod
    def _mime_type(response: httpx.Response) -> str:
        content_type = response.headers.get("content-type", "image/jpeg")
        return content_type.split(";")[0].strip() or "image/jpeg"

    async def _generate_image_async(self, prompt: str) -> tuple[bytes, str]:
        self._logger.info("Generating image with Cloudflare Workers AI (FLUX-1-schnell).")

        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.get(self._base_url, params={"prompt": prompt})
        response.raise_for_status()

        image_bytes = response.content
        if not image_bytes:
            raise CloudflareWorkerImageError("Cloudflare Worker returned an empty response.")

        mime_type = self._mime_type(response)
        if not mime_type.startswith("image/"):
            raise CloudflareWorkerImageError(
                f"Cloudflare Worker returned a non-image response ({mime_type})."
            )

        self._logger.info(
            "Image generated successfully (%s, %d bytes).", mime_type, len(image_bytes)
        )
        return image_bytes, mime_type

    @_retried_with_timeout
    async def generate_image(self, prompt: str, aspect_ratio: str = "1:1") -> tuple[bytes, str]:
        """
        Generate one image from a text prompt. aspect_ratio is accepted for
        interface parity with the other providers, but this Worker's
        FLUX-1-schnell binding only produces its fixed default output size —
        the parameter is currently not forwarded upstream.
        Returns (image_bytes, mime_type).
        """
        return await self._generate_image_async(prompt)

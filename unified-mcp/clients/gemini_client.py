from __future__ import annotations

import base64

import httpx

from core.logger import get_logger
from core.retry import _retried

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_DEFAULT_MODEL = "gemini-2.5-flash-image"
_REQUEST_TIMEOUT = 120.0  # image generation can take a while

_VALID_ASPECT_RATIOS = ("1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9")


class GeminiAPIError(Exception):
    pass


class GeminiImageClient:
    """
    Image generation via the Gemini API ("nano banana" — gemini-2.5-flash-image).
    Free tier available with a Google AI Studio API key.
    """

    def __init__(self, api_key: str, model: str = _DEFAULT_MODEL) -> None:
        self._api_key = api_key
        self._model = model
        self._logger = get_logger(__name__)

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code >= 400:
            self._logger.error(
                "Gemini API error %s: %s", response.status_code, response.text
            )
            response.raise_for_status()

    @_retried
    async def generate_image(self, prompt: str, aspect_ratio: str = "1:1") -> tuple[bytes, str]:
        """
        Generate one image from a text prompt.
        Returns (image_bytes, mime_type).
        """
        if aspect_ratio not in _VALID_ASPECT_RATIOS:
            raise GeminiAPIError(
                f"Invalid aspect_ratio '{aspect_ratio}'. "
                f"Valid values: {', '.join(_VALID_ASPECT_RATIOS)}"
            )
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {"aspectRatio": aspect_ratio},
            },
        }
        self._logger.info("Generating image with %s (aspect %s).", self._model, aspect_ratio)
        async with httpx.AsyncClient(base_url=_BASE_URL, timeout=_REQUEST_TIMEOUT) as client:
            response = await client.post(
                f"/models/{self._model}:generateContent",
                json=body,
                # API key goes in a header, not the URL, so it never appears
                # in logs or error messages.
                headers={"x-goog-api-key": self._api_key},
            )
        self._raise_for_status(response)
        payload = response.json()

        candidates = payload.get("candidates", [])
        if not candidates:
            feedback = payload.get("promptFeedback", {})
            raise GeminiAPIError(
                f"Gemini returned no candidates (possibly blocked). Feedback: {feedback}"
            )
        for part in candidates[0].get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                mime_type = inline.get("mimeType") or inline.get("mime_type") or "image/png"
                self._logger.info("Image generated successfully (%s).", mime_type)
                return base64.b64decode(inline["data"]), mime_type
        raise GeminiAPIError(
            "Gemini response contained no image data. "
            f"Finish reason: {candidates[0].get('finishReason', 'unknown')}"
        )

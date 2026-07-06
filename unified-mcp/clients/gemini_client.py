from __future__ import annotations

import asyncio
import base64
from typing import Any

from google import genai

from core.logger import get_logger
from core.retry import _retried

_DEFAULT_MODEL = "models/gemini-3.1-flash-lite-image"

_VALID_ASPECT_RATIOS = ("1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9")


class GeminiAPIError(Exception):
    pass


class GeminiImageClient:
    """
    Image generation via the Google Gen AI SDK.
    Free tier available with a Google AI Studio API key.
    """

    def __init__(self, api_key: str, model: str = _DEFAULT_MODEL) -> None:
        self._model = model
        self._client = genai.Client(api_key=api_key)
        self._logger = get_logger(__name__)

    @staticmethod
    def _part_value(part: Any, name: str) -> Any:
        if isinstance(part, dict):
            return part.get(name)
        return getattr(part, name, None)

    def _generate_image_sync(self, prompt: str, aspect_ratio: str) -> tuple[bytes, str]:
        generation_config = {
            "temperature": 1,
            "max_output_tokens": 65536,
            "top_p": 0.95,
            "thinking_level": "low",
        }
        prompt_with_format = (
            f"{prompt}\n\n"
            f"Generate the image with an aspect ratio of {aspect_ratio}."
        )

        interaction = self._client.interactions.create(
            model=self._model,
            input=prompt_with_format,
            generation_config=generation_config,
            response_modalities=["image", "text"],
        )

        text_parts: list[str] = []
        for step in getattr(interaction, "steps", []) or []:
            if self._part_value(step, "type") != "model_output":
                continue
            for part in self._part_value(step, "content") or []:
                part_type = self._part_value(part, "type")
                if part_type == "image":
                    data = self._part_value(part, "data")
                    if not data:
                        continue
                    mime_type = (
                        self._part_value(part, "mime_type")
                        or self._part_value(part, "mimeType")
                        or "image/png"
                    )
                    return base64.b64decode(data), mime_type
                if part_type == "text":
                    text = self._part_value(part, "text")
                    if text:
                        text_parts.append(text)

        detail = " ".join(text_parts).strip()
        raise GeminiAPIError(
            "Gemini response contained no image data."
            + (f" Text response: {detail}" if detail else "")
        )

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

        self._logger.info("Generating image with %s (aspect %s).", self._model, aspect_ratio)
        try:
            image_bytes, mime_type = await asyncio.to_thread(
                self._generate_image_sync, prompt, aspect_ratio
            )
        except GeminiAPIError:
            raise
        except Exception as exc:
            raise GeminiAPIError(str(exc)) from exc
        self._logger.info("Image generated successfully (%s).", mime_type)
        return image_bytes, mime_type

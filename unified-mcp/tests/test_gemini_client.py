from __future__ import annotations

import base64
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from clients.gemini_client import GeminiImageClient


class FakeInteractions:
    def __init__(self) -> None:
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        image_data = base64.b64encode(b"fake-image").decode("ascii")
        image = SimpleNamespace(type="image", data=image_data, mime_type="image/png")
        step = SimpleNamespace(type="model_output", content=[image])
        return SimpleNamespace(steps=[step])


class GeminiImageClientTests(TestCase):
    def test_interaction_uses_supported_low_thinking_level(self) -> None:
        client = GeminiImageClient.__new__(GeminiImageClient)
        fake_interactions = FakeInteractions()
        client._model = "models/gemini-3.1-flash-lite-image"
        client._client = SimpleNamespace(interactions=fake_interactions)

        image_bytes, mime_type = client._generate_image_sync("Draw a square", "1:1")

        self.assertEqual(image_bytes, b"fake-image")
        self.assertEqual(mime_type, "image/png")
        self.assertEqual(
            fake_interactions.kwargs["generation_config"]["thinking_level"],
            "low",
        )
        self.assertEqual(fake_interactions.kwargs["response_modalities"], ["image", "text"])

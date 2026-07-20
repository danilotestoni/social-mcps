from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tools.image_tools as image_tools


class _FakeImageClient:
    def __init__(self, *, image_bytes=b"fake-bytes", mime_type="image/png", error=None):
        self._image_bytes = image_bytes
        self._mime_type = mime_type
        self._error = error
        self.calls = []

    async def generate_image(self, prompt, aspect_ratio="1:1"):
        self.calls.append((prompt, aspect_ratio))
        if self._error is not None:
            raise self._error
        return self._image_bytes, self._mime_type


class _FakeWordPressClient:
    def __init__(self, *, url="https://example.wordpress.com/media.jpg", media_id=42, error=None):
        self._url = url
        self._media_id = media_id
        self._error = error
        self.uploaded = []

    async def upload_media_get_url(self, data, filename):
        self.uploaded.append((data, filename))
        if self._error is not None:
            raise self._error
        return {"url": self._url, "id": self._media_id}


class GenerateImageFallbackTests(TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        patcher = patch("tools.image_tools._OUTPUT_DIR", Path(self._tmpdir.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_uses_gemini_when_it_succeeds_and_never_calls_pollinations(self) -> None:
        gemini = _FakeImageClient(image_bytes=b"gemini-bytes", mime_type="image/png")
        pollinations = _FakeImageClient(image_bytes=b"pollinations-bytes")

        result = asyncio.run(
            image_tools.generate_image(gemini, "a cat", pollinations_client=pollinations)
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["provider"], "gemini")
        self.assertNotIn("fallback_reason", result["data"])
        self.assertEqual(len(gemini.calls), 1)
        self.assertEqual(len(pollinations.calls), 0)

    def test_falls_back_to_pollinations_when_gemini_fails(self) -> None:
        gemini = _FakeImageClient(error=RuntimeError("quota exceeded"))
        pollinations = _FakeImageClient(image_bytes=b"pollinations-bytes", mime_type="image/jpeg")

        result = asyncio.run(
            image_tools.generate_image(gemini, "a cat", pollinations_client=pollinations)
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["provider"], "pollinations")
        self.assertIn("quota exceeded", result["data"]["fallback_reason"])
        self.assertEqual(len(gemini.calls), 1)
        self.assertEqual(len(pollinations.calls), 1)

    def test_uses_pollinations_directly_when_gemini_not_configured(self) -> None:
        pollinations = _FakeImageClient(image_bytes=b"pollinations-bytes")

        result = asyncio.run(
            image_tools.generate_image(None, "a cat", pollinations_client=pollinations)
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["provider"], "pollinations")
        self.assertEqual(len(pollinations.calls), 1)

    def test_fails_when_all_providers_fail(self) -> None:
        gemini = _FakeImageClient(error=RuntimeError("gemini down"))
        pollinations = _FakeImageClient(error=RuntimeError("pollinations down"))

        result = asyncio.run(
            image_tools.generate_image(gemini, "a cat", pollinations_client=pollinations)
        )

        self.assertFalse(result["success"])
        self.assertIn("gemini down", result["error"])
        self.assertIn("pollinations down", result["error"])

    def test_fails_when_no_provider_configured(self) -> None:
        result = asyncio.run(image_tools.generate_image(None, "a cat", pollinations_client=None))

        self.assertFalse(result["success"])

    def test_uploads_to_wordpress_when_available(self) -> None:
        gemini = _FakeImageClient(image_bytes=b"gemini-bytes")
        wordpress = _FakeWordPressClient(url="https://example.com/img.png", media_id=7)

        result = asyncio.run(
            image_tools.generate_image(gemini, "a cat", wordpress_client=wordpress)
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["public_url"], "https://example.com/img.png")
        self.assertEqual(result["data"]["wordpress_media_id"], 7)

    def test_dry_run_reports_pollinations_when_gemini_unavailable(self) -> None:
        pollinations = _FakeImageClient()

        result = asyncio.run(
            image_tools.generate_image(
                None, "a cat", pollinations_client=pollinations, dry_run=True
            )
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["platform"], "pollinations")
        self.assertEqual(len(pollinations.calls), 0)

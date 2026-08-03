from __future__ import annotations

import asyncio
import io
import sys
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tools.image_tools as image_tools
from mcp.server.fastmcp import Image


def _make_png_bytes(size: tuple[int, int] = (4, 4)) -> bytes:
    from PIL import Image as PILImage

    buffer = io.BytesIO()
    PILImage.new("RGB", size, color=(200, 30, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def _make_noisy_png_bytes(size: tuple[int, int]) -> bytes:
    """A solid-color PNG of any size compresses to near-nothing, so a real
    payload-size test needs actual pixel entropy — random noise won't
    compress away, giving a realistically large file like an actual photo."""
    import random

    from PIL import Image as PILImage

    rng = random.Random(0)
    width, height = size
    pixel_data = bytes(rng.getrandbits(8) for _ in range(width * height * 3))
    buffer = io.BytesIO()
    PILImage.frombytes("RGB", size, pixel_data).save(buffer, format="PNG")
    return buffer.getvalue()


class _FakeProviderClient:
    """Stands in for CloudflareWorkerImageClient / HuggingFaceFluxClient /
    PollinationsImageClient — all three share the same generate_image(prompt,
    aspect_ratio) -> (bytes, mime_type) interface."""

    def __init__(self, *, image_bytes: bytes | None = None, mime_type="image/png", error=None):
        self._image_bytes = image_bytes if image_bytes is not None else _make_png_bytes()
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


class GenerateImageTests(TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        patcher = patch("tools.image_tools._OUTPUT_DIR", Path(self._tmpdir.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    # -- provider fallback chain (Cloudflare -> Hugging Face -> Pollinations) --

    def test_uses_cloudflare_when_it_succeeds_and_never_calls_others(self) -> None:
        cloudflare = _FakeProviderClient(image_bytes=_make_png_bytes(), mime_type="image/png")
        huggingface = _FakeProviderClient()
        pollinations = _FakeProviderClient()

        data, preview = asyncio.run(
            image_tools.generate_image(
                "a cat",
                cloudflare_client=cloudflare,
                huggingface_client=huggingface,
                pollinations_client=pollinations,
            )
        )

        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["provider"], "cloudflare")
        self.assertNotIn("fallback_reason", data["data"])
        self.assertEqual(len(cloudflare.calls), 1)
        self.assertEqual(len(huggingface.calls), 0)
        self.assertEqual(len(pollinations.calls), 0)
        self.assertIsInstance(preview, Image)

    def test_falls_back_to_huggingface_when_cloudflare_fails(self) -> None:
        cloudflare = _FakeProviderClient(error=RuntimeError("worker down"))
        huggingface = _FakeProviderClient(image_bytes=_make_png_bytes(), mime_type="image/png")
        pollinations = _FakeProviderClient()

        data, preview = asyncio.run(
            image_tools.generate_image(
                "a cat",
                cloudflare_client=cloudflare,
                huggingface_client=huggingface,
                pollinations_client=pollinations,
            )
        )

        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["provider"], "huggingface")
        self.assertIn("worker down", data["data"]["fallback_reason"])
        self.assertEqual(len(huggingface.calls), 1)
        self.assertEqual(len(pollinations.calls), 0)
        self.assertIsInstance(preview, Image)

    def test_falls_back_to_pollinations_when_cloudflare_and_huggingface_fail(self) -> None:
        cloudflare = _FakeProviderClient(error=RuntimeError("worker down"))
        huggingface = _FakeProviderClient(error=RuntimeError("space asleep"))
        pollinations = _FakeProviderClient(image_bytes=b"pollinations-jpeg", mime_type="image/jpeg")

        data, preview = asyncio.run(
            image_tools.generate_image(
                "a cat",
                cloudflare_client=cloudflare,
                huggingface_client=huggingface,
                pollinations_client=pollinations,
            )
        )

        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["provider"], "pollinations")
        self.assertIn("worker down", data["data"]["fallback_reason"])
        self.assertEqual(len(pollinations.calls), 1)
        self.assertIsInstance(preview, Image)

    def test_fails_when_all_providers_fail(self) -> None:
        cloudflare = _FakeProviderClient(error=RuntimeError("worker down"))
        huggingface = _FakeProviderClient(error=RuntimeError("space asleep"))
        pollinations = _FakeProviderClient(error=RuntimeError("pollinations down"))

        data, preview = asyncio.run(
            image_tools.generate_image(
                "a cat",
                cloudflare_client=cloudflare,
                huggingface_client=huggingface,
                pollinations_client=pollinations,
            )
        )

        self.assertFalse(data["success"])
        self.assertIn("worker down", data["error"])
        self.assertIn("space asleep", data["error"])
        self.assertIn("pollinations down", data["error"])
        self.assertIsNone(preview)

    def test_fails_when_no_provider_configured(self) -> None:
        data, preview = asyncio.run(image_tools.generate_image("a cat"))

        self.assertFalse(data["success"])
        self.assertIsNone(preview)

    # -- scenario A: plain generation, no WordPress upload --

    def test_scenario_a_generates_without_uploading_to_wordpress(self) -> None:
        cloudflare = _FakeProviderClient(image_bytes=_make_png_bytes(), mime_type="image/png")
        wordpress = _FakeWordPressClient()

        data, preview = asyncio.run(
            image_tools.generate_image(
                "a red apple",
                cloudflare_client=cloudflare,
                wordpress_client=wordpress,
                upload_to_wordpress=False,
            )
        )

        self.assertTrue(data["success"])
        self.assertTrue(Path(data["data"]["local_path"]).exists())
        self.assertNotIn("public_url", data["data"])
        self.assertEqual(len(wordpress.uploaded), 0)
        self.assertIsInstance(preview, Image)

    # -- scenario B: generation + WordPress upload for cross-posting --

    def test_scenario_b_uploads_to_wordpress_and_returns_public_url(self) -> None:
        cloudflare = _FakeProviderClient(image_bytes=_make_png_bytes(), mime_type="image/png")
        wordpress = _FakeWordPressClient(url="https://example.com/img.png", media_id=7)

        data, preview = asyncio.run(
            image_tools.generate_image(
                "AI technology news illustration",
                cloudflare_client=cloudflare,
                wordpress_client=wordpress,
                upload_to_wordpress=True,
            )
        )

        self.assertTrue(data["success"])
        self.assertTrue(Path(data["data"]["local_path"]).exists())
        self.assertEqual(data["data"]["public_url"], "https://example.com/img.png")
        self.assertEqual(data["data"]["wordpress_media_id"], 7)
        self.assertEqual(len(wordpress.uploaded), 1)
        self.assertIsInstance(preview, Image)

    # -- scenario C: Cloudflare and Hugging Face fail, Pollinations works --

    def test_scenario_c_full_fallback_to_pollinations(self) -> None:
        cloudflare = _FakeProviderClient(error=RuntimeError("quota exceeded"))
        huggingface = _FakeProviderClient(error=RuntimeError("space asleep"))
        pollinations = _FakeProviderClient(image_bytes=_make_png_bytes(), mime_type="image/png")

        data, preview = asyncio.run(
            image_tools.generate_image(
                "a cat",
                cloudflare_client=cloudflare,
                huggingface_client=huggingface,
                pollinations_client=pollinations,
            )
        )

        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["provider"], "pollinations")
        self.assertTrue(Path(data["data"]["local_path"]).exists())
        self.assertIsInstance(preview, Image)

    # -- scenario D: ImageContent construction fails, publishing data survives --

    def test_scenario_d_preview_failure_is_non_fatal(self) -> None:
        cloudflare = _FakeProviderClient(image_bytes=_make_png_bytes(), mime_type="image/png")

        with patch("tools.image_tools.Image", side_effect=RuntimeError("boom")):
            data, preview = asyncio.run(
                image_tools.generate_image("a cat", cloudflare_client=cloudflare)
            )

        self.assertTrue(data["success"])
        self.assertTrue(Path(data["data"]["local_path"]).exists())
        self.assertIn("mcp_preview_error", data["data"])
        self.assertIsNone(preview)

    # -- scenario E: large image gets downscaled for the MCP preview only --

    def test_scenario_e_large_image_downscaled_for_preview_only(self) -> None:
        large_png = _make_noisy_png_bytes(size=(900, 900))
        self.assertGreater(len(large_png), image_tools._MCP_PREVIEW_MAX_BYTES)

        cloudflare = _FakeProviderClient(image_bytes=large_png, mime_type="image/png")

        data, preview = asyncio.run(
            image_tools.generate_image("a big image", cloudflare_client=cloudflare)
        )

        self.assertTrue(data["success"])
        # The file used for publishing keeps the full original bytes, untouched.
        saved_bytes = Path(data["data"]["local_path"]).read_bytes()
        self.assertEqual(len(saved_bytes), len(large_png))
        self.assertEqual(data["data"]["size_bytes"], len(large_png))

        # The MCP preview is a separate, smaller re-encode.
        self.assertIsInstance(preview, Image)
        preview_content = preview.to_image_content()
        import base64

        preview_bytes = base64.b64decode(preview_content.data)
        self.assertLess(len(preview_bytes), len(large_png))
        self.assertEqual(preview_content.mimeType, "image/jpeg")

    # -- dry run --

    def test_dry_run_reports_first_available_provider(self) -> None:
        pollinations = _FakeProviderClient()

        data, preview = asyncio.run(
            image_tools.generate_image(
                "a cat", pollinations_client=pollinations, dry_run=True
            )
        )

        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["platform"], "pollinations")
        self.assertEqual(len(pollinations.calls), 0)
        self.assertIsNone(preview)

    # -- real MIME detection from file signature --

    def test_mime_type_is_detected_from_file_signature_not_provider_label(self) -> None:
        cloudflare = _FakeProviderClient(image_bytes=_make_png_bytes(), mime_type="image/jpeg")

        data, _preview = asyncio.run(
            image_tools.generate_image("a cat", cloudflare_client=cloudflare)
        )

        self.assertEqual(data["data"]["mime_type"], "image/png")

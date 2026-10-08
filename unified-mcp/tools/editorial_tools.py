"""Protected editorial workflow; accepts identifiers, never publish-time content."""
from __future__ import annotations

import io
import time
from urllib.parse import urlsplit

import httpx
from PIL import Image

from clients.gcs_queue_client import QueueConflictError
from core import editorial as flow
from core.temp_image_tokens import mint
from tools.gcs_temp_storage_tools import _pick_estuary_url

MAX_BYTES = 12 * 1024 * 1024


async def guard_generic(queue, non_editorial, text, image_url=None):
    """Keep generic publishing available, but never infer an exemption for queue work."""
    if queue is None:
        return
    flow.check(non_editorial is True, "Noticias de cola: usa editorial_publish. Para contenido ajeno declara non_editorial=true.")
    for summary in await queue.list_items():
        item = await queue.get_item(summary["id"])
        e = item.get("editorial", {})
        texts = [item["contenido_markdown"].strip()]
        texts += [p.get("text", p.get("content", "")).strip() for p in e.get("payloads", {}).values()]
        flow.check(item["id"] not in text and not any(t and t == text.strip() for t in texts),
                   "Contenido de cola detectado: usa editorial_publish.")
        if image_url:
            flow.check(image_url != (e.get("image") or {}).get("source_url") and "/editorial-asset/" not in image_url,
                       "Activo editorial: usa editorial_publish.")


async def download_image(url):
    # Deliberately narrow: no internal URLs, credentials, arbitrary redirects or local files.
    allowed = ("chatgpt.com", "oaiusercontent.com", "wordpress.com", "wp.com")
    for _ in range(6):
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        flow.check(parsed.scheme == "https" and not parsed.username and not parsed.password
                   and parsed.port in (None, 443)
                   and any(host == d or host.endswith("." + d) for d in allowed),
                   "Origen no permitido. Usa ChatGPT Share o un activo HTTPS de WordPress/OpenAI.")
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            async with client.stream("GET", url) as response:
                if response.is_redirect:
                    from urllib.parse import urljoin
                    url = urljoin(url, response.headers["location"])
                    continue
                response.raise_for_status()
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    flow.check(len(data) <= MAX_BYTES, "Imagen/página demasiado grande.")
                if "text/html" in response.headers.get("content-type", ""):
                    candidate = _pick_estuary_url(bytes(data).decode("utf-8", errors="replace"))
                    flow.check(candidate is not None, "Enlace compartido sin imagen verificable.")
                    url = candidate
                    continue
                with Image.open(io.BytesIO(data)) as image:
                    flow.check(image.format in ("JPEG", "PNG", "WEBP") and image.width * image.height <= 25_000_000,
                               "Formato/dimensiones no admitidos.")
                    mime = Image.MIME[image.format]
                    image.verify()
                return bytes(data), mime
    raise flow.EditorialError("Demasiadas redirecciones; imagen no verificable.")


class EditorialService:
    def __init__(self, queue, context=None, base_url=""):
        self.queue = queue
        self.context = context or {}
        self.base_url = base_url.rstrip("/")

    async def resolve(self, fecha_prevista=None, news_id=None):
        if news_id:
            item = await self.queue.get_item(news_id)
        else:
            flow.check(bool(fecha_prevista), "Indica fecha local explícita YYYY-MM-DD o news_id.")
            candidates = [x for x in await self.queue.list_items() if x.get("fecha_prevista") == fecha_prevista]
            flow.check(len(candidates) == 1, "Fecha sin noticia inequívoca; solicita aclaración.")
            item = await self.queue.get_item(candidates[0]["id"])
        flow.active(item)
        return item

    async def prepare(self, news_id, expected_version, payloads, actor):
        return await self.queue.transition(news_id, expected_version,
                                           lambda item: flow.begin(item, payloads, actor))

    async def bind(self, news_id, expected_version, generation_id, source_url, actor):
        # Check identity before making any download/storage side effect.
        item = await self.queue.get_item(news_id)
        flow.active(item)
        flow.check(item["version"] == expected_version, "Versión obsoleta.")
        flow.check(item.get("editorial", {}).get("generation_id") == generation_id, "Generación incorrecta.")
        data, mime = await download_image(source_url)
        asset = await self.queue.store_asset(news_id, data, mime, source_url)
        return await self.queue.transition(news_id, expected_version,
                                           lambda item: flow.bind(item, generation_id, asset, actor))

    async def review_link(self, news_id):
        item = await self.queue.get_item(news_id)
        flow.active(item)
        e = item.get("editorial", {})
        flow.check(e.get("image") and self.base_url, "Falta imagen/base URL pública.")
        await self.queue.read_asset(e["image"])
        token = mint("editorial-review:" + news_id + ":" + e["review_id"], int(time.time()) + 1800)
        return {"review_url": self.base_url + "/editorial-review/" + token,
                "instruction": "El usuario debe abrir el enlace, inspeccionar la imagen y autorizar. "
                               "Los agentes nunca rellenan ni envían este formulario."}

    def asset_url(self, item):
        e = item["editorial"]
        token = mint("editorial-asset:" + item["id"] + ":" + e["image"]["sha256"], int(time.time()) + 3600)
        return self.base_url + "/editorial-asset/" + token

    async def publish(self, news_id, news_revision, image_revision, channel, actor, dry_run=False):
        item = await self.queue.get_item(news_id)
        flow.validate(item, news_revision, image_revision, channel)
        flow.check(channel in self.context and self.base_url, "Canal/base URL no configurado.")
        payload = dict(item["editorial"]["payloads"][channel])
        if channel != "wordpress" and "wordpress" in item["editorial"]["payloads"]:
            flow.check(item.get("canales", {}).get("wordpress", {}).get("estado") == "publicado",
                       "Publica y confirma WordPress primero.")
        if any("[WORDPRESS_URL]" in value for value in payload.values()):
            wp = item.get("canales", {}).get("wordpress", {})
            flow.check(wp.get("estado") == "publicado" and wp.get("url", "").startswith("https://"),
                       "Falta URL WordPress confirmada; no se publican placeholders.")
            payload = {key: value.replace("[WORDPRESS_URL]", wp["url"]) for key, value in payload.items()}
        await self.queue.read_asset(item["editorial"]["image"])
        if dry_run:
            return {"dry_run": True, "validated": True, "news_id": news_id, "channel": channel}
        def reservation(current):
            flow.reserve(current, news_revision, image_revision, channel, actor)
            current["editorial"]["attempts"][channel]["rendered_payload"] = payload
            current["editorial"]["attempts"][channel]["rendered_payload_hash"] = flow.digest(payload)
        item = await self.queue.transition(news_id, item["version"], reservation)
        # Any exception/cancellation after reservation is uncertain, never automatically replayed.
        try:
            result = await self._dispatch(channel, payload, self.asset_url(item))
        except Exception:
            result = {"success": False, "error": "API externa incierta; reconciliar manualmente."}
        for _ in range(5):
            current = await self.queue.get_item(news_id)
            try:
                saved = await self.queue.transition(news_id, current["version"],
                                                    lambda value: flow.finish(value, channel, result))
                return {"attempt": saved["editorial"]["attempts"][channel], "canales": saved["canales"]}
            except QueueConflictError:
                continue
        # Return evidence so an operator can reconcile even if GCS cannot save the receipt.
        return {"reconciliation_required": True, "external_result": result,
                "attempt_key": item["editorial"]["attempts"][channel]["key"]}

    async def _dispatch(self, channel, payload, image_url):
        # Existing clients use connection-only retries on non-idempotent publication calls.
        if channel == "wordpress":
            from tools.wordpress_tools import publish_post
            return await publish_post(self.context[channel], payload["title"], payload["content"], image_url=image_url)
        if channel == "linkedin":
            from tools.linkedin_tools import publish_post
            return await publish_post(self.context[channel], self.context["linkedin_person_urn"], payload["text"], image_url)
        if channel == "x":
            from tools.x_tools import post_to_x
            return await post_to_x(self.context[channel], payload["text"])
        if channel == "threads":
            from tools.threads_tools import publish_post
            return await publish_post(self.context[channel], payload["text"])
        import importlib
        module = importlib.import_module("tools." + channel + "_tools")
        return await module.publish_post(self.context[channel], payload["text"], image_url)


async def result_of(awaitable):
    try:
        return {"success": True, "data": await awaitable, "error": None}
    except Exception as exc:
        # No response bodies, signed links or platform credentials in failures.
        message = str(exc) if isinstance(exc, (flow.EditorialError, QueueConflictError)) else type(exc).__name__
        return {"success": False, "data": None, "error": message}

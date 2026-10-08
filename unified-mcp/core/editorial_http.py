"""Human-only review UI and immutable asset proxy, outside the MCP tool surface."""
from __future__ import annotations

import html
import json
from urllib.parse import parse_qs

from core import editorial as flow
from core.temp_image_tokens import verify


def reconcile(item, channel, actor, evidence, published, external_id="", url=""):
    e = item.get("editorial", {})
    attempt = e.get("attempts", {}).get(channel)
    flow.check(attempt and attempt["state"] in ("reserved", "uncertain"), "Intento no reconciliable.")
    flow.check(len(evidence.strip()) >= 15, "Describe la comprobación manual en la plataforma.")
    # Keep the complete receipt, including negative evidence, before allowing a new reservation.
    receipt = {"attempt": dict(attempt), "channel": channel, "actor": actor, "at": flow.now(),
               "evidence": evidence, "published": published, "external_id": external_id, "url": url}
    if published:
        flow.check(bool(external_id.strip()) and url.startswith("https://"), "ID y URL confirmados obligatorios.")
        keys = {"facebook": "post_id", "instagram": "media_id", "threads": "thread_id",
                "linkedin": "post_urn", "wordpress": "id", "x": "tweet_id"}
        attempt["state"] = "reserved"
        flow.finish(item, channel, {"success": True, "data": {keys[channel]: external_id, "url": url,
                    "status": "publish", "manual_confirmation": receipt}})
    else:
        del e["attempts"][channel]
    item.setdefault("reconciliations", []).append(receipt)
    flow.audit(item, "manual_reconciliation:" + channel, actor)


class EditorialHTTP:
    def __init__(self, app, service):
        self.app, self.service = app, service

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        is_review = path.startswith("/editorial-review/")
        is_asset = path.startswith("/editorial-asset/")
        if scope["type"] != "http" or not (is_review or is_asset):
            return await self.app(scope, receive, send)
        try:
            method = scope.get("method")
            flow.check(method in (("GET", "POST") if is_review else ("GET",)), "Método no admitido.")
            kind, news_id, identity = verify(path.rsplit("/", 1)[1]).split(":")
            flow.check(kind == ("editorial-review" if is_review else "editorial-asset"), "Token de otra finalidad.")
            item = await self.service.queue.get_item(news_id)
            e = item.get("editorial", {})
            if is_asset:
                assets = [v.get("image") for v in [e] + item.get("editorial_versions", [])]
                asset = next((a for a in assets if a and a["sha256"] == identity), None)
                flow.check(asset is not None, "Activo no vinculado.")
                data = await self.service.queue.read_asset(asset)
                return await self.respond(send, 200, data, asset["mime_type"])
            flow.check(e.get("review_id") == identity, "Revisión obsoleta.")
            if method == "POST":
                raw = bytearray()
                while True:
                    message = await receive()
                    flow.check(message["type"] == "http.request", "Petición interrumpida.")
                    raw.extend(message.get("body", b""))
                    flow.check(len(raw) <= 16_384, "Formulario demasiado grande.")
                    if not message.get("more_body"):
                        break
                form = parse_qs(raw.decode())
                def value(k):
                    return form.get(k, [""])[0]
                flow.check(value("version") == str(item["version"]), "Noticia cambiada; vuelve a abrir el enlace.")
                if value("action") == "reconcile":
                    flow.check(value("confirmed") == "yes", "Confirma la inspección manual de la plataforma.")
                    flow.check(value("outcome") in ("published", "absent"), "Resultado obligatorio.")
                    operation = lambda current: reconcile(current, value("channel"), value("actor"),
                        value("observation"), value("outcome") == "published", value("external_id"), value("url"))
                else:
                    await self.service.queue.read_asset(e["image"])
                    operation = lambda current: flow.approve(current, identity, value("actor"), value("observation"),
                        value("semantic_match") == "yes", value("authorized") == "yes", form.get("channel", []))
                await self.service.queue.transition(news_id, item["version"], operation)
                return await self.respond(send, 200, b"Decision guardada. Este formulario no publica contenido.")
            await self.service.queue.read_asset(e["image"])
            esc = html.escape
            channels = "".join(f'<label><input type="checkbox" name="channel" value="{esc(c)}">{esc(c)}</label> '
                               for c in e["payloads"])
            pending = [c for c, a in e["attempts"].items() if a["state"] in ("reserved", "uncertain")]
            reconcile_form = ""
            if pending:
                options = "".join(f'<option>{esc(c)}</option>' for c in pending)
                reconcile_form = f'''<h2>Reconciliar un resultado incierto</h2>
<p>Comprueba la plataforma antes de decidir. No marques ausente basándote en un timeout.</p>
<pre>{esc(json.dumps(e['attempts'], ensure_ascii=False, indent=2))}</pre>
<form method="post"><input type="hidden" name="action" value="reconcile">
<input type="hidden" name="version" value="{item['version']}">
<select name="channel">{options}</select><select name="outcome" required>
<option value="">Resultado</option><option value="published">Publicación confirmada</option>
<option value="absent">Ausencia comprobada; permitir otro intento</option></select>
<input name="actor" placeholder="Tu nombre" required><input name="external_id" placeholder="ID externo">
<input name="url" type="url" placeholder="URL publicada"><textarea name="observation" minlength="15" required
placeholder="Qué comprobaste y dónde"></textarea><label><input type="checkbox" name="confirmed" value="yes" required>
He comprobado personalmente este resultado</label><button>Guardar reconciliación</button></form>'''
            document = f'''<!doctype html><html lang="es"><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>Revisión editorial</title>
<style>body{{font:17px system-ui;max-width:900px;margin:30px auto;padding:16px;background:#111827;color:#f9fafb}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere}}img{{max-width:100%}}input,textarea,button,select{{padding:10px;margin:8px}}
textarea{{display:block;width:90%}}label{{display:block}}button{{cursor:pointer}}</style>
<h1>Revisar {esc(news_id)}</h1><p>Noticia r{e['news_revision']} · Imagen r{e['image_revision']}</p>
<p>Esta página es para el usuario. Ningún agente debe cumplimentarla.</p>
<pre>{esc(item['contenido_markdown'])}</pre><img src="{esc(self.service.asset_url(item))}" alt="Imagen pendiente de revisión">
<p>Origen: {esc(e['image']['source_url'])}</p><h2>Contenido exacto por canal</h2>
<pre>{esc(json.dumps(e['payloads'], ensure_ascii=False, indent=2))}</pre>
<form method="post"><input type="hidden" name="version" value="{item['version']}">
<input name="actor" placeholder="Tu nombre" required><textarea name="observation" minlength="15" required
placeholder="Describe lo que ves y cómo corresponde a esta noticia"></textarea>
<label><input type="checkbox" name="semantic_match" value="yes" required>He visto la imagen y corresponde a esta noticia.
Si no se muestra o representa otra noticia, no aprobar.</label>{channels}
<label><input type="checkbox" name="authorized" value="yes" required>Apruebo imagen y textos y autorizo expresamente
su publicación en los canales seleccionados.</label><button>Guardar aprobación</button></form>{reconcile_form}</html>'''
            await self.respond(send, 200, document.encode(), "text/html; charset=utf-8")
        except Exception:
            await self.respond(send, 409, "Operación bloqueada: enlace caducado, revisión cambiada, activo inaccesible o confirmación incompleta. Vuelve a consultar la cola.".encode())

    @staticmethod
    async def respond(send, status, data, mime="text/plain; charset=utf-8"):
        await send({"type": "http.response.start", "status": status, "headers": [
            (b"content-type", mime.encode()), (b"cache-control", b"no-store"),
            (b"referrer-policy", b"no-referrer"), (b"x-content-type-options", b"nosniff"),
            (b"content-security-policy", b"default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'")]})
        await send({"type": "http.response.body", "body": data})

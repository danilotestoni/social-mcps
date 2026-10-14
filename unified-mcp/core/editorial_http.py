"""Human review UI and immutable asset proxy, outside the MCP tool surface."""
from __future__ import annotations

import html
import re
from urllib.parse import parse_qs

from core import editorial as flow
from core.temp_image_tokens import TempImageTokenError, verify

CHANNEL_LABELS = {"wordpress": "WordPress", "linkedin": "LinkedIn", "facebook": "Facebook",
                  "instagram": "Instagram", "threads": "Threads", "x": "X"}
_RESULT_KEYS = {"facebook": "post_id", "instagram": "media_id", "threads": "thread_id",
                "linkedin": "post_urn", "wordpress": "id", "x": "tweet_id"}
_DEFAULT_ACTOR = "Usuario"
_DEFAULT_EVIDENCE = "Comprobado por el usuario en la plataforma."


def derive_external_id(channel, url):
    """Best-effort ID from a public permalink; falls back to the URL itself."""
    patterns = {"x": r"/status/(\d+)", "threads": r"/post/([\w-]+)", "linkedin": r"(urn:li:\w+:\d+)"}
    match = re.search(patterns.get(channel, r"$^"), url)
    if match:
        return match.group(1)
    if channel == "linkedin":
        activity = re.search(r"activity[-:](\d+)", url)
        if activity:
            return "urn:li:activity:" + activity.group(1)
    return url


def reconcilable_channels(item):
    """Prepared channels that are not confirmed yet: uncertain/reserved attempts or never attempted."""
    e = item.get("editorial", {})
    canales = item.get("canales", {})
    result = {}
    for channel in e.get("payloads", {}):
        if canales.get(channel, {}).get("estado") in ("publicado", "publicada"):
            continue
        attempt = e.get("attempts", {}).get(channel)
        if attempt is None or attempt.get("state") in ("reserved", "uncertain"):
            result[channel] = attempt
    return result


def reconcile(item, channel, actor, evidence, published, external_id="", url=""):
    e = item.get("editorial", {})
    flow.check(channel in e.get("payloads", {}), "Canal no preparado para esta noticia: " + str(channel))
    flow.check(channel in reconcilable_channels(item), "Canal ya confirmado o sin resultado pendiente: " + channel)
    actor = (actor or "").strip() or _DEFAULT_ACTOR
    evidence = (evidence or "").strip() or _DEFAULT_EVIDENCE
    url = (url or "").strip()
    attempts = e.setdefault("attempts", {})
    attempt = attempts.get(channel)
    receipt = {"attempt": dict(attempt) if attempt else None, "channel": channel, "actor": actor,
               "at": flow.now(), "evidence": evidence, "published": published, "url": url}
    if published:
        flow.check(url.startswith("https://"), "Falta la URL https de la publicación en " + CHANNEL_LABELS.get(channel, channel))
        external_id = (external_id or "").strip() or derive_external_id(channel, url)
        receipt["external_id"] = external_id
        if attempt is None:
            # Published outside the server (e.g. X from the user's machine): record it as a manual attempt.
            attempt = attempts[channel] = {"key": flow.digest([item["id"], e.get("news_revision"), channel]),
                                           "state": "reserved", "at": flow.now(), "actor": actor, "manual": True}
        attempt["state"] = "reserved"
        flow.finish(item, channel, {"success": True, "data": {_RESULT_KEYS[channel]: external_id, "url": url,
                    "status": "publish", "manual_confirmation": receipt}})
    else:
        flow.check(attempt is not None, "No hay intento que liberar en " + CHANNEL_LABELS.get(channel, channel))
        del attempts[channel]
    item.setdefault("reconciliations", []).append(receipt)
    flow.audit(item, "manual_reconciliation:" + channel, actor)


def reconcile_many(item, entries, actor=""):
    """Apply several channel outcomes atomically: [{channel, outcome: published|absent, url?, external_id?, evidence?}]."""
    flow.check(isinstance(entries, list) and entries, "Indica al menos un canal que conciliar.")
    channels = [entry.get("channel") for entry in entries]
    flow.check(len(channels) == len(set(channels)), "Canal repetido en la conciliación.")
    for entry in entries:
        outcome = entry.get("outcome")
        flow.check(outcome in ("published", "absent"), "Resultado debe ser published o absent.")
        reconcile(item, entry.get("channel"), entry.get("actor") or actor, entry.get("evidence", ""),
                  outcome == "published", entry.get("external_id", ""), entry.get("url", ""))


# ── Presentation ───────────────────────────────────────────────────────────────

_CSS = """
:root{--bg:#f4f5f7;--card:#fff;--text:#14161a;--muted:#5d6470;--line:#e2e5ea;--accent:#2457d6;
--accent-text:#fff;--ok:#127a3c;--ok-bg:#e5f5ec;--warn:#8a5a00;--warn-bg:#fff4dc;--bad:#b42318;--bad-bg:#fdecea;
--chip:#eef1f6;color-scheme:light dark}
@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--card:#181b21;--text:#eceef2;--muted:#9aa2ae;
--line:#2a2f38;--accent:#5b8cff;--accent-text:#0b0d10;--ok:#58d38c;--ok-bg:#12291c;--warn:#f2c14e;
--warn-bg:#2c2412;--bad:#ff8a80;--bad-bg:#2e1614;--chip:#232833}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:720px;margin:0 auto;padding:16px 16px 120px}
header{margin:8px 0 16px}.eyebrow{font-size:13px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
h1{font-size:22px;line-height:1.25;margin:4px 0 6px}h2{font-size:17px;margin:0 0 10px}
.meta{font-size:14px;color:var(--muted)}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin:0 0 14px}
.hero{padding:0;overflow:hidden}.hero img{display:block;width:100%;height:auto}
.hero p{margin:0;padding:8px 14px;font-size:12px;color:var(--muted);overflow-wrap:anywhere}
.banner{border-radius:12px;padding:12px 14px;margin:0 0 14px;font-size:15px}
.banner.ok{background:var(--ok-bg);color:var(--ok)}.banner.warn{background:var(--warn-bg);color:var(--warn)}
.banner.bad{background:var(--bad-bg);color:var(--bad)}
.channel{border-top:1px solid var(--line);padding:12px 0}.channel:first-of-type{border-top:0;padding-top:0}
.row{display:flex;align-items:center;gap:10px;justify-content:space-between}
.pick{display:flex;align-items:center;gap:10px;font-weight:600;min-height:44px;cursor:pointer}
.pick input{width:22px;height:22px;accent-color:var(--accent)}
.badge{font-size:12px;padding:3px 9px;border-radius:999px;background:var(--chip);color:var(--muted);white-space:nowrap}
.badge.ok{background:var(--ok-bg);color:var(--ok)}.badge.warn{background:var(--warn-bg);color:var(--warn)}
details summary{cursor:pointer;color:var(--accent);font-size:14px;min-height:36px;display:flex;align-items:center}
.text{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--chip);border-radius:10px;padding:10px 12px;
font-size:15px;margin:6px 0 0}.text b{display:block;margin-bottom:6px}
.count{font-size:12px;color:var(--muted);margin-top:4px}.count.over{color:var(--bad)}
label.field{display:block;font-size:14px;color:var(--muted);margin:10px 0 4px}
input[type=text],input[type=url],textarea{width:100%;font:inherit;color:var(--text);background:var(--bg);
border:1px solid var(--line);border-radius:10px;padding:11px 12px}textarea{min-height:76px;resize:vertical}
.outcomes{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin:10px 0 0}
.outcomes label{display:flex;align-items:center;justify-content:center;text-align:center;min-height:44px;
border:1px solid var(--line);border-radius:10px;font-size:14px;cursor:pointer;padding:6px}
.outcomes input{position:absolute;opacity:0;pointer-events:none}
.outcomes input:checked+span{font-weight:700}.outcomes label:has(input:checked){border-color:var(--accent);
background:var(--chip)}
.bar{position:fixed;left:0;right:0;bottom:0;background:var(--card);border-top:1px solid var(--line);
padding:12px 16px calc(12px + env(safe-area-inset-bottom))}.bar div{max-width:720px;margin:0 auto}
button{width:100%;min-height:50px;border:0;border-radius:12px;font:600 17px system-ui,sans-serif;
background:var(--accent);color:var(--accent-text);cursor:pointer}button.secondary{background:var(--chip);color:var(--text)}
button:disabled{opacity:.45;cursor:not-allowed}.hint{font-size:13px;color:var(--muted);margin:8px 0 0;text-align:center}
.inline-action{margin-top:12px}.bar.static{position:static;background:none;border:0;padding:0}
@media (min-width:900px){main{padding-top:32px}.bar{position:static;background:none;border:0;padding:0}
.bar div{max-width:none}}
"""


def _page(title, body):
    return (f'<!doctype html><html lang="es"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            f'<meta name="robots" content="noindex"><title>{html.escape(title)}</title>'
            f'<style>{_CSS}</style></head><body><main>{body}</main></body></html>').encode()


def message_page(title, text, tone="ok", detail=""):
    esc = html.escape
    extra = f'<p class="meta">{esc(detail)}</p>' if detail else ""
    return _page(title, f'<header><div class="eyebrow">Revisión editorial</div><h1>{esc(title)}</h1></header>'
                        f'<div class="banner {tone}">{esc(text)}</div>{extra}')


def _payload_text(channel, payload, wordpress_url):
    if channel == "wordpress":
        return payload.get("title", ""), payload.get("content", "")
    text = payload.get("text", "")
    if wordpress_url:
        text = text.replace("[WORDPRESS_URL]", wordpress_url)
    return "", text


def _channel_status(item, channel):
    estado = item.get("canales", {}).get(channel, {}).get("estado")
    attempt = item.get("editorial", {}).get("attempts", {}).get(channel) or {}
    if estado in ("publicado", "publicada"):
        return "ok", "Publicado"
    if attempt.get("state") in ("reserved", "uncertain"):
        return "warn", "Incierto"
    return "", "Pendiente"


def render_review(item, asset_url):
    esc = html.escape
    e = item["editorial"]
    payloads = e["payloads"]
    wp = item.get("canales", {}).get("wordpress", {})
    wordpress_url = wp.get("url") if wp.get("estado") == "publicado" else ""
    title = payloads.get("wordpress", {}).get("title") or item["id"]
    approval = e.get("approval") or {}
    approved_now = bool(approval) and approval.get("snapshot") == flow.snapshot(e)
    pending = reconcilable_channels(item)
    uncertain = [c for c, a in pending.items() if a and a.get("state") in ("reserved", "uncertain")]
    published = [c for c in payloads if _channel_status(item, c)[1] == "Publicado"]
    if not (e.get("attempts") or published):
        pending = {}  # Nothing has been published yet: reconciliation would only be noise.

    parts = [(f'<header><div class="eyebrow">Revisión editorial · {esc(item.get("fecha_prevista") or "")}</div>'
              f'<h1>{esc(title)}</h1><div class="meta">{esc(item["id"])} · noticia r{e["news_revision"]}'
              f' · imagen r{e["image_revision"]}</div></header>')]
    if approved_now:
        when = esc((approval.get("at") or "")[:16].replace("T", " "))
        names = ", ".join(CHANNEL_LABELS.get(c, c) for c in approval.get("channels", []))
        parts.append(f'<div class="banner ok">Aprobada {when} UTC para: {esc(names)}.</div>')
    if published:
        parts.append(f'<div class="banner ok">Ya publicada en: '
                     f'{esc(", ".join(CHANNEL_LABELS.get(c, c) for c in published))}.</div>')

    parts.append(f'<section class="card hero"><img src="{esc(asset_url)}" alt="Imagen propuesta para la noticia">'
                 f'<p>Origen: {esc(e["image"]["source_url"])}</p></section>')

    # Reconciliation first when something is uncertain: approval is locked until it is resolved.
    if pending:
        rows = []
        for channel, attempt in pending.items():
            tone, label = _channel_status(item, channel)
            absent = (f'<label><input type="radio" name="outcome_{esc(channel)}" value="absent">'
                      f'<span>No publicado</span></label>' if attempt else '<label style="visibility:hidden"></label>')
            rows.append(
                f'<div class="channel"><div class="row"><strong>{esc(CHANNEL_LABELS.get(channel, channel))}</strong>'
                f'<span class="badge {tone}">{label}</span></div>'
                f'<div class="outcomes"><label><input type="radio" name="outcome_{esc(channel)}" value="" checked>'
                f'<span>Sin cambios</span></label><label><input type="radio" name="outcome_{esc(channel)}" '
                f'value="published"><span>Publicado</span></label>{absent}</div>'
                f'<label class="field" for="url_{esc(channel)}">URL del post (si está publicado)</label>'
                f'<input type="url" id="url_{esc(channel)}" name="url_{esc(channel)}" inputmode="url" '
                f'placeholder="https://…" autocomplete="off"></div>')
        intro = ("Marca solo los canales que hayas comprobado. Puedes conciliar varios a la vez; "
                 "el ID se obtiene de la URL.")
        parts.append(f'<section class="card"><h2>Conciliar canales</h2><p class="meta">{intro}</p>'
                     f'<form method="post"><input type="hidden" name="action" value="reconcile">'
                     f'<input type="hidden" name="version" value="{item["version"]}">{"".join(rows)}'
                     f'<div class="inline-action"><button class="secondary">Guardar conciliación</button></div>'
                     f'</form></section>')

    cards = []
    for channel, payload in payloads.items():
        tone, label = _channel_status(item, channel)
        heading, text = _payload_text(channel, payload, wordpress_url)
        is_published = label == "Publicado"
        checked = "" if is_published else " checked"
        disabled = " disabled" if is_published else ""
        count = ""
        if channel == "x":
            over = " over" if len(text) > 280 else ""
            count = f'<div class="count{over}">{len(text)}/280 caracteres</div>'
        body = (f'<b>{esc(heading)}</b>' if heading else "") + esc(text)
        cards.append(
            f'<div class="channel"><div class="row"><label class="pick"><input type="checkbox" name="channel" '
            f'value="{esc(channel)}"{checked}{disabled}>{esc(CHANNEL_LABELS.get(channel, channel))}</label>'
            f'<span class="badge {tone}">{label}</span></div>'
            f'<details><summary>Ver texto</summary><div class="text">{body}</div>{count}</details></div>')

    locked = bool(uncertain)
    hint = ("Concilia primero los canales inciertos para poder aprobar." if locked else
            "Al aprobar confirmas que la imagen corresponde a esta noticia y autorizas los canales marcados.")
    button = "Actualizar aprobación" if approved_now else "Aprobar y publicar"
    # While reconciling, the reconciliation button is the main action: never cover it with a sticky bar.
    bar_class = "bar static" if pending else "bar"
    if locked and approved_now:
        action = '<div class="banner ok">La aprobación sigue vigente; no hace falta repetirla.</div>'
    else:
        action = f'<button{" disabled" if locked else ""}>{button}</button><p class="hint">{hint}</p>'
    parts.append(
        f'<form method="post"><input type="hidden" name="action" value="approve">'
        f'<input type="hidden" name="version" value="{item["version"]}">'
        f'<section class="card"><h2>Canales y textos</h2>{"".join(cards)}</section>'
        f'<section class="card"><details><summary>Contenido completo de la cola</summary>'
        f'<div class="text">{esc(item["contenido_markdown"])}</div></details>'
        f'<details><summary>Añadir nota (opcional)</summary>'
        f'<label class="field" for="actor">Nombre</label><input type="text" id="actor" name="actor" '
        f'placeholder="Tu nombre (opcional)" autocomplete="name">'
        f'<label class="field" for="observation">Nota</label><textarea id="observation" name="observation" '
        f'placeholder="Comentario sobre la imagen o los textos"></textarea></details></section>'
        f'<div class="{bar_class}"><div>{action}</div></div></form>')
    return _page("Revisión · " + title, "".join(parts))


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
            try:
                kind, news_id, identity = verify(path.rsplit("/", 1)[1]).split(":")
            except (TempImageTokenError, ValueError) as exc:
                raise flow.EditorialError("Enlace caducado o no válido. Pide uno nuevo en el chat.") from exc
            flow.check(kind == ("editorial-review" if is_review else "editorial-asset"), "Token de otra finalidad.")
            item = await self.service.queue.get_item(news_id)
            e = item.get("editorial", {})
            if is_asset:
                assets = [v.get("image") for v in [e] + item.get("editorial_versions", [])]
                asset = next((a for a in assets if a and a["sha256"] == identity), None)
                flow.check(asset is not None, "Activo no vinculado.")
                data = await self.service.queue.read_asset(asset)
                return await self.respond(send, 200, data, asset["mime_type"])
            flow.check(e.get("review_id") == identity, "Esta revisión ya no es la vigente. Pide un enlace nuevo.")
            if method == "POST":
                form = await self._read_form(receive)
                def value(k):
                    return form.get(k, [""])[0]
                flow.check(value("version") == str(item["version"]),
                           "La noticia ha cambiado desde que abriste la página. Recárgala.")
                if value("action") == "reconcile":
                    entries = [{"channel": c, "outcome": value("outcome_" + c), "url": value("url_" + c),
                                "external_id": value("id_" + c)}
                               for c in reconcilable_channels(item) if value("outcome_" + c)]
                    flow.check(entries, "No has marcado ningún canal como publicado o no publicado.")
                    saved = await self.service.queue.transition(
                        news_id, item["version"], lambda current: reconcile_many(current, entries, value("actor")))
                    done = ", ".join(f'{CHANNEL_LABELS.get(x["channel"], x["channel"])}: '
                                     f'{"publicado" if x["outcome"] == "published" else "liberado para reintentar"}'
                                     for x in entries)
                    status = ("La noticia queda publicada en todos los canales." if saved.get("estado") == "publicada"
                              else "Vuelve al chat para continuar.")
                    return await self.respond(send, 200, message_page("Conciliación guardada", done, "ok", status),
                                              "text/html; charset=utf-8")
                # Legacy clients posted two checkboxes; the new page submits a single explicit approval action.
                decided = value("action") == "approve" or (value("semantic_match") == "yes" and value("authorized") == "yes")
                flow.check(decided, "Falta la aprobación expresa.")
                await self.service.queue.read_asset(e["image"])
                channels = form.get("channel", [])
                await self.service.queue.transition(news_id, item["version"], lambda current: flow.approve(
                    current, identity, value("actor"), value("observation"), True, True, channels))
                names = ", ".join(CHANNEL_LABELS.get(c, c) for c in channels)
                return await self.respond(send, 200, message_page(
                    "Aprobación guardada", f"Canales autorizados: {names}.", "ok",
                    "Vuelve al chat y escribe «publica» para iniciar los canales autorizados."),
                    "text/html; charset=utf-8")
            await self.service.queue.read_asset(e["image"])
            document = render_review(item, self.service.asset_url(item))
            await self.respond(send, 200, document, "text/html; charset=utf-8")
        except flow.EditorialError as exc:
            await self.respond(send, 409, message_page("No se ha podido completar", str(exc), "bad",
                                                       "No se ha guardado nada. Vuelve atrás o pide un enlace nuevo."),
                               "text/html; charset=utf-8")
        except Exception:
            await self.respond(send, 409, message_page(
                "No se ha podido completar",
                "Operación bloqueada: enlace caducado, revisión cambiada o activo inaccesible.", "bad",
                "No se ha guardado nada. Pide un enlace nuevo en el chat."), "text/html; charset=utf-8")

    @staticmethod
    async def _read_form(receive):
        raw = bytearray()
        while True:
            message = await receive()
            flow.check(message["type"] == "http.request", "Petición interrumpida.")
            raw.extend(message.get("body", b""))
            flow.check(len(raw) <= 16_384, "Formulario demasiado grande.")
            if not message.get("more_body"):
                break
        return parse_qs(raw.decode(), keep_blank_values=True)

    @staticmethod
    async def respond(send, status, data, mime="text/plain; charset=utf-8"):
        await send({"type": "http.response.start", "status": status, "headers": [
            (b"content-type", mime.encode()), (b"cache-control", b"no-store"),
            (b"referrer-policy", b"no-referrer"), (b"x-content-type-options", b"nosniff"),
            (b"content-security-policy", b"default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'")]})
        await send({"type": "http.response.body", "body": data})

"""Pure editorial transitions. Persistence must apply them with a generation CAS."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from core.models import QUEUE_CANALES


class EditorialError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def content_hash(item):
    return digest({"news_id": item["id"], "content": item["contenido_markdown"].strip()})


def check(condition, message):
    if not condition:
        raise EditorialError(message)


def active(item):
    check(item.get("estado") not in ("publicada", "descartada"), "Noticia publicada o descartada.")


def unlocked(item):
    check(not any(a["state"] in ("reserved", "uncertain")
                  for a in item.get("editorial", {}).get("attempts", {}).values()),
          "Hay un intento reservado o incierto: reconciliar antes de modificar.")


def audit(item, event, actor):
    check(bool(actor.strip()), "Responsable obligatorio.")
    item.setdefault("editorial_history", []).append({"event": event, "actor": actor, "at": now()})


def begin(item, payloads, actor):
    active(item)
    unlocked(item)
    check(isinstance(payloads, dict) and bool(payloads), "Payloads por canal obligatorios.")
    for channel, payload in payloads.items():
        check(channel in QUEUE_CANALES and isinstance(payload, dict), "Canal/payload inválido.")
        required = {"title", "content"} if channel == "wordpress" else {"text"}
        check(set(payload) == required and all(isinstance(v, str) and v.strip() for v in payload.values()),
              "Payload debe contener solo title/content (WordPress) o text (redes).")
    old = item.get("editorial", {})
    revision = item.get("news_revision", 1)
    if old and old["content_hash"] != content_hash(item):
        revision = max(revision, old["news_revision"] + 1)
    if old:
        item.setdefault("editorial_versions", []).append(old)
    item["news_revision"] = revision
    item["editorial"] = {
        "schema_version": 1, "news_id": item["id"], "news_revision": revision,
        "content_hash": content_hash(item), "payloads": payloads,
        "payload_hash": digest(payloads), "image_revision": old.get("image_revision", 0) + 1,
        "generation_id": uuid.uuid4().hex, "image": None, "approval": None,
        "attempts": {}, "created_at": now(), "created_by": actor,
        "visual_prompt": "Crea una imagen editorial fiel solo a esta noticia. No añadas marcas, "
                         "productos ni cifras ajenos. Contenido de la cola:\n" + item["contenido_markdown"],
    }
    audit(item, "generation_started", actor)


def bind(item, generation_id, asset, actor):
    active(item)
    unlocked(item)
    e = item.get("editorial", {})
    check(e.get("generation_id") == generation_id and not e.get("image"), "Generación pendiente incorrecta.")
    check(e["content_hash"] == content_hash(item), "Contenido modificado; preparar de nuevo.")
    e["image"] = dict(asset, news_id=item["id"], news_revision=e["news_revision"],
                      image_revision=e["image_revision"], bound_at=now(), bound_by=actor)
    e["review_id"] = uuid.uuid4().hex
    audit(item, "image_bound_unapproved", actor)


def snapshot(e):
    return digest({k: e[k] for k in ("news_id", "news_revision", "content_hash", "payload_hash",
                                    "image_revision", "image")})


def approve(item, review_id, actor, observation, semantic_match, authorized, channels):
    """Only called by the human review HTTP form, never registered as an MCP tool."""
    active(item)
    unlocked(item)
    e = item.get("editorial", {})
    check(e.get("review_id") == review_id and e.get("image"), "Revisión visual obsoleta.")
    check(e["content_hash"] == content_hash(item) and e["payload_hash"] == digest(e["payloads"]),
          "Contenido cambiado desde la preparación.")
    check(semantic_match is True and authorized is True, "Falta correspondencia visual o autorización expresa.")
    check(len(observation.strip()) >= 15, "Describe lo que ves y por qué corresponde a esta noticia.")
    check(channels and len(channels) == len(set(channels)) and set(channels) <= set(e["payloads"]),
          "Selecciona canales preparados.")
    e["approval"] = {"snapshot": snapshot(e), "channels": channels, "actor": actor,
                     "at": now(), "visual_observation": observation, "semantic_match": True,
                     "publication_authorized": True, "method": "human_review_form"}
    audit(item, "human_approved", actor)


def validate(item, news_revision, image_revision, channel):
    active(item)
    e = item.get("editorial", {})
    check(e.get("news_id") == item["id"], "Sin vinculación editorial; histórico no aprobado.")
    check(news_revision == e["news_revision"] == item.get("news_revision", 1), "Revisión noticia incorrecta.")
    check(image_revision == e["image_revision"], "Revisión imagen incorrecta.")
    check(e["content_hash"] == content_hash(item), "Contenido cambiado desde aprobación.")
    check(e["payload_hash"] == digest(e["payloads"]), "Payload cambiado desde aprobación.")
    image = e.get("image") or {}
    check(image.get("news_id") == item["id"] and image.get("news_revision") == news_revision
          and image.get("image_revision") == image_revision, "Imagen de otra noticia/revisión.")
    approval = e.get("approval") or {}
    check(approval.get("snapshot") == snapshot(e) and approval.get("semantic_match") is True
          and approval.get("publication_authorized") is True, "Imagen/contenido sin aprobación humana vigente.")
    check(channel in approval.get("channels", []) and channel in e["payloads"], "Canal no autorizado.")
    check(item.get("canales", {}).get(channel, {}).get("estado") not in ("publicado", "publicada"),
          "Canal ya publicado.")
    check(channel not in e["attempts"], "Intento ya reservado/registrado; requiere reconciliación.")


def reserve(item, news_revision, image_revision, channel, actor):
    validate(item, news_revision, image_revision, channel)
    e = item["editorial"]
    # Include the image revision in evidence, but never allow it to reset a published channel.
    key = digest([item["id"], news_revision, channel])
    e["attempts"][channel] = {"key": key, "state": "reserved", "at": now(), "actor": actor}
    audit(item, "reserved:" + channel, actor)


def finish(item, channel, result):
    attempt = item["editorial"]["attempts"][channel]
    check(attempt["state"] == "reserved", "El intento no está reservado.")
    data = result.get("data") or {}
    identifiers = {"wordpress": "id", "linkedin": "post_urn", "facebook": "post_id",
                   "instagram": "media_id", "threads": "thread_id", "x": "tweet_id"}
    external_id = data.get(identifiers[channel])
    confirmed = result.get("success") is True and bool(external_id)
    if channel == "wordpress":
        confirmed = confirmed and data.get("status") == "publish"
    attempt.update(state="confirmed" if confirmed else "uncertain", result=result, completed_at=now())
    if confirmed:
        item.setdefault("canales", {})[channel] = {
            "estado": "publicado", "id": str(external_id),
            "url": data.get("url") or data.get("permalink"), "error": None,
            "confirmed_at": now(), "attempt_key": attempt["key"],
        }
        if channel == "wordpress":
            item["url_wordpress"] = data.get("url")
        if all(item["canales"].get(c, {}).get("estado") == "publicado"
               for c in item["editorial"]["approval"]["channels"]):
            item.update(estado="publicada", fecha_publicada=now())
    audit(item, attempt["state"] + ":" + channel, attempt["actor"])

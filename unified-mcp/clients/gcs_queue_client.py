from __future__ import annotations

import asyncio
import datetime
import re

import yaml
from google.api_core.exceptions import NotFound, PreconditionFailed
from google.cloud import storage

from core.logger import get_logger
from core.models import QUEUE_CANALES, QUEUE_ESTADOS, QueueItemSummary

_QUEUE_PREFIX = "queue"
_ARCHIVE_PREFIX = "archive"
_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


class GCSQueueError(Exception):
    pass


class QueueNotFoundError(GCSQueueError):
    pass


class QueueAlreadyExistsError(GCSQueueError):
    pass


class QueueConflictError(GCSQueueError):
    pass


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _default_canales() -> dict:
    return {canal: {"estado": "pendiente", "id": None, "url": None, "error": None} for canal in QUEUE_CANALES}


def _parse_item_blob(text: str) -> tuple[dict, str]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise GCSQueueError("Fichero de cola sin delimitadores de frontmatter YAML (---).")
    frontmatter_raw, body = match.groups()
    try:
        frontmatter = yaml.safe_load(frontmatter_raw) or {}
    except yaml.YAMLError as exc:
        raise GCSQueueError(f"Frontmatter YAML inválido: {exc}") from exc
    if not isinstance(frontmatter, dict):
        raise GCSQueueError("El frontmatter debe ser un mapeo YAML (clave: valor).")
    return frontmatter, body.lstrip("\n")


def _render_item_blob(frontmatter: dict, body: str) -> str:
    yaml_text = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)
    return f"---\n{yaml_text}---\n\n{body.strip()}\n"


class GCSQueueClient:
    """
    Semantic storage for the shared weekly news queue — one self-contained
    Markdown+YAML-frontmatter file per item in gs://<bucket>/queue/<id>.md.
    Both Claude (this server, local) and ChatGPT (same server, via the
    Social-Mcps-Cloud connector over Cloud Run) call the same queue_* tools
    against this one bucket, so there is exactly one operational state for
    the pipeline instead of two local copies that could diverge.

    Concurrency: every write is gated by the caller's expected_version
    against the blob's real GCS generation number via if_generation_match,
    so a stale read-modify-write from either agent is rejected atomically
    by GCS itself (QueueConflictError) rather than silently overwriting the
    other agent's change.
    """

    def __init__(self, bucket_name: str) -> None:
        self._bucket_name = bucket_name
        self._logger = get_logger(__name__)
        self._client: storage.Client | None = None

    def _get_client(self) -> storage.Client:
        if self._client is None:
            self._client = storage.Client()
        return self._client

    def _bucket(self) -> storage.Bucket:
        return self._get_client().bucket(self._bucket_name)

    def _blob_name(self, item_id: str) -> str:
        return f"{_QUEUE_PREFIX}/{item_id}.md"

    def _validate_id(self, item_id: str) -> None:
        if not _ID_RE.match(item_id):
            raise GCSQueueError(
                f"id inválido: {item_id!r}. Usa solo letras, números, guiones y guiones bajos "
                "(formato recomendado: YYYY-MM-DD-noticia-N)."
            )

    def _validate_estado(self, estado: str) -> None:
        if estado not in QUEUE_ESTADOS:
            raise GCSQueueError(f"estado inválido: {estado!r}. Válidos: {', '.join(QUEUE_ESTADOS)}.")

    # ── list ─────────────────────────────────────────────────────────────

    def _list_items_sync(self, estado: str | None) -> list[dict]:
        if estado is not None:
            self._validate_estado(estado)

        bucket = self._bucket()
        summaries: list[dict] = []
        for blob in self._get_client().list_blobs(bucket, prefix=f"{_QUEUE_PREFIX}/"):
            if not blob.name.endswith(".md"):
                continue
            try:
                frontmatter, _ = _parse_item_blob(blob.download_as_text())
            except GCSQueueError as exc:
                self._logger.warning("Saltando fichero de cola malformado %s: %s", blob.name, exc)
                continue

            if estado is not None and frontmatter.get("estado") != estado:
                continue

            summary = QueueItemSummary(
                id=frontmatter.get("id", blob.name.rsplit("/", 1)[-1][:-3]),
                version=blob.generation,
                estado=frontmatter.get("estado", "error"),
                orden=frontmatter.get("orden", 999),
                fecha_prevista=frontmatter.get("fecha_prevista"),
                fecha_publicada=frontmatter.get("fecha_publicada"),
                url_wordpress=frontmatter.get("url_wordpress"),
            )
            summaries.append(summary.model_dump())

        summaries.sort(key=lambda item: item["orden"])
        return summaries

    async def list_items(self, estado: str | None = None) -> list[dict]:
        return await asyncio.to_thread(self._list_items_sync, estado)

    # ── get ──────────────────────────────────────────────────────────────

    def _get_item_sync(self, item_id: str) -> dict:
        blob = self._bucket().blob(self._blob_name(item_id))
        try:
            blob.reload()
        except NotFound as exc:
            raise QueueNotFoundError(f"No existe la noticia '{item_id}' en la cola.") from exc

        frontmatter, body = _parse_item_blob(blob.download_as_text())
        frontmatter["version"] = blob.generation
        frontmatter["contenido_markdown"] = body
        return frontmatter

    async def get_item(self, item_id: str) -> dict:
        return await asyncio.to_thread(self._get_item_sync, item_id)

    # ── create ───────────────────────────────────────────────────────────

    def _create_item_sync(
        self,
        item_id: str,
        orden: int,
        fecha_prevista: str,
        contenido_markdown: str,
        imagen: dict | None,
        updated_by: str,
    ) -> dict:
        self._validate_id(item_id)

        frontmatter = {
            "id": item_id,
            "estado": "pendiente",
            "orden": orden,
            "fecha_prevista": fecha_prevista,
            "fecha_publicada": None,
            "url_wordpress": None,
            "imagen": imagen or {"proveedor": None, "url": None, "canva_id": None},
            "canales": _default_canales(),
            "descartada_motivo": None,
            "fecha_descartada": None,
            "notas": None,
            "updated_at": _now_iso(),
            "updated_by": updated_by,
        }
        text = _render_item_blob(frontmatter, contenido_markdown)

        blob = self._bucket().blob(self._blob_name(item_id))
        try:
            # if_generation_match=0 means "only write if the object does
            # not exist yet" — the atomic equivalent of an exclusive create.
            blob.upload_from_string(
                text, content_type="text/markdown; charset=utf-8", if_generation_match=0
            )
        except PreconditionFailed as exc:
            raise QueueAlreadyExistsError(f"Ya existe una noticia con id '{item_id}'.") from exc

        blob.reload()
        frontmatter["version"] = blob.generation
        frontmatter["contenido_markdown"] = contenido_markdown
        return frontmatter

    async def create_item(
        self,
        item_id: str,
        orden: int,
        fecha_prevista: str,
        contenido_markdown: str,
        imagen: dict | None,
        updated_by: str,
    ) -> dict:
        return await asyncio.to_thread(
            self._create_item_sync, item_id, orden, fecha_prevista, contenido_markdown, imagen, updated_by
        )

    # ── update (backs update / mark_published / mark_discarded) ────────────

    def _update_item_sync(
        self,
        item_id: str,
        expected_version: int,
        updated_by: str,
        fields: dict,
        contenido_markdown: str | None,
    ) -> dict:
        blob = self._bucket().blob(self._blob_name(item_id))
        try:
            blob.reload()
        except NotFound as exc:
            raise QueueNotFoundError(f"No existe la noticia '{item_id}' en la cola.") from exc

        if blob.generation != expected_version:
            raise QueueConflictError(
                f"Conflicto de versión en '{item_id}': esperabas version={expected_version} pero "
                f"la cola tiene version={blob.generation} ahora mismo. Otro agente la modificó "
                "mientras tanto — vuelve a leerla con queue_get antes de reintentar."
            )

        frontmatter, body = _parse_item_blob(blob.download_as_text())

        if "estado" in fields and fields["estado"] is not None:
            self._validate_estado(fields["estado"])

        for key, value in fields.items():
            if value is not None:
                frontmatter[key] = value

        if contenido_markdown is not None:
            body = contenido_markdown

        frontmatter["updated_at"] = _now_iso()
        frontmatter["updated_by"] = updated_by
        frontmatter.pop("version", None)
        frontmatter.pop("contenido_markdown", None)

        new_text = _render_item_blob(frontmatter, body)
        try:
            blob.upload_from_string(
                new_text,
                content_type="text/markdown; charset=utf-8",
                if_generation_match=expected_version,
            )
        except PreconditionFailed as exc:
            raise QueueConflictError(
                f"Conflicto de versión en '{item_id}': otro agente escribió justo ahora, "
                "entre tu lectura y esta escritura. Vuelve a leerla con queue_get y reintenta."
            ) from exc

        blob.reload()
        frontmatter["version"] = blob.generation
        frontmatter["contenido_markdown"] = body
        return frontmatter

    async def update_item(
        self,
        item_id: str,
        expected_version: int,
        updated_by: str,
        *,
        estado: str | None = None,
        orden: int | None = None,
        fecha_prevista: str | None = None,
        fecha_publicada: str | None = None,
        url_wordpress: str | None = None,
        imagen: dict | None = None,
        canales: dict | None = None,
        descartada_motivo: str | None = None,
        fecha_descartada: str | None = None,
        notas: str | None = None,
        contenido_markdown: str | None = None,
    ) -> dict:
        """
        Partial update: only fields passed as non-None are changed. `canales`,
        when provided, REPLACES the whole per-channel results map rather than
        merging key by key (matches how a single publish run reports results
        for every channel it attempted in one call). `notas` is free-form
        context that doesn't fit the structured fields (e.g. "redundante con
        publicación previa del 28/07") — everything else in the schema stays
        strict/closed on purpose, this is the one deliberate escape hatch.
        """
        fields = {
            "estado": estado,
            "orden": orden,
            "fecha_prevista": fecha_prevista,
            "fecha_publicada": fecha_publicada,
            "url_wordpress": url_wordpress,
            "imagen": imagen,
            "canales": canales,
            "descartada_motivo": descartada_motivo,
            "fecha_descartada": fecha_descartada,
            "notas": notas,
        }
        return await asyncio.to_thread(
            self._update_item_sync, item_id, expected_version, updated_by, fields, contenido_markdown
        )

    # ── archive ──────────────────────────────────────────────────────────

    def _archive_week_sync(self, week_start: str, updated_by: str) -> dict:
        bucket = self._bucket()
        archived: list[str] = []
        for blob in list(self._get_client().list_blobs(bucket, prefix=f"{_QUEUE_PREFIX}/")):
            if not blob.name.endswith(".md"):
                continue
            item_id = blob.name.rsplit("/", 1)[-1][:-len(".md")]
            dest_name = f"{_ARCHIVE_PREFIX}/{week_start}/{item_id}.md"
            bucket.copy_blob(blob, bucket, dest_name)
            blob.delete()
            archived.append(item_id)

        self._logger.info(
            "Archivadas %d noticias bajo archive/%s/ (por %s).", len(archived), week_start, updated_by
        )
        return {"archived": archived, "week_start": week_start}

    async def archive_week(self, week_start: str, updated_by: str) -> dict:
        return await asyncio.to_thread(self._archive_week_sync, week_start, updated_by)

from __future__ import annotations

from clients.gcs_queue_client import (
    GCSQueueClient,
    GCSQueueError,
    QueueAlreadyExistsError,
    QueueConflictError,
    QueueNotFoundError,
)
from core.errors import describe_exception
from core.logger import get_logger
from core.models import ToolResult

_logger = get_logger(__name__)


def _error_result(exc: Exception) -> dict:
    return ToolResult(success=False, error=describe_exception(exc)).model_dump()


async def queue_list(client: GCSQueueClient, estado: str | None = None) -> dict:
    try:
        items = await client.list_items(estado)
        return ToolResult(success=True, data={"items": items}).model_dump()
    except GCSQueueError as exc:
        return _error_result(exc)
    except Exception as exc:
        _logger.exception("Unexpected error in queue_list")
        return _error_result(exc)


async def queue_get(client: GCSQueueClient, id: str) -> dict:
    try:
        item = await client.get_item(id)
        return ToolResult(success=True, data=item).model_dump()
    except (QueueNotFoundError, GCSQueueError) as exc:
        return _error_result(exc)
    except Exception as exc:
        _logger.exception("Unexpected error in queue_get")
        return _error_result(exc)


async def queue_create(
    client: GCSQueueClient,
    id: str,
    orden: int,
    fecha_prevista: str,
    contenido_markdown: str,
    updated_by: str,
    imagen: dict | None = None,
) -> dict:
    try:
        item = await client.create_item(id, orden, fecha_prevista, contenido_markdown, imagen, updated_by)
        return ToolResult(success=True, data=item).model_dump()
    except (QueueAlreadyExistsError, GCSQueueError) as exc:
        return _error_result(exc)
    except Exception as exc:
        _logger.exception("Unexpected error in queue_create")
        return _error_result(exc)


async def queue_update(
    client: GCSQueueClient,
    id: str,
    expected_version: int,
    updated_by: str,
    estado: str | None = None,
    orden: int | None = None,
    fecha_prevista: str | None = None,
    contenido_markdown: str | None = None,
    imagen: dict | None = None,
    notas: str | None = None,
) -> dict:
    try:
        item = await client.update_item(
            id,
            expected_version,
            updated_by,
            estado=estado,
            orden=orden,
            fecha_prevista=fecha_prevista,
            imagen=imagen,
            notas=notas,
            contenido_markdown=contenido_markdown,
        )
        return ToolResult(success=True, data=item).model_dump()
    except (QueueConflictError, QueueNotFoundError, GCSQueueError) as exc:
        return _error_result(exc)
    except Exception as exc:
        _logger.exception("Unexpected error in queue_update")
        return _error_result(exc)


async def queue_mark_published(
    client: GCSQueueClient,
    id: str,
    expected_version: int,
    updated_by: str,
    url_wordpress: str,
    fecha_publicada: str,
    canales: dict,
) -> dict:
    try:
        item = await client.update_item(
            id,
            expected_version,
            updated_by,
            estado="publicada",
            url_wordpress=url_wordpress,
            fecha_publicada=fecha_publicada,
            canales=canales,
        )
        return ToolResult(success=True, data=item).model_dump()
    except (QueueConflictError, QueueNotFoundError, GCSQueueError) as exc:
        return _error_result(exc)
    except Exception as exc:
        _logger.exception("Unexpected error in queue_mark_published")
        return _error_result(exc)


async def queue_mark_discarded(
    client: GCSQueueClient,
    id: str,
    expected_version: int,
    updated_by: str,
    motivo: str,
    fecha_descartada: str | None = None,
) -> dict:
    try:
        item = await client.update_item(
            id,
            expected_version,
            updated_by,
            estado="descartada",
            descartada_motivo=motivo,
            fecha_descartada=fecha_descartada,
        )
        return ToolResult(success=True, data=item).model_dump()
    except (QueueConflictError, QueueNotFoundError, GCSQueueError) as exc:
        return _error_result(exc)
    except Exception as exc:
        _logger.exception("Unexpected error in queue_mark_discarded")
        return _error_result(exc)


async def queue_archive_week(client: GCSQueueClient, week_start: str, updated_by: str) -> dict:
    try:
        result = await client.archive_week(week_start, updated_by)
        return ToolResult(success=True, data=result).model_dump()
    except GCSQueueError as exc:
        return _error_result(exc)
    except Exception as exc:
        _logger.exception("Unexpected error in queue_archive_week")
        return _error_result(exc)

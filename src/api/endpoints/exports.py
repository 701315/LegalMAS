# src/api/endpoints/exports.py

"""
API endpoints для работы с экспортами (Excel / Word / др.).

Текущая версия:
- GET /api/v1/exports/{export_id}          — получить статус экспорта и meta-информацию;
- GET /api/v1/exports/{export_id}/download — скачать файл через backend streaming.

Особенности:
- фронт получает стабильный internal download URL:
    /api/v1/exports/{export_id}/download
- backend сам проверяет статус экспорта и существование артефакта;
- backend сам стримит файл из MinIO/S3 в браузер;
- браузер НЕ ходит в MinIO напрямую;
- bucket может оставаться полностью приватным.

Пока:
- используем только проверку существования Export;
- не проверяем роли (admin/editor/viewer);
- не пишем отдельный audit log скачивания;
- не используем полноценный tenant-aware доступ.

Это позволяет безопасно раздавать файлы через приложение,
не публикуя MinIO наружу.
"""

from __future__ import annotations

import mimetypes
from email.utils import format_datetime
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from api.schemas.export import ExportRecord
from core.exceptions import PermanentError, TransientError
from core.logging import get_logger
from db.models.deal import Deal
from db.models.export import Export
from db.session import get_db
from storage.artifact_store import ArtifactStore

logger = get_logger(__name__)

router = APIRouter(
    prefix="/exports",
    tags=["exports"],
)

STREAM_CHUNK_SIZE_BYTES = 1024 * 1024

_EXPORT_CONTENT_TYPES = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".json": "application/json; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".pdf": "application/pdf",
}


async def _get_scoped_export_or_404(
    db: AsyncSession,
    export_id: UUID,
    user: CurrentUser,
) -> Export:
    """
    Вернуть Export только если он доступен в tenant scope текущего пользователя.

    Правила:
    - superadmin   → может видеть export любого tenant'а
    - tenant_admin → только exports своего tenant'а
    - member       → только exports своего tenant'а

    ВАЖНО:
    - этот helper проверяет только tenant isolation;
    - deal-level RBAC (viewer/editor/admin membership) проверяется отдельно
      через require_project_role().
    """
    stmt = (
        select(Export)
        .join(Deal, Export.deal_id == Deal.id)
        .where(Export.id == export_id)
    )

    if user.global_role != "superadmin":
        stmt = stmt.where(Deal.tenant_id == user.tenant_id)

    result = await db.execute(stmt)
    export: Export | None = result.scalars().first()

    if export is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export not found",
        )

    return export


def _build_download_url(export: Export) -> str | None:
    """
    Вернуть внутренний API URL для скачивания, если экспорт готов.

    Важно:
    - здесь НЕ генерируем presigned URL;
    - download URL стабилен и не зависит от storage topology;
    - реальная выдача файла происходит только при фактическом GET /download.
    """
    file_ref = (export.file_ref or "").strip()
    if export.status != "completed" or not file_ref:
        return None

    return f"/api/v1/exports/{export.id}/download"


def _extract_filename(file_ref: str, export_id: UUID) -> str:
    raw_name = PurePosixPath(file_ref).name.strip()
    if raw_name:
        return raw_name
    return f"{export_id}.bin"


def _resolve_content_type(filename: str, storage_content_type: str | None) -> str:
    if storage_content_type and storage_content_type.strip():
        return storage_content_type.strip()

    ext = PurePosixPath(filename).suffix.lower()
    explicit = _EXPORT_CONTENT_TYPES.get(ext)
    if explicit:
        return explicit

    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def _build_content_disposition(filename: str, content_type: str) -> str:
    """
    Для PDF оставляем inline-вариант.
    Для остальных экспортов — attachment, чтобы браузер корректно скачивал файл.
    """
    disposition_type = "inline" if content_type == "application/pdf" else "attachment"

    ascii_fallback = filename.encode("ascii", errors="ignore").decode("ascii").strip()
    ascii_fallback = ascii_fallback.replace("\\", "_").replace('"', "")
    if not ascii_fallback:
        ascii_fallback = "export"

    return (
        f'{disposition_type}; filename="{ascii_fallback}"; '
        f"filename*=UTF-8''{quote(filename)}"
    )


def _iter_storage_response(storage_response: Any):
    """
    Итерироваться по объекту MinIO безопасными chunk'ами и гарантированно
    освобождать соединение после завершения streaming.
    """
    try:
        while True:
            chunk = storage_response.read(STREAM_CHUNK_SIZE_BYTES)
            if not chunk:
                break
            yield chunk
    finally:
        try:
            storage_response.close()
        finally:
            storage_response.release_conn()


@router.get("/{export_id}", response_model=ExportRecord)
async def get_export_status(
    export_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> ExportRecord:
    """
    Получить статус экспорта и базовую информацию по одной записи Export.

    Фронтенд использует этот endpoint для polling:
    - status = pending / processing -> продолжаем опрос;
    - status = completed -> показываем кнопку скачивания;
    - status = failed -> показываем ошибку.

    Поле download_url заполняется только если экспорт завершён и file_ref существует.
    """
    export = await _get_scoped_export_or_404(db, export_id, user)

    await require_project_role(
        db=db,
        user=user,
        deal_id=export.deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    record = ExportRecord.model_validate(export)
    record.download_url = _build_download_url(export)

    logger.info(
        "Export status requested",
        export_id=str(export.id),
        run_id=str(export.run_id),
        deal_id=str(export.deal_id),
        export_type=export.export_type,
        status=export.status,
        file_ref=export.file_ref,
        file_size_bytes=export.file_size_bytes,
        has_download_url=bool(record.download_url),
        actor_user_id=user.id,
        actor_tenant_id=str(user.tenant_id),
        actor_role=user.global_role,
    )

    if export.status in {"pending", "processing"}:
        logger.debug(
            "Export still in progress",
            export_id=str(export.id),
            status=export.status,
        )
    elif export.status == "failed":
        logger.warning(
            "Export is in failed status",
            export_id=str(export.id),
            run_id=str(export.run_id),
            deal_id=str(export.deal_id),
        )
    elif export.status == "completed" and not export.file_ref:
        logger.warning(
            "Export completed without file_ref",
            export_id=str(export.id),
            run_id=str(export.run_id),
            deal_id=str(export.deal_id),
        )

    return record


@router.get("/{export_id}/download")
async def download_export_file(
    export_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Скачать файл экспорта через backend streaming.

    Логика:
    - ищем Export;
    - убеждаемся, что status == completed и file_ref заполнен;
    - проверяем наличие объекта в storage и читаем его metadata;
    - открываем streaming-object через ArtifactStore;
    - отдаём бинарный поток клиенту через FastAPI StreamingResponse.

    Почему это production-friendly:
    - bucket остаётся приватным;
    - браузер не знает ничего про MinIO endpoint;
    - dev/demo работают одинаково независимо от сетевой topology;
    - приложение сохраняет контроль доступа на своём уровне.
    """
    export = await _get_scoped_export_or_404(db, export_id, user)

    await require_project_role(
        db=db,
        user=user,
        deal_id=export.deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    file_ref = (export.file_ref or "").strip()

    if export.status != "completed":
        logger.warning(
            "Download requested for export that is not completed",
            export_id=str(export.id),
            run_id=str(export.run_id),
            deal_id=str(export.deal_id),
            export_type=export.export_type,
            status=export.status,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Export is not ready",
        )

    if not file_ref:
        logger.warning(
            "Download requested for completed export without file_ref",
            export_id=str(export.id),
            run_id=str(export.run_id),
            deal_id=str(export.deal_id),
            export_type=export.export_type,
            status=export.status,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Export file is missing",
        )

    store = ArtifactStore()

    try:
        metadata = store.get_file_metadata(file_ref)
        storage_response = store.open_file_stream(file_ref)
    except PermanentError as e:
        logger.warning(
            "Export artifact not found in storage",
            export_id=str(export.id),
            run_id=str(export.run_id),
            deal_id=str(export.deal_id),
            export_type=export.export_type,
            file_ref=file_ref,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export file not found in storage",
        ) from e
    except TransientError as e:
        logger.exception(
            "Failed to open export artifact stream",
            export_id=str(export.id),
            run_id=str(export.run_id),
            deal_id=str(export.deal_id),
            export_type=export.export_type,
            file_ref=file_ref,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to open export file",
        ) from e
    except Exception as e:  # noqa: BLE001
        logger.exception(
            "Unexpected error while preparing export download",
            export_id=str(export.id),
            run_id=str(export.run_id),
            deal_id=str(export.deal_id),
            export_type=export.export_type,
            file_ref=file_ref,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to prepare export download",
        ) from e

    filename = _extract_filename(file_ref, export.id)
    content_type = _resolve_content_type(
        filename=filename,
        storage_content_type=metadata.get("content_type"),
    )

    headers = {
        "Content-Disposition": _build_content_disposition(filename, content_type),
        "Cache-Control": "private, no-store",
        "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff",
    }

    size = metadata.get("size")
    if isinstance(size, int) and size >= 0:
        headers["Content-Length"] = str(size)

    etag = metadata.get("etag")
    if isinstance(etag, str) and etag:
        headers["ETag"] = etag

    last_modified = metadata.get("last_modified")
    if last_modified is not None:
        try:
            headers["Last-Modified"] = format_datetime(last_modified, usegmt=True)
        except Exception:
            pass

    logger.info(
        "Streaming export download via backend",
        export_id=str(export.id),
        deal_id=str(export.deal_id),
        run_id=str(export.run_id),
        export_type=export.export_type,
        file_ref=file_ref,
        filename=filename,
        content_type=content_type,
        size=size,
        actor_user_id=user.id,
        actor_tenant_id=str(user.tenant_id),
        actor_role=user.global_role,
    )

    return StreamingResponse(
        _iter_storage_response(storage_response),
        media_type=content_type,
        headers=headers,
    )

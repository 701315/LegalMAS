# src/api/endpoints/exports.py

"""
API endpoints для работы с экспортами (Excel / Word / др.).

Текущая версия:
- GET /api/v1/exports/{export_id}          — получить статус экспорта и meta-информацию;
- GET /api/v1/exports/{export_id}/download — выдать redirect на временный presigned URL файла.

Особенности:
- фронт получает стабильный internal download URL:
    /api/v1/exports/{export_id}/download
- реальный URL файла генерируется только в момент скачивания;
- backend не раздаёт бинарник через себя, а делегирует скачивание MinIO/S3;
- схема подходит для production и приватного bucket'а.

Пока:
- используем только проверку существования Export;
- не проверяем роли (admin/editor/viewer);
- не пишем audit log;
- не используем полноценный tenant-aware доступ.

Это позволяет быстро завести рабочий контракт для фронта,
а затем безопасно нарастить RBAC, audit и storage layer.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.export import ExportRecord
from core.logging import get_logger
from db.models.export import Export
from db.session import get_db
from storage.artifact_store import ArtifactStore

logger = get_logger(__name__)

router = APIRouter(
    prefix="/exports",
    tags=["exports"],
)

EXPORT_PRESIGNED_URL_EXPIRES_SECONDS = 3600


async def get_tenant_id() -> str:
    """
    Временная заглушка для tenant_id.

    Сейчас возвращает константу "default".
    Позже здесь можно подключить:
    - чтение tenant_id из токена,
    - чтение tenant_id из middleware / request state,
    - или multi-tenant routing по домену / заголовкам.
    """
    return "default"


async def _get_export_or_404(
    db: AsyncSession,
    export_id: UUID,
) -> Export:
    stmt = select(Export).where(Export.id == export_id)
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
    - presigned URL создаётся только в момент фактического скачивания,
      чтобы ссылка не успела протухнуть, пока пользователь смотрит UI.
    """
    file_ref = (export.file_ref or "").strip()
    if export.status != "completed" or not file_ref:
        return None

    return f"/api/v1/exports/{export.id}/download"


@router.get("/{export_id}", response_model=ExportRecord)
async def get_export_status(
    export_id: UUID,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
) -> ExportRecord:
    """
    Получить статус экспорта и базовую информацию по одной записи Export.

    Фронтенд использует этот endpoint для polling:
    - status = pending / processing -> продолжаем опрос;
    - status = completed -> показываем кнопку скачивания;
    - status = failed -> показываем ошибку.

    Поле download_url заполняется только если экспорт завершён и file_ref существует.
    """
    export = await _get_export_or_404(db, export_id)

    _ = tenant_id

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
    tenant_id: str = Depends(get_tenant_id),
):
    """
    Скачать файл экспорта через redirect на временный presigned URL MinIO/S3.

    Логика:
    - ищем Export;
    - убеждаемся, что status == completed и file_ref заполнен;
    - генерируем presigned URL через ArtifactStore;
    - редиректим клиента на этот URL.

    Это production-friendly подход:
    - bucket может оставаться приватным;
    - backend не стримит тяжёлые файлы через себя;
    - ссылка живёт ограниченное время.
    """
    export = await _get_export_or_404(db, export_id)

    _ = tenant_id

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

    try:
        store = ArtifactStore()
        presigned_url = store.get_presigned_get_url(
            file_ref,
            expires_seconds=EXPORT_PRESIGNED_URL_EXPIRES_SECONDS,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception(
            "Failed to generate presigned download URL",
            export_id=str(export.id),
            run_id=str(export.run_id),
            deal_id=str(export.deal_id),
            export_type=export.export_type,
            file_ref=file_ref,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to prepare download URL",
        ) from e

    logger.info(
        "Redirecting export download to presigned URL",
        export_id=str(export.id),
        deal_id=str(export.deal_id),
        run_id=str(export.run_id),
        export_type=export.export_type,
        file_ref=file_ref,
        expires_seconds=EXPORT_PRESIGNED_URL_EXPIRES_SECONDS,
    )

    return RedirectResponse(
        url=presigned_url,
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )

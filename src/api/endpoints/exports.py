# src/api/endpoints/exports.py

"""
API endpoints для работы с экспортами (Excel / Word / др.).

Упрощённая версия:
- GET /api/v1/exports/{export_id}          — получить статус экспорта и meta-информацию;
- GET /api/v1/exports/{export_id}/download — отдать redirect на готовый файл экспорта.

Пока:
- используем только проверку существования Export и связанной сделки;
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

from core.logging import get_logger
from db.session import get_db
from db.models.deal import Deal
from db.models.export import Export
from api.schemas.export import ExportRecord

logger = get_logger(__name__)

router = APIRouter(
    prefix="/exports",
    tags=["exports"],
)


# Временная заглушка.
# Пока tenant никак не используется в фильтрации, но оставляем зависимость,
# чтобы потом проще было встроить мультитенантность без смены сигнатур endpoint'ов.
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

    # 1. Ищем запись Export по id.
    stmt = select(Export).where(Export.id == export_id)
    result = await db.execute(stmt)
    export: Export | None = result.scalars().first()

    if export is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export not found",
        )

    # 2. Проверяем, что связанная сделка существует.
    # Это простая sanity-check проверка, чтобы не отдавать "висячий" экспорт.
    deal_stmt = select(Deal).where(Deal.id == export.deal_id)
    deal_res = await db.execute(deal_stmt)
    deal = deal_res.scalars().first()

    if deal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deal not found",
        )

    # tenant_id пока не используется, но зависимость оставлена намеренно.
    _ = tenant_id

    # 3. Строим download_url только для готового экспорта.
    download_url: str | None = None
    if export.status == "completed" and export.file_ref:
        download_url = f"/api/v1/exports/{export.id}/download"

    # 4. Преобразуем ORM-модель в Pydantic response schema.
    record = ExportRecord.model_validate(export)
    record.download_url = download_url

    return record


@router.get("/{export_id}/download")
async def download_export_file(
    export_id: UUID,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
):
    """
    Скачать файл экспорта через redirect на фактический URL файла.

    Текущая логика:
    - ищем Export;
    - убеждаемся, что status == completed и file_ref заполнен;
    - если file_ref уже абсолютный URL (http/https), редиректим прямо туда;
    - иначе считаем, что это относительный путь до раздаваемой статики
      и редиректим на /static/{file_ref}.

    Это простой рабочий вариант.
    Позже здесь можно заменить redirect на:
    - presigned URL из S3 / MinIO,
    - FileResponse,
    - StreamingResponse,
    - audit log + RBAC.
    """

    # 1. Ищем запись Export.
    stmt = select(Export).where(Export.id == export_id)
    result = await db.execute(stmt)
    export: Export | None = result.scalars().first()

    if export is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export not found",
        )

    # 2. Проверяем, что связанная сделка существует.
    deal_stmt = select(Deal).where(Deal.id == export.deal_id)
    deal_res = await db.execute(deal_stmt)
    deal = deal_res.scalars().first()

    if deal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deal not found",
        )

    # tenant_id пока не используется, но зависимость оставлена намеренно.
    _ = tenant_id

    # 3. Экспорт должен быть завершён и иметь file_ref.
    if export.status != "completed" or not export.file_ref:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Export is not ready",
        )

    file_ref = export.file_ref

    # 4. Если file_ref уже абсолютный URL — редиректим прямо туда.
    if file_ref.startswith("http://") or file_ref.startswith("https://"):
        download_url = file_ref
    else:
        # Иначе считаем, что file_ref — это относительный путь от корня статики.
        # Пример:
        #   file_ref = "exports/deal-123/run-456/deal_summary.xlsx"
        # Тогда итоговая ссылка будет:
        #   /static/exports/deal-123/run-456/deal_summary.xlsx
        download_url = f"/static/{file_ref.lstrip('/')}"

    logger.info(
        "Redirecting export download",
        export_id=str(export.id),
        deal_id=str(export.deal_id),
        run_id=str(export.run_id),
        download_url=download_url,
    )

    return RedirectResponse(
        url=download_url,
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )



# src/api/endpoints/document_chunk_exports.py

"""
Эндпоинты для экспорта документа в виде «чанков» (chunks).

Для чего это нужно непрофессиональному пользователю (юристу / аналитику):

- Документ автоматически режется на небольшие логические куски — чанки.
- В каждом чанке система старается сохранить связный фрагмент текста
  (абзац, подпункт или небольшую группу пунктов).
- Этот модуль позволяет получить специальный .md‑файл, где:
  * каждый чанк идёт один за другим;
  * перед текстом чанка есть заголовок с:
    - номером чанка,
    - идентификатором пункта договора (clause_uid), если он известен,
    - примерным размером чанка по токенам/словам,
    - диапазоном страниц в оригинальном PDF;
  * при наличии структуры (оглавление/путь разделов) она показывается
    перед чанком в виде PATH: Раздел / Подраздел / Пункт.

Файл нужен для ручной проверки качества чанкинга:
- юрист может глазами посмотреть, где система «режет» документ;
- увидеть, не попали ли важные абзацы на стык чанков;
- сравнить текст с исходным PDF, если нужно.

Важно: этот эндпоинт НИЧЕГО не меняет в базе данных и в документе.
Он только:
- забирает уже посчитанные чанки документа,
- собирает из них один большой Markdown‑текст,
- сохраняет его во внутреннем хранилище (MinIO / S3),
- возвращает HTTP‑ссылку для скачивания/просмотра.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from db.session import get_db
from db.repositories.document_repo import DocumentRepository
from db.repositories.deal_repo import DealRepository
from engine.content.chunk_exporter import ChunkExportService
from storage.artifact_store import ArtifactStore
from core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/documents",
    tags=["document-exports"],  # отдельный тег в Swagger для всех экспортов документов
)


@router.get(
    "/{document_id}/chunk-view",
    summary="Скачать документ в виде чанков (debug)",
    response_model=dict,  # { "url": "https://..." }
)
async def get_document_chunk_view(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Вернуть ссылку на специальный .md‑файл, где документ показан
    «как его видит система чанкинга».

    Для непрофессионального пользователя:

    - Документ режется на небольшие смысловые куски (чанки).
    - В результирующем файле каждый чанк идёт один за другим,
      с заголовком, где указаны:
        * номер чанка;
        * пункт договора (clause_uid), если он известен;
        * примерный размер по токенам;
        * диапазон страниц в оригинальном PDF.
    - Если у документа есть оглавление/структура, перед чанком
      показывается путь до него (PATH: Раздел / Подраздел / Пункт).

    Это помогает юристу:

    - увидеть, как система «разрезала» документ;
    - проверить, не потерялся ли смысл на стыках чанков;
    - сравнить разбиение с исходным PDF.

    Технически эндпоинт:

    - проверяет, что документ существует и принадлежит проекту пользователя;
    - проверяет роль пользователя в проекте (viewer и выше);
    - находит сделку документа и её tenant_id;
    - собирает Markdown‑представление чанков через ChunkExportService;
    - сохраняет .md‑файл во внутреннем хранилище (MinIO / S3);
    - конвертирует внутренний s3:// URI в обычную HTTP‑ссылку;
    - возвращает JSON-объект вида: { "url": "https://.../doc_id__chunks_view.md" }.

    Важно: эндпоинт не запускает заново обработку документа и не меняет его
    статус. Он использует уже готовые sized‑чанки.
    """

    # 1. Проверяем, что документ существует
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(document_id)
    if doc is None:
        # Для пользователя: документа не существует или он был удалён.
        raise HTTPException(status_code=404, detail="Document not found")

    # 2. Проверяем, что пользователь имеет права на проект этого документа.
    #    Допускаем: admin, editor, reviewer, viewer.
    await require_project_role(
        db=db,
        user=user,
        deal_id=doc.deal_id,
        allowed_roles=("admin", "editor", "reviewer", "viewer"),
    )

    # 3. Находим сделку, чтобы получить tenant_id.
    #    Для непрофессионального программиста:
    #    - документ "живёт" внутри сделки (Deal),
    #    - у сделки есть tenant_id (арендатор в системе),
    #    - поэтому путь в MinIO строится по паре (tenant_id, deal_id).
    deal_repo = DealRepository(db)
    deal = await deal_repo.get_by_id(doc.deal_id)
    if deal is None:
        # Это аномальная ситуация: документ ссылается на несуществующую сделку.
        logger.error(
            "Deal not found for document when preparing chunk view",
            extra={
                "document_id": str(document_id),
                "deal_id": str(doc.deal_id),
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Internal error: deal not found for this document.",
        )

    # 4. Собираем Markdown‑файл из уже посчитанных чанков.
    exporter = ChunkExportService(db)
    try:
        # s3_uri — внутренний путь вида s3://bucket/tenants/.../exports/...
        s3_uri = await exporter.export_sized_chunks_markdown(
            doc_id=document_id,
            deal_id=deal.id,
            tenant_id=deal.tenant_id,
        )
    except ValueError as e:
        # Например, если DocumentContentService не нашёл чанков
        # или вернул некорректные данные.
        logger.warning(
            "Chunk export failed with ValueError",
            extra={"document_id": str(document_id), "error": str(e)},
        )
        raise HTTPException(
            status_code=404,
            detail="Chunk view is not available for this document yet",
        )
    except Exception as e:
        # Любая другая непредвиденная ошибка — логируем и отдаём 500 с понятным detail.
        logger.exception(
            "Unexpected error during chunk export",
            extra={"document_id": str(document_id)},
        )
        raise HTTPException(
            status_code=500,
            detail="Internal error while preparing chunk view for this document.",
        ) from e

    # 5. Превращаем внутренний s3:// путь в ПОДПИСАННУЮ HTTP‑ссылку (presigned URL),
    #    по которой браузер сможет скачать или открыть файл даже при приватном бакете.
    store = ArtifactStore()
    presigned_url = store.get_presigned_get_url(s3_uri)

    # 6. Возвращаем JSON с единственным полем "url".
    #    На фронте этим URL можно:
    #    - либо открыть в новой вкладке,
    #    - либо скачать как файл.
    return {"url": presigned_url}


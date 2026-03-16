# src/workers/structure_builder.py

"""
Structure Builder Worker.

Назначение:
- Считать сырой макет документа (textlayoutraw) из MinIO.
- Построить древовидную структуру документа (clause_tree) через сервис StructureBuilder.
- Сохранить clause_tree в MinIO и обновить ссылки в DocumentVersion.
- Обновить статус документа: sanitized -> structured.
- Запустить следующую задачу пайплайна: workers.classify_document.

Архитектурный паттерн:
- Внешняя функция Celery‑таски остаётся синхронной (def), чтобы Celery
  мог корректно сериализовать результат и работать в prefork‑модели.
- Вся асинхронная логика (БД, MinIO) находится в _build_structure_async()
  и вызывается из таски через безопасный переход sync → async (run_async + db_uow).
"""

import time
import uuid

from core.config import settings
from core.constants import DocumentStatus
from core.exceptions import PermanentError
from core.logging import get_logger
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.uow import db_uow, UnitOfWork
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from mas_queue.async_helpers import run_async
from services.structure.builder import StructureBuilder
from storage.artifact_store import ArtifactPath, ArtifactStore

logger = get_logger(__name__)


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.build_structure",
    queue="default",
)
def build_structure(
    self,
    document_version_id: str,
    **kwargs,  # принимаем остальные аргументы (deal_id, run_id и т.д.) для совместимости
) -> dict:
    """
    Sync Celery entry point.

    Паттерн:
    - Celery вызывает синхронную функцию.
    - Внутри один раз передаём управление в async‑мир через run_async.
    """

    async def _wrapper() -> dict:
        try:
            async with db_uow() as uow:
                return await _build_structure_async(
                    document_version_id=document_version_id,
                    extra_args=kwargs,
                    uow=uow,
                )
        except PermanentError as e:
            logger.error(
                "Permanent error during structure building",
                document_version_id=document_version_id,
                error=str(e),
            )
            # Отдельный UoW только для перевода документа в FAILED + деталей
            async with db_uow() as uow_status:
                await _mark_failed(
                    uow_status,
                    document_version_id=document_version_id,
                    message=str(e),
                )
            return {
                "status": DocumentStatus.FAILED.value,
                "document_version_id": document_version_id,
                "error": str(e),
            }

    return run_async(_wrapper())


async def _build_structure_async(
    document_version_id: str,
    extra_args: dict,
    uow: UnitOfWork,
) -> dict:
    store = ArtifactStore(settings)
    start = time.time()
    v_id = (
        uuid.UUID(document_version_id)
        if isinstance(document_version_id, str)
        else document_version_id
    )

    ver_repo = DocumentVersionRepository(uow.session)
    doc_repo = DocumentRepository(uow.session)

    # 1. Загрузка версии и документа
    version = await ver_repo.get_by_id(v_id)
    if not version:
        raise PermanentError(f"DocumentVersion {v_id} not found")

    doc = await doc_repo.get_by_id(version.document_id)
    if not doc:
        raise PermanentError(f"Document {version.document_id} not found")

    # Идемпотентность: не перестраиваем, если уже готово
    if doc.status in (
        DocumentStatus.STRUCTURED.value,
        DocumentStatus.CLASSIFIED.value,
        DocumentStatus.ANALYZING.value,
    ):
        logger.info("Already structured, skipping", document_id=str(doc.id))
        return {"document_id": str(doc.id), "skipped": True}

    # 2. Получение сырого макета из MinIO
    if not version.text_layout_raw_ref:
        raise PermanentError(f"text_layout_raw_ref missing for version {v_id}")

    # ArtifactStore.get_json — синхронный метод, НЕ используем await
    raw_layout = store.get_json(version.text_layout_raw_ref)
    elements = raw_layout.get("elements", [])
    if not elements:
        raise PermanentError(f"No elements in raw layout for version {v_id}")


    # 3. Вызов сервиса построения структуры
    builder = StructureBuilder()
    clause_tree = builder.build(
        document_id=str(doc.id),
        elements=elements,
    )

    # 4. Сохранение ClauseTree как отдельного артефакта
    # ВАЖНО: tenant_id берём из связанной сделки, а не подменяем deal_id.
    if hasattr(doc, "deal") and doc.deal and hasattr(doc.deal, "tenant_id"):
        tenant_id = str(doc.deal.tenant_id)
    else:
        # fallback для dev‑режима, если связь не подгружена
        tenant_id = str(doc.deal_id)

    deal_id = str(doc.deal_id)

    clause_tree_path = ArtifactPath.clause_tree(
        tenant_id=tenant_id,
        deal_id=deal_id,
        document_id=str(doc.id),
    )
    # ArtifactStore.put_json — синхронный метод, НЕ используем await
    store.put_json(clause_tree_path, clause_tree.to_dict())


    # 5. Обновление БД
    await ver_repo.update_refs(version_id=v_id, clause_tree_ref=clause_tree_path)
    await doc_repo.update_status(
        doc.id,
        DocumentStatus.STRUCTURED.value,
        processing_error_details=None,
    )
    # UoW зафиксирует изменения (commit) при выходе из db_uow в таске

    # 6. Запуск следующего этапа (Классификация)
    # Передаём в classify_document достаточный контекст:
    # - run_id (если есть),
    # - deal_id и tenant_id для корректного запуска run_deal_checks через классификатор.
    from mas_queue.celery_app import celery_app as _celery  # локальный импорт на случай циклов

    _celery.send_task(
        "workers.classify_document",
        kwargs={
            "document_id": str(doc.id),
            "run_id": extra_args.get("run_id"),
            "deal_id": deal_id,
            "tenant_id": tenant_id,
        },
    )

    return {
        "document_id": str(doc.id),
        "clause_tree_ref": clause_tree_path,
        "confidence": clause_tree.structure_confidence,
        "is_degraded": clause_tree.degraded,
        "duration": round(time.time() - start, 2),
    }


async def _mark_failed(
    uow: UnitOfWork,
    document_version_id: str,
    *,
    message: str,
) -> None:
    """
    Отдельный простой UoW для перевода документа в статус FAILED
    с заполнением processing_error_details, если структура не смогла построиться.
    """
    ver_repo = DocumentVersionRepository(uow.session)
    doc_repo = DocumentRepository(uow.session)

    v_id = uuid.UUID(document_version_id)
    version = await ver_repo.get_by_id(v_id)
    if not version:
        return

    await doc_repo.set_failed(
        version.document_id,
        stage="structure",
        message=message,
        reason="structure_error",
        run_id=None,
    )

# src/workers/structure_builder.py

"""
Structure Builder Worker.

Назначение:
- Считать санитизированный макет документа (одноязычный layout после PII) из хранилища.
- Построить древовидную структуру документа (clause_tree) через сервис StructureBuilder.
- Сохранить clause_tree в хранилище и обновить ссылку в DocumentVersion.
- Обновить статус документа: SANITIZED -> STRUCTURED.
- Запуск последующих задач пайплайна (classify, build_chunks и далее)
  выполняется централизованным оркестратором.

Архитектурный паттерн:
- Внешняя Celery-таска остаётся синхронной (def), чтобы Celery корректно
  работал в prefork-модели и сериализовал результат.
- Вся асинхронная логика (БД, хранилище) находится в _build_structure_async()
  и вызывается через безопасный переход sync -> async (run_async + db_uow).
- Воркер не управляет следующими стадиями пайплайна: он отвечает только
  за построение структуры и фиксацию результата своей стадии.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from core.config import settings
from core.constants import DocumentStatus
from core.exceptions import PermanentError
from core.logging import get_logger
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.uow import UnitOfWork, db_uow
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from services.structure.builder import StructureBuilder
from storage.artifact_store import ArtifactPath, ArtifactStore
from services.run_orchestrator_trigger import retrigger_run_pipeline

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
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Синхронная Celery entry point.

    Паттерн:
    - Celery вызывает синхронную функцию;
    - внутри один раз передаём управление в async-мир через run_async();
    - все ошибки уровня бизнес-контракта переводим в FAILED через отдельный UoW.
    """

    run_id = kwargs.get("run_id")
    deal_id = kwargs.get("deal_id")
    tenant_id = kwargs.get("tenant_id")

    async def _wrapper() -> dict[str, Any]:
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
                deal_id=deal_id,
                tenant_id=tenant_id,
                run_id=run_id,
                error=str(e),
            )
            async with db_uow() as uow_status:
                await _mark_failed(
                    uow=uow_status,
                    document_version_id=document_version_id,
                    message=str(e),
                )
            return {
                "status": DocumentStatus.FAILED.value,
                "document_version_id": document_version_id,
                "error": str(e),
            }

    result = run_async(_wrapper())

    if run_id and result.get("status") != DocumentStatus.FAILED.value:
        logger.info(
            "Structure building finished, retriggering run pipeline",
            document_version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            run_id=run_id,
        )
        retrigger_run_pipeline(
            run_id=run_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
        )

    return result

async def _build_structure_async(
    *,
    document_version_id: str,
    extra_args: dict[str, Any],
    uow: UnitOfWork,
) -> dict[str, Any]:
    """
    Асинхронное ядро стадии structure.

    Делает только свою стадию:
    1) загружает DocumentVersion и Document;
    2) читает layout по unified primary-layout контракту;
    3) строит clause_tree;
    4) сохраняет clause_tree в хранилище;
    5) обновляет clause_tree_ref и статус документа.
    """
    _ = extra_args  # намеренно игнорируем, сохраняя совместимость интерфейса

    start = time.time()
    store = ArtifactStore(settings)

    v_id = uuid.UUID(document_version_id)

    ver_repo = DocumentVersionRepository(uow.session)
    doc_repo = DocumentRepository(uow.session)

    # 1. Загрузка версии и документа
    version = await ver_repo.get_by_id(v_id)
    if not version:
        raise PermanentError(f"DocumentVersion {v_id} not found")

    doc = await doc_repo.get_by_id(version.document_id)
    if not doc:
        raise PermanentError(f"Document {version.document_id} not found")

    # 2. Идемпотентность
    if doc.status in (
        DocumentStatus.STRUCTURED.value,
        DocumentStatus.CLASSIFIED.value,
        DocumentStatus.ANALYZING.value,
    ):
        logger.info(
            "Document already structured, skipping rebuild",
            document_id=str(doc.id),
            document_version_id=str(v_id),
            status=doc.status,
        )
        return {
            "document_id": str(doc.id),
            "document_version_id": str(v_id),
            "skipped": True,
        }

    # 3. Получение макета по единому контракту пайплайна
    #
    # Приоритет:
    # 1) layout_primary_sanitized_ref — основной source of truth после PII;
    # 2) layout_primary_ref — recovery fallback для случаев,
    #    когда PII ещё не выполнен, но structure всё же нужно восстановить.
    layout_ref = (
        getattr(version, "layout_primary_sanitized_ref", None)
        or getattr(version, "layout_primary_ref", None)
    )

    if not layout_ref:
        raise PermanentError(
            f"layout_primary_sanitized_ref or layout_primary_ref is required for version {v_id}"
        )

    raw_layout = store.get_json(layout_ref)
    elements = raw_layout.get("elements", [])
    if not elements:
        raise PermanentError(f"No elements found in layout for version {v_id}")

    # 4. Построение структуры
    builder = StructureBuilder()
    clause_tree = builder.build(
        document_id=str(doc.id),
        elements=elements,
    )

    # 5. Построение пути артефакта
    #
    # tenant_id берём из связанной сделки как из source of truth;
    # fallback на deal_id оставляем только для dev/неполной загрузки отношений.
    if hasattr(doc, "deal") and doc.deal and hasattr(doc.deal, "tenant_id"):
        tenant_id = str(doc.deal.tenant_id)
    else:
        tenant_id = str(doc.deal_id)

    deal_id = str(doc.deal_id)

    clause_tree_path = ArtifactPath.clause_tree(
        tenant_id=tenant_id,
        deal_id=deal_id,
        document_id=str(doc.id),
    )

    # 6. Сохранение clause_tree
    store.put_json(clause_tree_path, clause_tree.to_dict())

    # 7. Обновление БД
    await ver_repo.update_refs(
        version_id=v_id,
        clause_tree_ref=clause_tree_path,
    )
    await doc_repo.update_status(
        doc.id,
        DocumentStatus.STRUCTURED.value,
        processing_error_details=None,
    )
    # commit произойдёт при выходе из db_uow()

    duration = round(time.time() - start, 2)

    logger.info(
        "Structure building complete",
        document_id=str(doc.id),
        document_version_id=str(v_id),
        clause_tree_ref=clause_tree_path,
        confidence=getattr(clause_tree, "structure_confidence", None),
        is_degraded=getattr(clause_tree, "degraded", None),
        duration_seconds=duration,
    )

    return {
        "document_id": str(doc.id),
        "document_version_id": str(v_id),
        "clause_tree_ref": clause_tree_path,
        "confidence": clause_tree.structure_confidence,
        "is_degraded": clause_tree.degraded,
        "duration_seconds": duration,
    }


async def _mark_failed(
    uow: UnitOfWork,
    document_version_id: str,
    *,
    message: str,
) -> None:
    """
    Отдельный короткий UoW для перевода документа в FAILED,
    если стадия structure завершилась постоянной ошибкой.

    Здесь мы намеренно не поднимаем исключение дальше:
    если версия не найдена, просто выходим — это best-effort запись статуса.
    """
    ver_repo = DocumentVersionRepository(uow.session)
    doc_repo = DocumentRepository(uow.session)

    v_id = uuid.UUID(document_version_id)
    version = await ver_repo.get_by_id(v_id)
    if not version:
        logger.warning(
            "Cannot mark document as FAILED during structure stage: version not found",
            document_version_id=document_version_id,
        )
        return

    await doc_repo.set_failed(
        version.document_id,
        stage="structure",
        message=message,
        reason="structure_error",
        run_id=None,
    )

    
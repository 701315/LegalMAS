# src/workers/structure_builder.py

"""
Structure Builder Worker.

Назначение:
- Считать санитизированный одноязычный макет документа из хранилища.
- Построить древовидную структуру документа (clause_tree) через StructureBuilder.
- Сохранить clause_tree в хранилище и обновить ссылку в DocumentVersion.
- Обновить статус документа: SANITIZED -> STRUCTURED.
- Запуск последующих задач пайплайна выполняется централизованным оркестратором.

Позиция в пайплайне:
- import -> convert -> build_primary_language_source -> extract -> pii -> structure -> classify -> ...

Контракт стадии:
- Основной source of truth для structure — только layout_primary_sanitized_ref.
- Fallback на layout_primary_ref допускается только через feature flag
  ALLOW_LEGACY_LAYOUT_FALLBACK=True.
- В нормальном боевом режиме fallback выключен.
- retrigger downstream допустим только после подтверждённого commit результатов structure.

Архитектурный паттерн:
- Внешняя Celery-задача синхронная (def).
- Асинхронная бизнес-логика живёт в _build_structure_async().
- Один sync -> async переход через run_async().
- Ошибки уровня контракта стадии переводятся в FAILED через отдельный UoW.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from core.config import settings
from core.constants import DocumentStatus
from core.exceptions import PermanentError, TransientError
from core.logging import get_logger
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.uow import UnitOfWork, db_uow
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from services.run_orchestrator_trigger import retrigger_run_pipeline
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
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Sync Celery entrypoint.

    Поведение:
    - выполняет только стадию structure;
    - при PermanentError переводит документ в FAILED;
    - при TransientError отдаёт управление retry-механизму;
    - при успехе будит оркестратор только после commit.
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

        except TransientError as e:
            logger.warning(
                "Transient error during structure building; task should be retried",
                document_version_id=document_version_id,
                deal_id=deal_id,
                tenant_id=tenant_id,
                run_id=run_id,
                error=str(e),
            )
            raise

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
                "committed": False,
            }

    result = run_async(_wrapper())

    if run_id and result.get("committed") is True:
        logger.info(
            "Structure building committed, retriggering run pipeline",
            document_version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            run_id=run_id,
            clause_tree_ref=result.get("clause_tree_ref"),
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
    2) читает layout по sanitization-first контракту;
    3) строит clause_tree;
    4) сохраняет clause_tree в хранилище;
    5) обновляет clause_tree_ref и статус документа;
    6) делает flush -> verify -> commit;
    7) возвращает committed=True только после commit.
    """
    _ = extra_args

    start = time.time()
    store = ArtifactStore(settings)

    v_id = uuid.UUID(document_version_id)

    ver_repo = DocumentVersionRepository(uow.session)
    doc_repo = DocumentRepository(uow.session)

    version = await ver_repo.get_by_id(v_id)
    if not version:
        raise PermanentError(
            f"DocumentVersion {v_id} not found",
            details={"stage": "structure", "kind": "version_not_found"},
        )

    doc = await doc_repo.get_by_id(version.document_id)
    if not doc:
        raise PermanentError(
            f"Document {version.document_id} not found",
            details={"stage": "structure", "kind": "document_not_found"},
        )

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
            "status": DocumentStatus.STRUCTURED.value,
            "document_id": str(doc.id),
            "document_version_id": str(v_id),
            "skipped": True,
            "committed": False,
        }

    allow_legacy_layout_fallback = bool(
        getattr(settings, "ALLOW_LEGACY_LAYOUT_FALLBACK", False)
    )

    sanitized_layout_ref = getattr(version, "layout_primary_sanitized_ref", None)
    primary_layout_ref = getattr(version, "layout_primary_ref", None)

    layout_ref = sanitized_layout_ref
    layout_source = "layout_primary_sanitized_ref"

    if not layout_ref and allow_legacy_layout_fallback:
        layout_ref = primary_layout_ref
        layout_source = "layout_primary_ref_legacy_fallback"

        logger.warning(
            "Structure builder is using legacy unsanitized layout fallback",
            document_id=str(doc.id),
            document_version_id=str(v_id),
            layout_primary_ref=primary_layout_ref,
        )

    if not layout_ref:
        raise PermanentError(
            "Sanitized layout is required for structure building: "
            f"doc={doc.id}, version={v_id}",
            details={
                "stage": "structure",
                "kind": "missing_sanitized_layout",
                "allow_legacy_layout_fallback": allow_legacy_layout_fallback,
            },
        )

    try:
        raw_layout = store.get_json(layout_ref)
    except Exception as e:
        logger.exception(
            "Failed to read layout for structure building",
            document_id=str(doc.id),
            document_version_id=str(v_id),
            layout_ref=layout_ref,
            layout_source=layout_source,
            error=str(e),
        )
        raise PermanentError(
            f"Failed to read layout for structure building: {e}",
            details={"stage": "structure", "kind": "layout_read_error"},
        )

    elements = raw_layout.get("elements", [])
    if not elements:
        raise PermanentError(
            f"No elements found in layout for version {v_id}",
            details={"stage": "structure", "kind": "empty_layout"},
        )

    builder = StructureBuilder()
    try:
        clause_tree = builder.build(
            document_id=str(doc.id),
            elements=elements,
        )
    except Exception as e:
        logger.exception(
            "Failed to build clause tree",
            document_id=str(doc.id),
            document_version_id=str(v_id),
            layout_ref=layout_ref,
            error=str(e),
        )
        raise PermanentError(
            f"Failed to build clause tree: {e}",
            details={"stage": "structure", "kind": "structure_build_error"},
        )

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

    try:
        clause_tree_ref = store.put_json(clause_tree_path, clause_tree.to_dict())
    except Exception as e:
        logger.exception(
            "Failed to store clause tree",
            document_id=str(doc.id),
            document_version_id=str(v_id),
            clause_tree_path=clause_tree_path,
            error=str(e),
        )
        raise PermanentError(
            f"Failed to store clause tree: {e}",
            details={"stage": "structure", "kind": "clause_tree_store_error"},
        )

    updated_version = await ver_repo.update_refs(
        version_id=v_id,
        clause_tree_ref=clause_tree_ref,
    )
    if not updated_version:
        raise PermanentError(
            f"Failed to update clause_tree_ref for version {v_id}",
            details={"stage": "structure", "kind": "version_update_failed"},
        )

    updated_doc = await doc_repo.update_status(
        doc.id,
        DocumentStatus.STRUCTURED.value,
        processing_error_details=None,
    )
    if not updated_doc:
        raise PermanentError(
            f"Failed to update document status to STRUCTURED for doc {doc.id}",
            details={"stage": "structure", "kind": "document_status_update_failed"},
        )

    await uow.session.flush()

    refreshed_version = await ver_repo.get_by_id(v_id)
    refreshed_clause_tree_ref = (
        getattr(refreshed_version, "clause_tree_ref", None)
        if refreshed_version
        else None
    )

    if not refreshed_version:
        raise TransientError(
            f"DocumentVersion {v_id} is not visible after flush"
        )

    if not refreshed_clause_tree_ref:
        raise TransientError(
            f"clause_tree_ref is not visible after flush for version {v_id}"
        )

    if refreshed_clause_tree_ref != clause_tree_ref:
        raise TransientError(
            f"clause_tree_ref mismatch after flush for version {v_id}"
        )

    await uow.session.commit()

    duration = round(time.time() - start, 2)

    logger.info(
        "Structure building committed successfully",
        document_id=str(doc.id),
        document_version_id=str(v_id),
        clause_tree_ref=clause_tree_ref,
        layout_source=layout_source,
        layout_ref=layout_ref,
        confidence=getattr(clause_tree, "structure_confidence", None),
        is_degraded=getattr(clause_tree, "degraded", None),
        duration_seconds=duration,
        status=DocumentStatus.STRUCTURED.value,
    )

    return {
        "status": DocumentStatus.STRUCTURED.value,
        "document_id": str(doc.id),
        "document_version_id": str(v_id),
        "clause_tree_ref": clause_tree_ref,
        "layout_ref": layout_ref,
        "layout_source": layout_source,
        "confidence": getattr(clause_tree, "structure_confidence", None),
        "is_degraded": getattr(clause_tree, "degraded", None),
        "duration_seconds": duration,
        "committed": True,
    }


async def _mark_failed(
    uow: UnitOfWork,
    document_version_id: str,
    *,
    message: str,
) -> None:
    """
    Best-effort перевод документа в FAILED,
    если стадия structure завершилась постоянной ошибкой.
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

    
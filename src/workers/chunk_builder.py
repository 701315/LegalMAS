# src/workers/chunk_builder.py

"""
Chunk Builder Worker.

Назначение:
- Построить canonical snapshot чанков (section / clause / subclause)
  через единый сервис ChunkSnapshotBuilder.
- Сохранить snapshot в MinIO и обновить ссылку chunks_ref в DocumentVersion.
- Обновить статус документа: STRUCTURED -> CHUNKED.
- В будущем: запускать downstream-задачи, которым нужны готовые чанки.

Позиция в пайплайне:
- import -> convert -> build_primary_language_source -> extract -> pii
  -> structure -> chunking -> classify/checks/...

Контракт стадии:
- Источник чанков — только canonical downstream-артефакты:
  * layout_primary_sanitized_ref / layout_primary_ref (определяется внутри ChunkSnapshotBuilder),
  * clause_tree_ref.
- В самом воркере нет собственных layout-fallback’ов; они централизованы
  в ChunkSnapshotBuilder.
- В нормальном боевом режиме layout_kind=layout_primary_sanitized_ref;
  fallback на layout_primary_ref допускается только через feature flag
  в ChunkSnapshotBuilder.
- retrigger downstream допустим только после подтверждённого commit
  результатов chunking (committed=True).
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from core.config import settings
from core.constants import DocumentStatus
from core.exceptions import PermanentError, TransientError, QuarantineError
from core.logging import get_logger
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.uow import UnitOfWork, db_uow
from engine.content.chunk_snapshot_builder import ChunkSnapshotBuilder
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from services.run_orchestrator_trigger import retrigger_run_pipeline
from storage.artifact_store import ArtifactPath, ArtifactStore

logger = get_logger(__name__)


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.build_chunks",
    queue="default",
)
def build_chunks(
    self,
    document_version_id: str,
    document_id: str,
    deal_id: str,
    tenant_id: str,
    run_id: str | None = None,
    **kwargs: Any,
) -> dict:
    """
    Sync Celery entry point для построения чанков.

    Поведение:
    - выполняет только свою стадию chunking;
    - при PermanentError переводит документ в FAILED;
    - при TransientError отдаёт управление retry-механизму;
    - при QuarantineError переводит документ в карантин по стадии chunking;
    - при успехе будит оркестратор только после commit.
    """

    async def _wrapper() -> dict:
        try:
            async with db_uow() as uow:
                return await _build_chunks_async(
                    document_version_id=document_version_id,
                    document_id=document_id,
                    deal_id=deal_id,
                    tenant_id=tenant_id,
                    run_id=run_id,
                    uow=uow,
                )

        except TransientError as e:
            logger.warning(
                "Transient error during chunk building; task should be retried",
                document_id=document_id,
                document_version_id=document_version_id,
                deal_id=deal_id,
                tenant_id=tenant_id,
                run_id=run_id,
                error=str(e),
            )
            raise

        except QuarantineError as e:
            # Мягкий карантин: документ не FAILED, но chunking дальше не идёт.
            logger.warning(
                "Quarantine during chunk building",
                document_id=document_id,
                document_version_id=document_version_id,
                deal_id=deal_id,
                tenant_id=tenant_id,
                run_id=run_id,
                reason=getattr(e, "reason", None),
                error=str(e),
            )
            async with db_uow() as uow_status:
                await _mark_quarantined(
                    uow=uow_status,
                    document_uuid=uuid.UUID(document_id),
                    message=str(e),
                    reason=getattr(e, "reason", "emptychunks"),
                    run_id=uuid.UUID(run_id) if run_id else None,
                )
            return {
                "status": DocumentStatus.QUARANTINE.value,
                "document_id": document_id,
                "document_version_id": document_version_id,
                "quarantined": True,
                "quarantine_reason": getattr(e, "reason", "emptychunks"),
                "error": str(e),
                "committed": False,
            }

        except PermanentError as e:
            logger.error(
                "Permanent error during chunk building",
                document_id=document_id,
                document_version_id=document_version_id,
                deal_id=deal_id,
                tenant_id=tenant_id,
                run_id=run_id,
                error=str(e),
            )
            async with db_uow() as uow_status:
                await _mark_failed(
                    uow=uow_status,
                    document_uuid=uuid.UUID(document_id),
                    message=str(e),
                    run_id=uuid.UUID(run_id) if run_id else None,
                )
            return {
                "status": DocumentStatus.FAILED.value,
                "document_id": document_id,
                "document_version_id": document_version_id,
                "error": str(e),
                "committed": False,
            }

    result = run_async(_wrapper())

    if run_id and result.get("committed") is True:
        logger.info(
            "Chunk building committed, retriggering run pipeline",
            document_id=document_id,
            document_version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            run_id=run_id,
            chunks_ref=result.get("chunks_ref"),
            layout_kind=result.get("layout_kind"),
            layout_ref=result.get("layout_ref"),
        )
        retrigger_run_pipeline(
            run_id=run_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
        )

    return result


async def _build_chunks_async(
    *,
    document_version_id: str,
    document_id: str,
    deal_id: str,
    tenant_id: str,
    run_id: str | None,
    uow: UnitOfWork,
) -> dict:
    """
    Асинхронная логика построения чанков.

    Шаги:
    1) загружаем Document и DocumentVersion;
    2) проверяем, что есть clause_tree_ref (structure уже выполнен);
    3) строим snapshot чанков через ChunkSnapshotBuilder;
    4) сохраняем snapshot в MinIO;
    5) обновляем chunks_ref в DocumentVersion и статус документа -> CHUNKED;
    6) flush -> verify -> commit;
    7) возвращаем committed=True только после успешного commit.
    """

    start = time.time()
    store = ArtifactStore(settings)

    ver_repo = DocumentVersionRepository(uow.session)
    doc_repo = DocumentRepository(uow.session)

    v_id = uuid.UUID(document_version_id)
    d_id = uuid.UUID(document_id)

    version = await ver_repo.get_by_id(v_id)
    if not version:
        raise PermanentError(
            f"DocumentVersion {v_id} not found",
            details={"stage": "chunking", "kind": "version_not_found"},
        )

    doc = await doc_repo.get_by_id(d_id)
    if not doc:
        raise PermanentError(
            f"Document {d_id} not found",
            details={"stage": "chunking", "kind": "document_not_found"},
        )

    if (
        getattr(version, "chunks_ref", None)
        and doc.status == DocumentStatus.CHUNKED.value
    ):
        logger.info(
            "Chunks snapshot already exists and document is CHUNKED, skipping rebuild",
            document_id=str(doc.id),
            document_version_id=str(version.id),
            chunks_ref=version.chunks_ref,
        )
        return {
            "status": DocumentStatus.CHUNKED.value,
            "document_id": str(doc.id),
            "document_version_id": str(version.id),
            "chunks_ref": version.chunks_ref,
            "skipped": True,
            "committed": False,
        }

    clause_tree_ref = getattr(version, "clause_tree_ref", None)
    if not clause_tree_ref:
        raise PermanentError(
            f"Cannot build chunks: clause_tree_ref is missing for version {v_id}",
            details={"stage": "chunking", "kind": "missing_clause_tree"},
        )

    snapshot_builder = ChunkSnapshotBuilder(store=store)
    try:
        snapshot = await snapshot_builder.build_snapshot(
            session=uow.session,
            doc_id=d_id,
            target_tokens=300,
            max_tokens=800,
            overlap_ratio=0.15,
        )
    except PermanentError:
        raise
    except Exception as e:
        logger.exception(
            "ChunkSnapshotBuilder failed",
            document_id=str(doc.id),
            document_version_id=str(v_id),
            clause_tree_ref=clause_tree_ref,
            error=str(e),
        )
        raise PermanentError(
            f"ChunkSnapshotBuilder failed: {e}",
            details={"stage": "chunking", "kind": "snapshot_builder_error"},
        )

    # Разбираем source-info из snapshot (используется и в логах, и ниже).
    source_info = snapshot.get("source") or {}
    layout_ref = source_info.get("layout_ref")
    layout_kind = source_info.get("layout_kind")
    snapshot_clause_tree_ref = source_info.get("clause_tree_ref")

    # После успешной сборки snapshot проверяем, что в нём есть реально
    # пригодные для анализа чанки. Пустой snapshot (без clause/subclause)
    # трактуем как "нет анализируемого контента" и отправляем в карантин.
    chunks = snapshot.get("chunks") or {}
    clause_chunks = chunks.get("clause") or []
    subclause_chunks = chunks.get("subclause") or []

    if not clause_chunks and not subclause_chunks:
        logger.warning(
            "ChunkSnapshotBuilder produced empty snapshot (no clause/subclause chunks)",
            extra={
                "document_id": str(doc.id),
                "document_version_id": str(version.id),
                "clause_tree_ref": clause_tree_ref,
                "layout_ref": layout_ref,
            },
        )
        raise QuarantineError(
            "No usable chunks built from clause tree and layout",
            document_id=str(doc.id),
            reason="emptychunks",
            details={
                "document_version_id": str(version.id),
                "clause_tree_ref": clause_tree_ref,
                "layout_ref": layout_ref,
            },
        )

    if not layout_ref or not layout_kind:
        logger.warning(
            "Chunk snapshot source metadata is incomplete",
            document_id=str(doc.id),
            document_version_id=str(v_id),
            snapshot_source=source_info,
        )

    chunks_path = ArtifactPath.chunks(
        tenant_id=tenant_id,
        deal_id=deal_id,
        document_id=str(doc.id),
    )

    try:
        chunks_ref = store.put_json(chunks_path, snapshot)
    except Exception as e:
        logger.exception(
            "Failed to store chunks snapshot",
            document_id=str(doc.id),
            document_version_id=str(v_id),
            chunks_path=chunks_path,
            error=str(e),
        )
        raise PermanentError(
            f"Failed to store chunks snapshot: {e}",
            details={"stage": "chunking", "kind": "chunks_store_error"},
        )

    updated_version = await ver_repo.update_refs(
        version_id=v_id,
        chunks_ref=chunks_ref,
    )
    if not updated_version:
        raise PermanentError(
            f"Failed to update chunks_ref for version {v_id}",
            details={"stage": "chunking", "kind": "version_update_failed"},
        )

    updated_doc = await doc_repo.update_status(
        doc.id,
        DocumentStatus.CHUNKED.value,
        processing_error_details=None,
    )
    if not updated_doc:
        raise PermanentError(
            f"Failed to update document status to CHUNKED for doc {doc.id}",
            details={"stage": "chunking", "kind": "document_status_update_failed"},
        )

    await uow.session.flush()

    refreshed_version = await ver_repo.get_by_id(v_id)
    if not refreshed_version:
        raise TransientError(
            f"DocumentVersion {v_id} is not visible after flush"
        )

    refreshed_chunks_ref = getattr(refreshed_version, "chunks_ref", None)
    if not refreshed_chunks_ref:
        raise TransientError(
            f"chunks_ref is not visible after flush for version {v_id}"
        )

    if refreshed_chunks_ref != chunks_ref:
        raise TransientError(
            f"chunks_ref mismatch after flush for version {v_id}"
        )

    await uow.session.commit()

    duration = round(time.time() - start, 2)

    logger.info(
        "Chunks snapshot built and committed successfully",
        document_id=str(doc.id),
        document_version_id=str(v_id),
        chunks_ref=chunks_ref,
        clause_tree_ref=clause_tree_ref,
        snapshot_clause_tree_ref=snapshot_clause_tree_ref,
        layout_ref=layout_ref,
        layout_kind=layout_kind,
        duration_seconds=duration,
        status=DocumentStatus.CHUNKED.value,
    )

    return {
        "status": DocumentStatus.CHUNKED.value,
        "document_id": str(doc.id),
        "document_version_id": str(v_id),
        "chunks_ref": chunks_ref,
        "clause_tree_ref": clause_tree_ref,
        "snapshot_clause_tree_ref": snapshot_clause_tree_ref,
        "layout_ref": layout_ref,
        "layout_kind": layout_kind,
        "duration_seconds": duration,
        "committed": True,
    }


async def _mark_quarantined(
    uow: UnitOfWork,
    document_uuid: uuid.UUID,
    *,
    message: str,
    reason: str,
    run_id: uuid.UUID | None,
) -> None:
    """
    Перевести документ в карантин на стадии chunking.

    Используем отдельный helper, чтобы не путать с FAILED:
    - статус документа остаётся прежним,
      а подробности попадают в таблицу карантина.
    """
    doc_repo = DocumentRepository(uow.session)
    await doc_repo.set_quarantined(
        document_uuid,
        stage="chunking",
        message=message,
        reason=reason,
        run_id=run_id,
    )


async def _mark_failed(
    uow: UnitOfWork,
    document_uuid: uuid.UUID,
    *,
    message: str,
    run_id: uuid.UUID | None,
) -> None:
    """
    Best-effort перевод документа в FAILED при ошибке chunking.
    """
    doc_repo = DocumentRepository(uow.session)
    await doc_repo.set_failed(
        document_uuid,
        stage="chunking",
        message=message,
        reason="chunking_error",
        run_id=run_id,
    )


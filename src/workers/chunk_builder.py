# src/workers/chunk_builder.py

from __future__ import annotations

"""
Chunk Builder Worker.

Назначение:
- В legacy-режиме: построить canonical snapshot чанков (section / clause / subclause)
  через ChunkSnapshotBuilder и сохранить его в chunks_ref (schema_version=1).
- В v2-режиме: построить per-segment chunk snapshots через SegmentChunkBuilderV2,
  сохранить их в MinIO, обновить segment_chunks_ref в DocumentSegment и
  сохранить file-level chunks_manifest_v2_ref в DocumentVersion.
- Обновить статус документа: STRUCTURED -> CHUNKED.
- Запустить downstream-орchestrator только после committed=True.

Позиция в пайплайне:
- import -> convert -> build_primary_language_source -> extract -> pii
  -> structure -> chunking -> classify/checks/...
"""

import time
import uuid
from typing import Any

from core.config import settings
from core.constants import DocumentStatus
from core.exceptions import PermanentError, QuarantineError, TransientError
from core.logging import get_logger
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_segment_repo import DocumentSegmentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.uow import UnitOfWork, db_uow
from engine.content.chunk_snapshot_builder import ChunkSnapshotBuilder
from engine.content.segment_chunk_builder_v2 import (
    FileChunkManifestV2,
    FileChunkManifestSegmentV2,
    SegmentChunkBuilderV2,
    SegmentChunkSnapshotV2,
)
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
                # TODO: завести feature flag / setting вместо захардкоженного False.
                use_v2 = settings.CHUNKS_V2_ENABLED

                if use_v2:
                    return await _build_chunks_v2_async(
                        document_version_id=document_version_id,
                        document_id=document_id,
                        deal_id=deal_id,
                        tenant_id=tenant_id,
                        run_id=run_id,
                        uow=uow,
                    )
                else:
                    return await _build_chunks_legacy_async(
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
            chunks_manifest_v2_ref=result.get("chunks_manifest_v2_ref"),
        )
        retrigger_run_pipeline(
            run_id=run_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
        )

    return result


async def _build_chunks_legacy_async(
    *,
    document_version_id: str,
    document_id: str,
    deal_id: str,
    tenant_id: str,
    run_id: str | None,
    uow: UnitOfWork,
) -> dict:
    """
    Текущая legacy-логика построения чанков (schema_version=1, один snapshot на файл).
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

    existing_chunks_ref = getattr(version, "chunks_ref", None)

    existing_schema_version: int | None = None
    if existing_chunks_ref:
        try:
            existing_snapshot = store.get_json(existing_chunks_ref)
            if isinstance(existing_snapshot, dict):
                existing_schema_version = existing_snapshot.get("schema_version")
        except Exception as e:
            logger.warning(
                "Failed to load existing chunk snapshot for version, will rebuild",
                document_id=str(doc.id),
                document_version_id=str(version.id),
                chunks_ref=existing_chunks_ref,
                error=str(e),
            )

    force_rebuild = False  # TODO: прокинуть из Celery kwargs при необходимости.

    needs_rebuild = (
        force_rebuild
        or not existing_chunks_ref
        or doc.status != DocumentStatus.CHUNKED.value
        or existing_schema_version != 1
    )

    if not needs_rebuild:
        logger.info(
            "Chunks snapshot already exists with expected schema_version, skipping rebuild",
            document_id=str(doc.id),
            document_version_id=str(version.id),
            chunks_ref=existing_chunks_ref,
            schema_version=existing_schema_version,
        )
        return {
            "status": DocumentStatus.CHUNKED.value,
            "document_id": str(doc.id),
            "document_version_id": str(version.id),
            "chunks_ref": existing_chunks_ref,
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

    source_info = snapshot.get("source") or {}
    layout_ref = source_info.get("layout_ref")
    layout_kind = source_info.get("layout_kind")
    snapshot_clause_tree_ref = source_info.get("clause_tree_ref")

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
        "Chunks snapshot (legacy) built and committed successfully",
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


async def _build_chunks_v2_async(
    *,
    document_version_id: str,
    document_id: str,
    deal_id: str,
    tenant_id: str,
    run_id: str | None,
    uow: UnitOfWork,
) -> dict:
    """
    Новая v2-логика построения чанков:
    - строим per-segment snapshots и file-level manifest через SegmentChunkBuilderV2;
    - сохраняем segment_chunks и manifest в MinIO;
    - обновляем segment_chunks_ref и chunks_manifest_v2_ref в БД;
    - статус документа -> CHUNKED.
    """

    start = time.time()
    store = ArtifactStore(settings)

    ver_repo = DocumentVersionRepository(uow.session)
    doc_repo = DocumentRepository(uow.session)
    seg_repo = DocumentSegmentRepository(uow.session)

    v_id = uuid.UUID(document_version_id)
    d_id = uuid.UUID(document_id)

    version = await ver_repo.get_by_id(v_id)
    if not version:
        raise PermanentError(
            f"DocumentVersion {v_id} not found",
            details={"stage": "chunking_v2", "kind": "version_not_found"},
        )

    doc = await doc_repo.get_by_id(d_id)
    if not doc:
        raise PermanentError(
            f"Document {d_id} not found",
            details={"stage": "chunking_v2", "kind": "document_not_found"},
        )

    segments = await seg_repo.list_by_version(v_id)
    if not segments:
        raise PermanentError(
            f"No DocumentSegment rows found for version {v_id}",
            details={"stage": "chunking_v2", "kind": "segments_missing"},
        )

    builder_v2 = SegmentChunkBuilderV2(store=store)

    try:
        file_manifest, segment_snapshots = await builder_v2.build_for_version(
            session=uow.session,
            document_version_id=v_id,
            target_tokens=300,
            max_tokens=800,
            overlap_ratio=0.15,
        )
    except PermanentError:
        raise
    except Exception as e:
        logger.exception(
            "SegmentChunkBuilderV2 failed",
            document_id=str(doc.id),
            document_version_id=str(v_id),
            error=str(e),
        )
        raise PermanentError(
            f"SegmentChunkBuilderV2 failed: {e}",
            details={"stage": "chunking_v2", "kind": "segment_builder_error"},
        )

    if not segment_snapshots:
        logger.warning(
            "SegmentChunkBuilderV2 produced no segment snapshots",
            document_id=str(doc.id),
            document_version_id=str(v_id),
        )
        raise QuarantineError(
            "No usable segment chunks built",
            document_id=str(doc.id),
            reason="emptysegments",
            details={
                "document_version_id": str(version.id),
            },
        )

    # 1. Сохраняем per-segment snapshots в MinIO и обновляем segment_chunks_ref.
    segments_by_id = {s.segment_id: s for s in segments}
    manifest_segments: dict[str, FileChunkManifestSegmentV2] = {
        s.segment_id: s for s in file_manifest.segments
    }

    for snapshot in segment_snapshots:
        seg = segments_by_id.get(snapshot.segment_id)
        if seg is None:
            raise PermanentError(
                f"Internal error: no DocumentSegment row for snapshot.segment_id={snapshot.segment_id}",
                details={"stage": "chunking_v2", "kind": "segment_not_found_for_snapshot"},
            )

        chunk_path = ArtifactPath.segment_chunks(
            tenant_id=tenant_id,
            deal_id=deal_id,
            document_id=str(doc.id),
            segment_id=snapshot.segment_id,
        )

        try:
            segment_chunks_ref = store.put_json(chunk_path, snapshot.to_dict())
        except Exception as e:
            logger.exception(
                "Failed to store segment chunk snapshot",
                document_id=str(doc.id),
                document_version_id=str(v_id),
                segment_id=snapshot.segment_id,
                chunks_path=chunk_path,
                error=str(e),
            )
            raise PermanentError(
                f"Failed to store segment chunk snapshot: {e}",
                details={"stage": "chunking_v2", "kind": "segment_chunks_store_error"},
            )

        # обновляем в БД segment_chunks_ref
        seg.segment_chunks_ref = segment_chunks_ref  # локально в объекте
        # и прокидываем в manifest
        manifest_segment = manifest_segments.get(snapshot.segment_id)
        if manifest_segment is not None:
            manifest_segment.segment_chunks_ref = segment_chunks_ref

    # 2. Перезаписываем DocumentSegment rows одним replace (atomic pattern).
    await seg_repo.replace_segments(
        document_version_id=v_id,
        items=list(segments),
    )

    # 3. Сохраняем file-level manifest в MinIO.
    manifest_path = ArtifactPath.chunks_manifest_v2(
        tenant_id=tenant_id,
        deal_id=deal_id,
        document_id=str(doc.id),
    )

    try:
        chunks_manifest_v2_ref = store.put_json(manifest_path, file_manifest.to_dict())
    except Exception as e:
        logger.exception(
            "Failed to store file chunk manifest v2",
            document_id=str(doc.id),
            document_version_id=str(v_id),
            manifest_path=manifest_path,
            error=str(e),
        )
        raise PermanentError(
            f"Failed to store file chunk manifest v2: {e}",
            details={"stage": "chunking_v2", "kind": "manifest_store_error"},
        )

    # 4. Обновляем DocumentVersion: записываем ссылку на v2 manifest.
    # ВАЖНО: здесь предполагается, что в DocumentVersion есть поле chunks_manifest_v2_ref
    # и в репозитории есть метод update_refs_v2 или расширенный update_refs.
    updated_version = await ver_repo.update_refs(
        version_id=v_id,
        # legacy chunks_ref можно оставить как есть, либо None.
        chunks_manifest_v2_ref=chunks_manifest_v2_ref,  # type: ignore[arg-type]
    )
    if not updated_version:
        raise PermanentError(
            f"Failed to update chunks_manifest_v2_ref for version {v_id}",
            details={"stage": "chunking_v2", "kind": "version_update_failed"},
        )

    updated_doc = await doc_repo.update_status(
        doc.id,
        DocumentStatus.CHUNKED.value,
        processing_error_details=None,
    )
    if not updated_doc:
        raise PermanentError(
            f"Failed to update document status to CHUNKED for doc {doc.id}",
            details={"stage": "chunking_v2", "kind": "document_status_update_failed"},
        )

    await uow.session.flush()

    refreshed_version = await ver_repo.get_by_id(v_id)
    if not refreshed_version:
        raise TransientError(
            f"DocumentVersion {v_id} is not visible after flush (v2)"
        )

    refreshed_manifest_ref = getattr(refreshed_version, "chunks_manifest_v2_ref", None)
    if not refreshed_manifest_ref:
        raise TransientError(
            f"chunks_manifest_v2_ref is not visible after flush for version {v_id}"
        )

    if refreshed_manifest_ref != chunks_manifest_v2_ref:
        raise TransientError(
            f"chunks_manifest_v2_ref mismatch after flush for version {v_id}"
        )

    await uow.session.commit()

    duration = round(time.time() - start, 2)

    logger.info(
        "Segment chunks and file manifest v2 built and committed successfully",
        document_id=str(doc.id),
        document_version_id=str(v_id),
        chunks_manifest_v2_ref=chunks_manifest_v2_ref,
        segments_count=len(segment_snapshots),
        duration_seconds=duration,
        status=DocumentStatus.CHUNKED.value,
    )

    # Для backward-совместимости можно продолжать возвращать chunks_ref=None.
    return {
        "status": DocumentStatus.CHUNKED.value,
        "document_id": str(doc.id),
        "document_version_id": str(v_id),
        "chunks_ref": None,
        "chunks_manifest_v2_ref": chunks_manifest_v2_ref,
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

    

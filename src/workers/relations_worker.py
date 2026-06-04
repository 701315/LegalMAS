# src/workers/relations_worker.py

"""
Relations Worker — построение дедупликации, связей и семей документов по сделке.

Назначение:
- Один раз на сделку пройти по всем документам и:
  1) сделать точный дедуп по SHA‑256;
  2) загрузить первые ~2000 символов текста для каждого документа;
  3) найти связи между документами (по имени файла и текстовым паттернам);
  4) собрать семьи документов (master + appendices + amendments + версии);
  5) сохранить связи и семьи в БД;
  6) записать audit‑лог по результатам.

Архитектурный паттерн:
- Снаружи — синхронная Celery‑таска build_relations (def), чтобы Celery
  мог корректно сериализовать результат в prefork‑модели.
- Внутри — один переход sync → async через run_async, всё
  взаимодействие с БД и MinIO реализовано в _build_relations_async() и helpers.

Audit trail:
- На успешном завершении пишет BUILD_RELATIONS с агрегированным отчётом.
- Audit logging best-effort: сбой аудита не должен ломать стадию.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from classifiers.yaml_registry import YAMLRegistry
from core.config import settings
from core.constants import DocumentStatus
from core.logging import get_logger
from db.repositories import (
    AuditRepository,
    DocumentRepository,
    DocumentVersionRepository,
    RelationRepository,
)
from db.uow import db_uow
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from ops.metrics import get_metrics
from services.relations.dedup import ExactDedupService
from services.relations.detector import RelationDetector
from services.relations.family_builder import FamilyBuilder
from services.relations.models import (
    DedupResult,
    DetectedRelation,
    FamilyGroup,
    RelationsReport,
)
from storage.artifact_store import ArtifactStore

logger = get_logger(__name__)


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.build_relations",
    track_job=False,
    queue="default",
)
def build_relations(
    self,
    deal_id: str,
    tenant_id: str,
    stage_execution_id: str | None = None,
    orchestration_strategy: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Синхронная Celery‑таска построения связей и семей документов.

    Внутри:
      - один раз передаём управление в async‑ядро _build_relations_async()
        через run_async;
      - открываем UnitOfWork через db_uow();
      - возвращаем агрегированный отчёт (кол‑во документов, дубликатов, семей).
    """
    _ = self

    async def _wrapper() -> dict[str, Any]:
        async with db_uow() as uow:
            return await _build_relations_async(deal_id, tenant_id, uow.session)

    return run_async(_wrapper())


async def _build_relations_async(
    deal_id: str,
    tenant_id: str,
    db: AsyncSession,
) -> dict[str, Any]:
    """
    Асинхронное ядро воркера: вся бизнес‑логика построения связей/семей.
    """
    metrics = get_metrics()

    start = time.time()
    logger.info("Build relations started", deal_id=deal_id)

    # ВАЖНО: приводим deal_id к UUID один раз и используем далее.
    deal_uuid = uuid.UUID(deal_id)

    # Шаг 0: очистка старых связей и семей по сделке (идемпотентность).
    relation_repo = RelationRepository(db)
    await relation_repo.delete_all_for_deal(deal_uuid)

    # Step 1: load deal documents
    docs = await _load_deal_documents(deal_id, db)
    if not docs:
        logger.info("No documents for deal", deal_id=deal_id)
        duration = time.time() - start
        return {
            "deal_id": deal_id,
            "total_documents": 0,
            "exact_duplicates": 0,
            "relations": 0,
            "families": 0,
            "duration_seconds": round(duration, 2),
            "committed": False,
        }

    original_total = len(docs)

    # Step 2: Exact dedup (SHA‑256)
    dedup_relations: list[DetectedRelation] = []
    dedup_result: DedupResult | None = None

    if settings.DEDUP_EXACT_ENABLED:
        deduper = ExactDedupService()
        dedup_result, dedup_relations = deduper.find_duplicates(docs)

        kept_ids = set(dedup_result.kept_doc_ids) if dedup_result else set()
        if kept_ids:
            docs = [d for d in docs if d["id"] in kept_ids]

        logger.info(
            "Exact dedup summary",
            deal_id=deal_id,
            total=dedup_result.total_documents if dedup_result else len(docs),
            duplicates=dedup_result.exact_duplicates if dedup_result else 0,
        )

        # Optionally mark duplicates in DB
        if dedup_result and dedup_result.marked_doc_ids:
            await _mark_duplicates(dedup_result.marked_doc_ids, db)

    # Step 3: load text snippets for text-based relations
    await _load_text_snippets(docs, tenant_id=tenant_id, deal_id=deal_id, db=db)

    # Step 4: relation detection
    traversal_start = time.time()

    detector = RelationDetector()
    detected_relations = detector.detect_all_relations(docs)

    # Add version relations from dedup
    all_relations: list[DetectedRelation] = detected_relations + dedup_relations

    # Step 5: family building
    family_builder = FamilyBuilder()
    families: list[FamilyGroup] = family_builder.build_families(docs, all_relations)

    metrics.relation_traversal_latency.observe(time.time() - traversal_start)

    # Step 6: save relations and families using repositories
    await _save_relations(deal_id, all_relations, db)
    await _save_families(deal_id, families, db)

    # Step 7: audit + logging
    report = RelationsReport(
        deal_id=deal_id,
        dedup_result=dedup_result or DedupResult(total_documents=len(docs)),
        relations_found=len(all_relations),
        families_created=len(families),
        family_groups=families,
        errors=[],
    )
    await _write_audit_log(tenant_id=tenant_id, deal_id=deal_id, report=report, db=db)

    if families:
        masters_with_yaml = sum(1 for f in families if f.master_yaml_available)
        master_levels = [
            f.master_classification_level for f in families if f.master_classification_level
        ]
        logger.info(
            "Family masters classification summary",
            deal_id=deal_id,
            families=len(families),
            masters_with_yaml=masters_with_yaml,
            master_levels=master_levels,
        )

    duration = time.time() - start
    logger.info(
        "Build relations finished",
        deal_id=deal_id,
        families=len(families),
        duration_seconds=round(duration, 2),
    )

    return {
        "deal_id": deal_id,
        "total_documents": original_total,
        "exact_duplicates": dedup_result.exact_duplicates if dedup_result else 0,
        "relations": len(all_relations),
        "families": len(families),
        "duration_seconds": round(duration, 2),
        "committed": True,
    }


# =====================================================================
# DB helpers (работают на AsyncSession через db_uow)
# =====================================================================


async def _load_deal_documents(deal_id: str, db: AsyncSession) -> list[dict]:
    """
    Load all non‑quarantined documents for a deal, with classification info.

    Для непрофессионального программиста:
    - Здесь мы подготавливаем упрощённый список документов для relations pipeline.
    - Важно: yaml_instruction_available больше НЕ читается из колонки БД.
    - Вместо этого мы вычисляем его runtime через YAMLRegistry по текущему doc_type.
    - Это делает поведение единым для всех частей системы и убирает риск рассинхрона.
    """
    repo = DocumentRepository(db)
    docs = await repo.get_by_deal(uuid.UUID(deal_id))

    # Берём registry один раз на весь список документов.
    # validate=False:
    # - не запускаем повторную тяжёлую валидацию паттернов на каждом вызове;
    # - используем уже загруженный singleton-реестр.
    registry = YAMLRegistry.get_instance(validate=False)

    return [
        {
            "id": str(d.id),
            "filename": d.filename,
            "folder_path": d.folder_path or "",
            "doc_type": d.doc_type or "",
            "sha256_file": d.sha256_file or "",
            "created_at": d.created_at.isoformat() if d.created_at else "",
            "status": d.status,
            # Classification fields from HybridClassifier (Stage 6)
            "classification_level": d.classification_level or "L0",
            "classification_confidence": float(d.classification_confidence or 0.0),
            "yaml_instruction_available": registry.get_config(d.doc_type or "") is not None,
            "applicable_triggers": d.applicable_triggers or [],
        }
        for d in docs
        if d.status not in (DocumentStatus.QUARANTINE.value,)
    ]


async def _load_text_snippets(
    documents: list[dict],
    tenant_id: str,
    deal_id: str,
    db: AsyncSession,
) -> list[dict]:
    """
    Load first ~2000 chars of layout text for each document.
    Prefer sanitized primary layout, fallback to primary layout
    for legacy / not-yet-PII documents.
    """
    _ = (tenant_id, deal_id)
    store = ArtifactStore()
    ver_repo = DocumentVersionRepository(db)

    for doc in documents:
        try:
            version = await ver_repo.get_latest(uuid.UUID(doc["id"]))
            if not version:
                doc["text_first_2000"] = ""
                continue

            # новый unified‑контракт
            layout_ref = getattr(version, "layout_primary_sanitized_ref", None) or getattr(
                version, "layout_primary_ref", None
            )
            if not layout_ref:
                doc["text_first_2000"] = ""
                continue

            layout = store.get_json(layout_ref)
            elements = layout.get("elements", [])
            text_parts = [e.get("text", "") for e in elements[:20]]
            doc["text_first_2000"] = " ".join(text_parts)[:2000]
        except Exception as e:
            logger.debug(
                "Failed to load text snippet",
                document_id=doc["id"],
                error=str(e),
            )
            doc["text_first_2000"] = ""

    return documents


async def _mark_duplicates(doc_ids: list[str], db: AsyncSession) -> None:
    """Mark documents as duplicates in DB."""
    repo = DocumentRepository(db)
    for doc_id in doc_ids:
        await repo.update_status(
            uuid.UUID(doc_id),
            "duplicate",
        )


async def _save_relations(
    deal_id: str,
    relations: list[DetectedRelation],
    db: AsyncSession,
) -> None:
    """Save detected relations to DB."""
    repo = RelationRepository(db)
    for rel in relations:
        await repo.create(
            deal_id=uuid.UUID(deal_id),
            source_doc_id=uuid.UUID(rel.source_doc_id),
            target_doc_id=uuid.UUID(rel.target_doc_id),
            relation_type=rel.relation_type,
            confidence=rel.confidence,
            evidence_text=rel.evidence_text,
        )
    # commit делает db_uow


async def _save_families(
    deal_id: str,
    families: list[FamilyGroup],
    db: AsyncSession,
) -> None:
    repo = RelationRepository(db)
    for family in families:
        db_family = await repo.create_family(
            deal_id=uuid.UUID(deal_id),
            master_doc_id=uuid.UUID(family.master_doc_id),
            master_classification_level=family.master_classification_level,
        )
        family.family_id = str(db_family.id)

        for member_id in family.member_doc_ids:
            await repo.create_family_member(
                family_id=db_family.id,
                document_id=uuid.UUID(member_id),
                relation_to_master=None,
            )


async def _write_audit_log(
    tenant_id: str,
    deal_id: str,
    report: RelationsReport,
    db: AsyncSession,
) -> None:
    """Write relations audit log entry."""
    repo = AuditRepository(db)
    try:
        await repo.log(
            tenant_id=uuid.UUID(tenant_id),
            deal_id=uuid.UUID(deal_id),
            action="BUILD_RELATIONS",
            actor="system",
            actor_role="worker",
            details=report.to_dict(),
        )
    except Exception as e:
        logger.warning(
            "Relations worker: failed to write audit log for BUILD_RELATIONS",
            deal_id=deal_id,
            tenant_id=tenant_id,
            error=str(e),
        )

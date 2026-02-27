"""
Relations Worker — runs dedup, relation detection, and family building.

This worker runs ONCE per deal after all documents are classified.
It processes all documents in the deal together (not per-document).

Pipeline:
1. Load all documents for the deal from DB
2. Run exact dedup (SHA256)
3. Load first 2000 chars of text for each document
4. Run relation detection (filename + text patterns)
5. Build families (master + appendix + amendment + versions)
6. Save all results to DB (document_relations, families)
7. Record audit log
"""

import time
import uuid
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import DocumentStatus
from src.core.exceptions import PermanentError
from src.core.logging import get_logger
from src.db.repositories import DocumentRepository, RelationRepository
from src.db.uow import db_uow
from src.queue.base_task import MASBaseTask
from src.queue.celery_app import celery_app
from src.services.relations.dedup import ExactDedupService
from src.services.relations.detector import RelationDetector
from src.services.relations.family_builder import FamilyBuilder
from src.services.relations.models import (
    DetectedRelation,
    FamilyGroup,
    DedupResult,
    RelationsReport,
)
from src.storage.artifact_store import ArtifactStore

logger = get_logger(__name__)


# =====================================================================
# Celery task (async, как import_worker / extract_worker)
# =====================================================================

@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.build_relations",
    track_job=False,
    queue="default",
)
async def build_relations(
    self,
    deal_id: str,
    tenant_id: str,
) -> dict:
    start = time.time()
    logger.info("Build relations started", deal_id=deal_id)

    async with db_uow() as uow:
        db: AsyncSession = uow.session

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
            }

        original_total = len(docs)  # <-- вот здесь

        # Step 2: Exact dedup (SHA-256)
        dedup_relations: List[DetectedRelation] = []
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
        detector = RelationDetector()
        detected_relations = detector.detect_all_relations(docs)

        # Add version relations from dedup
        all_relations: List[DetectedRelation] = detected_relations + dedup_relations

        # Step 5: family building
        family_builder = FamilyBuilder()
        families: List[FamilyGroup] = family_builder.build_families(docs, all_relations)

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
                f.master_classification_level
                for f in families
                if f.master_classification_level
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
    }


# =====================================================================
# DB helpers (работают на AsyncSession через db_uow)
# =====================================================================

async def _load_deal_documents(deal_id: str, db: AsyncSession) -> list[dict]:
    """Load all classified documents for a deal."""
    repo = DocumentRepository(db)
    docs = await repo.get_by_deal(uuid.UUID(deal_id))

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
            "classification_confidence": float(
                d.classification_confidence or 0.0
            ),
            "yaml_instruction_available": bool(
                getattr(d, "yaml_instruction_available", False)
            ),
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
    Load first 2000 chars of text_layout_raw for each document.
    This text is used for text-based relation detection.
    """
    from src.db.repositories import DocumentVersionRepository

    store = ArtifactStore()
    ver_repo = DocumentVersionRepository(db)

    for doc in documents:
        try:
            version = await ver_repo.get_latest(uuid.UUID(doc["id"]))
            if version and version.text_layout_raw_ref:
                raw_path = version.text_layout_raw_ref.replace(
                    f"s3://{store.bucket}/", ""
                )
                layout = store.get_json(raw_path)
                elements = layout.get("elements", [])
                text_parts = [
                    e.get("text", "") for e in elements[:20]
                ]
                doc["text_first_2000"] = " ".join(text_parts)[:2000]
            else:
                doc["text_first_2000"] = ""
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
    from src.db.repositories import DocumentRepository

    repo = DocumentRepository(db)
    for doc_id in doc_ids:
        await repo.update_status(
            uuid.UUID(doc_id),
            "duplicate",
        )


async def _save_relations(
    deal_id: str,
    relations: List[DetectedRelation],
    db: AsyncSession,
) -> None:
    """Save detected relations to DB."""
    from src.db.repositories import RelationRepository

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
    families: List[FamilyGroup],
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
    from src.db.repositories import AuditRepository

    repo = AuditRepository(db)
    await repo.log(
        tenant_id=uuid.UUID(tenant_id),
        deal_id=uuid.UUID(deal_id),
        action="BUILD_RELATIONS",
        actor="system",
        actor_role="system",
        details=report.to_dict(),
    )

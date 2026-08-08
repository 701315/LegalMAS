# src/engine/checks/enrichment_loader.py

"""
Enrichment loader: reads legal-unit enrichment artifacts for checks pipeline.

Responsibility:
- Read segment_meta["legal_units_enrichment_ref"] from ORM segment objects.
- Load enrichment sidecar from MinIO via ArtifactStore.
- Extract clause_functions and topic_tags as frozensets.
- Return SemanticEnrichmentContext (available or unavailable).

Design principles:
- Synchronous ArtifactStore call, no async needed here.
- Never raises: all errors -> SemanticEnrichmentContext.unavailable().
- No business logic: pure data extraction.
- Called once per segment in check_runner, result passed into executor.
"""

from __future__ import annotations

from typing import Any

from core.logging import get_logger
from engine.checks.semantic_context import SemanticEnrichmentContext
from storage.artifact_store import ArtifactStore

logger = get_logger(__name__)


def _extract_clause_functions(units: list[dict]) -> frozenset[str]:
    """
    Extract normalized clause_function values from enriched unit dicts.

    Handles missing/null/empty values gracefully.
    Returns lowercase stripped frozenset.
    """
    functions: set[str] = set()
    for unit in units:
        if not isinstance(unit, dict):
            continue
        cf = unit.get("clause_function")
        if cf and isinstance(cf, str) and cf.strip():
            functions.add(cf.strip().lower())
    return frozenset(functions)


def _extract_topic_tags(units: list[dict]) -> frozenset[str]:
    """
    Extract and flatten topic_tags from enriched unit dicts.

    Each unit may have topic_tags: list[str] or None.
    Returns lowercase stripped frozenset of all tags across all units.
    """
    tags: set[str] = set()
    for unit in units:
        if not isinstance(unit, dict):
            continue
        raw_tags = unit.get("topic_tags")
        if isinstance(raw_tags, list):
            for tag in raw_tags:
                if tag and isinstance(tag, str) and tag.strip():
                    tags.add(tag.strip().lower())
    return frozenset(tags)


def _extract_units_from_snapshot(snapshot: Any) -> list[dict]:
    """
    Extract the list of unit dicts from enrichment snapshot.

    Поддерживает два формата:

    Формат A — enrichment sidecar (legal_units_enrichment_v1.json):
    {
        "enrichments": [
            {
                "unit_id": "...",
                "base": {"clause_function": "...", ...},
                "effective": {"clause_function": "...", ...},
                "applied_fields": [...],
                ...
            }
        ]
    }

    Формат B — LegalUnitsSnapshot.to_dict():
    {"units": [...], ...}

    Формат C — bare list (legacy):
    [...]
    """
    if isinstance(snapshot, list):
        return [u for u in snapshot if isinstance(u, dict)]

    if not isinstance(snapshot, dict):
        return []

    # Формат A: enrichment sidecar — данные под ключом "enrichments"
    enrichments = snapshot.get("enrichments")
    if isinstance(enrichments, list) and enrichments:
        # Каждый элемент имеет вид:
        # {"unit_id": "...", "base": {...}, "effective": {...}, "applied_fields": [...]}
        # Нормализуем в плоский dict с clause_function из effective слоя.
        result: list[dict] = []
        for item in enrichments:
            if not isinstance(item, dict):
                continue
            unit_id = item.get("unit_id")
            if not unit_id:
                continue

            effective = item.get("effective") or {}
            base = item.get("base") or {}
            status = str(item.get("status") or "").strip()

            # Берём clause_function из effective (post-enrichment),
            # с fallback на base (pre-enrichment).
            clause_function = (
                effective.get("clause_function")
                or base.get("clause_function")
            )

            unit_type = (
                effective.get("unit_type")
                or base.get("unit_type")
            )

            # topic_tags: используем policy-approved effective слой.
            #
            # Было: topic_tags из llm_proposal (raw LLM suggestion, pre-policy).
            # Стало: topic_tags из effective (post-policy) для applied/no_change,
            #        из base (deterministic baseline) для skipped/failed.
            #
            # Это обеспечивает единый semantic source of truth:
            # тот же слой, что использует chunk_snapshot_reader.py.
            if status in ("applied", "no_change"):
                topic_tags = effective.get("topic_tags") or []
            else:
                topic_tags = base.get("topic_tags") or []

            result.append({
                "unit_id": unit_id,
                "clause_function": clause_function,
                "unit_type": unit_type,
                "topic_tags": topic_tags,
                "applied_fields": item.get("applied_fields") or [],
                "status": status,
            })
        return result

    # Формат B: LegalUnitsSnapshot.to_dict()
    units = snapshot.get("units")
    if isinstance(units, list):
        return [u for u in units if isinstance(u, dict)]

    return []


def load_enrichment_context_for_segment(
    *,
    document_id: str,
    segment: Any,
    artifact_store: ArtifactStore,
) -> SemanticEnrichmentContext:
    """
    Load SemanticEnrichmentContext for one ORM segment object.

    Args:
        document_id:    UUID string of the document.
        segment:        ORM DocumentSegment object (duck-typed).
        artifact_store: ArtifactStore instance for MinIO access.

    Returns:
        SemanticEnrichmentContext with enrichment_available=True if artifact
        was loaded successfully, or SemanticEnrichmentContext.unavailable()
        on any failure.

    Never raises.
    """
    segment_id = getattr(segment, "segment_id", None)
    segment_type = getattr(segment, "segment_type", None)
    segment_title = getattr(segment, "segment_title", None)
    is_primary = getattr(segment, "is_primary", None)

    # Read enrichment_ref from segment_meta
    segment_meta = getattr(segment, "segment_meta", None) or {}
    if not isinstance(segment_meta, dict):
        segment_meta = {}

    enrichment_ref = segment_meta.get("legal_units_enrichment_ref")

    if not enrichment_ref or not isinstance(enrichment_ref, str):
        logger.debug(
            "enrichment_loader: no legal_units_enrichment_ref for segment",
            extra={
                "document_id": document_id,
                "segment_id": segment_id,
            },
        )
        return SemanticEnrichmentContext.unavailable(
            document_id=document_id,
            segment_id=segment_id,
            segment_type=segment_type,
            segment_title=segment_title,
            is_primary_segment=is_primary,
        )

    # Load sidecar from MinIO
    try:
        snapshot = artifact_store.get_json(enrichment_ref)
    except Exception as exc:
        logger.warning(
            "enrichment_loader: failed to load enrichment sidecar",
            extra={
                "document_id": document_id,
                "segment_id": segment_id,
                "enrichment_ref": enrichment_ref,
                "error": str(exc),
            },
        )
        return SemanticEnrichmentContext.unavailable(
            document_id=document_id,
            segment_id=segment_id,
            segment_type=segment_type,
            segment_title=segment_title,
            is_primary_segment=is_primary,
        )

    units = _extract_units_from_snapshot(snapshot)
    clause_functions = _extract_clause_functions(units)
    topic_tags = _extract_topic_tags(units)

    logger.debug(
        "enrichment_loader: enrichment context loaded",
        extra={
            "document_id": document_id,
            "segment_id": segment_id,
            "segment_type": segment_type,
            "unit_count": len(units),
            "clause_functions": sorted(clause_functions),
            "topic_tags_count": len(topic_tags),
        },
    )

    return SemanticEnrichmentContext(
        document_id=document_id,
        segment_id=segment_id,
        segment_type=segment_type,
        segment_title=segment_title,
        is_primary_segment=is_primary,
        clause_functions=clause_functions,
        topic_tags=topic_tags,
        enrichment_available=True,
        raw_unit_count=len(units),
    )



# src/engine/content/_document_content_semantic.py

"""
Внутренние helper-функции для semantic layer сервиса содержимого документа.

Модуль содержит вспомогательную логику для загрузки legal units,
восстановления доменных объектов LegalUnit и сериализации результата
для evidence bundle.
"""

from __future__ import annotations

import uuid
from typing import Any

from storage.artifact_store import ArtifactStore


async def load_legal_units_from_segments(
    *,
    segments: list[Any],
    artifact_store: ArtifactStore,
    doc_id: uuid.UUID,
    primary_only: bool,
    logger: Any,
) -> list[dict[str, Any]]:
    """
    Загрузить legal units из segment snapshots.

    Phase 12.1.6: если для сегмента есть enrichment sidecar
    (segment_meta["legal_units_enrichment_ref"]), применяет
    project_enriched_units() и возвращает effective enriched dicts.

    Fallback: если sidecar отсутствует или projection падает —
    возвращает baseline units без изменений.

    Контракт не изменился: возвращает list[dict[str, Any]].
    """
    from anyio.to_thread import run_sync

    target_segments = (
        [segment for segment in segments if bool(segment.is_primary)]
        if primary_only
        else list(segments)
    )

    if not target_segments:
        logger.info(
            "DocumentContentService.get_legal_units: no target segments after filter",
            extra={
                "doc_id": str(doc_id),
                "primary_only": primary_only,
                "total_segments": len(segments),
            },
        )
        return []

    all_units: list[dict[str, Any]] = []

    for segment in target_segments:
        segment_meta = dict(segment.segment_meta or {})
        legal_units_ref = segment_meta.get("legal_units_ref")

        if not legal_units_ref:
            logger.debug(
                "DocumentContentService.get_legal_units: no legal_units_ref for segment",
                extra={
                    "doc_id": str(doc_id),
                    "segment_id": segment.segment_id,
                    "is_primary": bool(segment.is_primary),
                },
            )
            continue

        try:
            def _load(ref: str = legal_units_ref) -> dict[str, Any]:
                return artifact_store.get_json(ref)

            snapshot_dict = await run_sync(_load)

            if not isinstance(snapshot_dict, dict):
                logger.warning(
                    "DocumentContentService.get_legal_units: invalid snapshot format",
                    extra={
                        "doc_id": str(doc_id),
                        "segment_id": segment.segment_id,
                        "legal_units_ref": legal_units_ref,
                        "type": type(snapshot_dict).__name__,
                    },
                )
                continue

            units_raw = snapshot_dict.get("units") or []
            if not isinstance(units_raw, list):
                continue

            # ── Phase 12.1.6: apply enrichment projection ─────────────────
            # Если enrichment sidecar существует — применяем projection.
            # Результат: effective units с LLM-обогащёнными полями.
            # Если sidecar отсутствует или projection падает —
            # units_raw используется без изменений (baseline).
            enrichment_ref = segment_meta.get("legal_units_enrichment_ref")
            units_raw = await _apply_enrichment_if_available(
                units_raw=units_raw,
                snapshot_dict=snapshot_dict,
                enrichment_ref=enrichment_ref,
                artifact_store=artifact_store,
                doc_id=doc_id,
                segment_id=str(segment.segment_id),
                logger=logger,
            )

            for unit in units_raw:
                if not isinstance(unit, dict):
                    continue
                if not unit.get("unit_id"):
                    continue
                all_units.append(unit)

            logger.debug(
                "DocumentContentService.get_legal_units: loaded units from segment",
                extra={
                    "doc_id": str(doc_id),
                    "segment_id": segment.segment_id,
                    "units_count": len(units_raw),
                    "legal_units_ref": legal_units_ref,
                    "enrichment_applied": enrichment_ref is not None,
                },
            )

        except Exception as e:
            logger.warning(
                "DocumentContentService.get_legal_units: failed to load legal units for segment",
                extra={
                    "doc_id": str(doc_id),
                    "segment_id": segment.segment_id,
                    "legal_units_ref": legal_units_ref,
                    "error": str(e),
                },
            )
            continue

    all_units.sort(
        key=lambda unit: (
            int(unit.get("page_start") or 1),
            str(unit.get("unit_id") or ""),
        )
    )

    logger.info(
        "DocumentContentService.get_legal_units: loaded",
        extra={
            "doc_id": str(doc_id),
            "total_units": len(all_units),
            "primary_only": primary_only,
            "segments_checked": len(target_segments),
        },
    )

    return all_units


def build_profile_not_found_result(profile_id: str) -> dict[str, Any]:
    """
    Построить пустой bundle-ответ для случая, когда retrieval profile не найден.
    """
    return {
        "query_topic": profile_id,
        "primary_units_count": 0,
        "supporting_units_count": 0,
        "confidence": 0.0,
        "missing_topics": [],
        "primary_unit_ids": [],
        "supporting_unit_ids": [],
        "diagnostics": {"reason": "profile_not_found"},
        "units": [],
    }


def build_no_legal_units_result(
    *,
    query_topic: str,
    required_topics: list[str],
) -> dict[str, Any]:
    """
    Построить пустой bundle-ответ для случая отсутствия legal units.
    """
    return {
        "query_topic": query_topic,
        "primary_units_count": 0,
        "supporting_units_count": 0,
        "confidence": 0.0,
        "missing_topics": list(required_topics),
        "primary_unit_ids": [],
        "supporting_unit_ids": [],
        "diagnostics": {"reason": "no_legal_units"},
        "units": [],
    }


async def _apply_enrichment_if_available(
    *,
    units_raw: list[dict[str, Any]],
    snapshot_dict: dict[str, Any],
    enrichment_ref: str | None,
    artifact_store: ArtifactStore,
    doc_id: uuid.UUID,
    segment_id: str,
    logger: Any,
) -> list[dict[str, Any]]:
    """
    Загрузить enrichment sidecar и применить projection к baseline units.

    Принимает уже загруженный snapshot_dict (baseline) чтобы не
    перечитывать MinIO повторно.

    Возвращает effective units (enriched dicts) если projection успешна,
    иначе возвращает оригинальный units_raw без изменений.

    Failure-isolated: любая ошибка → fallback к baseline.
    """
    if not enrichment_ref:
        return units_raw

    from anyio.to_thread import run_sync

    try:
        # 1. Загружаем enrichment sidecar
        def _load_enrichment(ref: str = enrichment_ref) -> dict[str, Any]:
            return artifact_store.get_json(ref)

        enrichment_dict = await run_sync(_load_enrichment)

        if not isinstance(enrichment_dict, dict):
            logger.warning(
                "load_legal_units: enrichment sidecar invalid format, using baseline",
                extra={
                    "doc_id": str(doc_id),
                    "segment_id": segment_id,
                    "enrichment_ref": enrichment_ref,
                    "type": type(enrichment_dict).__name__,
                },
            )
            return units_raw

        # 2. Восстанавливаем LegalUnitsEnrichmentResult из dict
        from services.structure.semantic_enrichment._types import (
            LegalUnitsEnrichmentResult,
        )

        enrichment_result = LegalUnitsEnrichmentResult.from_dict(enrichment_dict)

        # Если нет applied enrichments — нет смысла в проекции
        applied_count = len(
            [e for e in enrichment_result.enrichments
             if e.status.value == "applied"]
        )
        if applied_count == 0:
            logger.debug(
                "load_legal_units: enrichment sidecar has no applied enrichments, using baseline",
                extra={
                    "doc_id": str(doc_id),
                    "segment_id": segment_id,
                    "total_enrichments": len(enrichment_result.enrichments),
                },
            )
            return units_raw

        # 3. Восстанавливаем LegalUnitsSnapshot из уже загруженного dict
        from services.structure.legal_unit_models import LegalUnitsSnapshot

        snapshot = LegalUnitsSnapshot.from_dict(snapshot_dict)

        # 4. Применяем projection
        from services.structure.semantic_enrichment.projection import (
            project_enriched_units,
        )

        effective_units = project_enriched_units(
            snapshot=snapshot,
            enrichment_result=enrichment_result,
        )

        # 5. Сериализуем обратно в dicts
        effective_dicts = [u.to_dict() for u in effective_units]

        logger.debug(
            "load_legal_units: enrichment projection applied",
            extra={
                "doc_id": str(doc_id),
                "segment_id": segment_id,
                "enrichment_ref": enrichment_ref,
                "baseline_count": len(units_raw),
                "effective_count": len(effective_dicts),
                "applied_count": applied_count,
            },
        )

        return effective_dicts

    except Exception as proj_exc:
        logger.warning(
            "load_legal_units: enrichment projection failed, using baseline units",
            extra={
                "doc_id": str(doc_id),
                "segment_id": segment_id,
                "enrichment_ref": enrichment_ref,
                "error": str(proj_exc),
            },
        )
        return units_raw


def restore_legal_units(
    *,
    units_raw: list[dict[str, Any]],
    doc_id: uuid.UUID,
    logger: Any,
) -> list[Any]:
    """
    Восстановить объекты LegalUnit из сериализованных dict-ов.
    """
    from services.structure.legal_unit_models import (
        CitabilityMetrics,
        ClauseFunction,
        LegalUnit,
        LegalUnitType,
        normalize_clause_function_label,
    )

    legal_units: list[Any] = []

    for raw in units_raw:
        try:
            unit_type_str = str(raw.get("unit_type") or "unknown").lower()
            try:
                unit_type = LegalUnitType(unit_type_str)
            except ValueError:
                unit_type = LegalUnitType.UNKNOWN

            clause_function = (
                normalize_clause_function_label(raw.get("clause_function"))
                or ClauseFunction.UNKNOWN
            )

            citability_raw = raw.get("citability") or {}
            citability = CitabilityMetrics(
                citability_score=float(citability_raw.get("citability_score") or 0.0),
                citability_band=str(citability_raw.get("citability_band") or "low"),
                has_own_text=bool(citability_raw.get("has_own_text", False)),
                has_subtree_text=bool(citability_raw.get("has_subtree_text", False)),
                is_heading_only=bool(citability_raw.get("is_heading_only", False)),
                recovered_via_best_effort=bool(
                    citability_raw.get("recovered_via_best_effort", False)
                ),
                parse_confidence=citability_raw.get("parse_confidence"),
            )

            unit = LegalUnit(
                unit_id=str(raw.get("unit_id") or ""),
                raw_uid=str(raw.get("raw_uid") or ""),
                scope=str(raw.get("scope") or ""),
                title=str(raw.get("title") or ""),
                level=int(raw.get("level") or 1),
                unit_type=unit_type,
                clause_function=clause_function,
                segment_id=str(raw.get("segment_id") or ""),
                segment_type=str(raw.get("segment_type") or "unknown"),
                page_start=int(raw.get("page_start") or 1),
                page_end=int(raw.get("page_end") or 1),
                own_text=raw.get("own_text") or None,
                subtree_text=raw.get("subtree_text") or None,
                own_element_ids=list(raw.get("own_element_ids") or []),
                topic_tags=list(raw.get("topic_tags") or []),
                cross_refs=[],
                citability=citability,
                node_kind=str(raw.get("node_kind") or "leaf"),
                semantic_node_type=raw.get("semantic_node_type") or None,
                recovered_via_best_effort=bool(raw.get("recovered_via_best_effort", False)),
                fallback_reason=raw.get("fallback_reason") or None,
                
                unit_class=str(raw.get("unit_class") or "generic_block"),
                exact_text=raw.get("exact_text") or None,
                retrieval_text=raw.get("retrieval_text") or None,
                context_prefix=raw.get("context_prefix") or None,
                context_strategy=raw.get("context_strategy") or None,
                parent_unit_id=raw.get("parent_unit_id"),
                children_unit_ids=list(raw.get("children_unit_ids") or []),
                path_ids=list(raw.get("path_ids") or []),
                source_element_ids=list(raw.get("source_element_ids") or []),
                heading_text=raw.get("heading_text") or None,
            )
            legal_units.append(unit)

        except Exception as unit_exc:
            logger.debug(
                "DocumentContentService.get_evidence_bundle: failed to restore unit",
                extra={
                    "doc_id": str(doc_id),
                    "unit_id": raw.get("unit_id"),
                    "error": str(unit_exc),
                },
            )
            continue

    return legal_units


def serialize_primary_units_for_bundle(
    primary_units: list[Any],
) -> list[dict[str, Any]]:
    """
    Сериализовать primary units для итогового bundle-ответа.
    """
    result: list[dict[str, Any]] = []

    for unit in primary_units:
        result.append(
            {
                "unit_id": unit.unit_id,
                "raw_uid": unit.raw_uid,
                "title": unit.title,
                "own_text": unit.own_text,
                "page_start": unit.page_start,
                "page_end": unit.page_end,
                "unit_type": unit.unit_type.value,
                "topic_tags": unit.topic_tags,
                "citability_band": unit.citability.citability_band,
            }
        )

    return result

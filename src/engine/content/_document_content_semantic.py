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
    Загрузить legal units из segment snapshots с сохранением текущего поведения.
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
    )

    legal_units: list[Any] = []

    for raw in units_raw:
        try:
            unit_type_str = str(raw.get("unit_type") or "unknown").lower()
            try:
                unit_type = LegalUnitType(unit_type_str)
            except ValueError:
                unit_type = LegalUnitType.UNKNOWN

            func_str = str(raw.get("clause_function") or "unknown").lower()
            try:
                clause_function = ClauseFunction(func_str)
            except ValueError:
                clause_function = ClauseFunction.UNKNOWN

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

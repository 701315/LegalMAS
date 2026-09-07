# src/services/dd_matrix_builder.py

"""
DD Matrix Builder.

Строит матричное представление результатов Run (DDMatrixResponseDTO) из:
- check_results (прямое чтение из БД)
- documents dict (метаданные документов)
- checks_by_id (CheckDefinition для metadata)

Архитектурный принцип:
  - Никакой зависимости от aggregator.py или AggregatedResults
  - Чтение напрямую из check_results + documents
  - Детерминированный порядок строк/столбцов

Структура ответа:
  - segment_documents: строки на уровне логического документа/сегмента (primary)
  - documents: legacy file-ориентированные строки (backward compatibility)
  - checks: реестр уникальных проверок (столбцы матрицы)
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from api.schemas.deal_review import (
    CheckMetaDTO,
    DDMatrixResponseDTO,
    DocumentMatrixRowDTO,
    ExtractedFieldDTO,
    MatrixCellDTO,
    SegmentMatrixRowDTO,
)
from engine.playbook.models import CheckDefinition


# ---------------------------------------------------------------------------
# Вспомогательные константы для приоритизации рисков
# ---------------------------------------------------------------------------

_RESULT_PRIORITY: dict[str, int] = {"fail": 3, "unclear": 2, "pass": 1}


def _select_best_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Выбрать наиболее важную строку для (segment, check):
    - сначала по result: fail > unclear > pass
    - затем по confidence (по убыванию)
    - severity больше не используется (убран из модели)
    """
    return max(
        rows,
        key=lambda r: (
            _RESULT_PRIORITY.get(r.get("result", "unclear"), 0),
            r.get("confidence", 0.0) or 0.0,
        ),
    )


def _sort_key(row: DocumentMatrixRowDTO | SegmentMatrixRowDTO) -> tuple[int, int, int]:
    """Сортировка строк по риску: critical fail первые, карантин последний."""
    critical_fails = sum(
        1 for c in row.results.values()
        if c.result == "fail" and c.severity == "critical"
    )
    all_fails = sum(1 for c in row.results.values() if c.result == "fail")
    quarantine_flag = 1 if row.status == "quarantine" else 0
    return (quarantine_flag, -critical_fails, -all_fails)


# ---------------------------------------------------------------------------
# Helpers — прямой подсчёт метрик
# ---------------------------------------------------------------------------


def _count_severity(check_results: list[dict[str, Any]]) -> dict[str, int]:
    """Подсчитать severity counts напрямую из check_results."""
    counts = {"critical": 0, "high": 0, "medium": 0, "pass": 0, "unclear": 0}
    for cr in check_results:
        result = cr.get("result", "unclear")
        severity = cr.get("severity", "medium")

        if result == "fail":
            if severity in counts:
                counts[severity] += 1
        elif result == "pass":
            counts["pass"] += 1
        else:
            counts["unclear"] += 1
    return counts


def _count_quality_metrics(
    check_results: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Подсчитать метрики качества анализа."""
    quarantine_count = sum(
        1 for doc in documents.values()
        if doc.get("status") == "quarantine"
    )

    degraded_docs = set()
    for cr in check_results:
        quality_flags = cr.get("quality_flags") or {}
        if isinstance(quality_flags, dict) and quality_flags.get("structure_degraded"):
            degraded_docs.add(cr.get("document_id", ""))

    fail_high_crit = [
        cr for cr in check_results
        if cr.get("result") == "fail" and cr.get("severity") in ("critical", "high")
    ]

    evidence_valid = sum(
        1 for cr in fail_high_crit
        if (cr.get("display_text") or cr.get("value_text") or "").strip()
    )

    evidence_validity_rate = (
        evidence_valid / len(fail_high_crit) if fail_high_crit else 1.0
    )

    return {
        "quarantine_count": quarantine_count,
        "degraded_count": len(degraded_docs),
        "evidence_validity_rate": evidence_validity_rate,
    }


# ---------------------------------------------------------------------------
# Публичный API
# ---------------------------------------------------------------------------


def build_dd_matrix(
    check_results: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
    checks_by_id: dict[str, CheckDefinition],
    deal_id: str,
    run_id: str,
    deal_name: str,
) -> DDMatrixResponseDTO:
    """
    Построить матричное представление результатов Run.

    Алгоритм:
    1. Реестр уникальных чеков: GLOBAL_PLAYBOOK первыми, затем DOCUMENT_TYPE.
    2. Два индекса extracted values: segment-aware и fallback (doc-level).
    3. Индекс результатов на уровне файла (для legacy file-rows).
    4. Segment-ориентированные строки (основной уровень).
    5. Legacy file-ориентированные строки (backward compatibility).
    6. Сортировка по риску.
    7. Сборка ответа.
    """

    # ------------------------------------------------------------------
    # Шаг 1. Реестр уникальных чеков (столбцы матрицы)
    # ------------------------------------------------------------------
    seen_checks: dict[str, dict[str, Any]] = {}

    # Проход 1: GLOBAL_PLAYBOOK — идут первыми
    for cr in check_results:
        origin = (cr.get("origin") or "").upper()
        if origin != "GLOBAL_PLAYBOOK":
            continue
        check_id = cr.get("check_id", "")
        if check_id not in seen_checks:
            seen_checks[check_id] = {
                "check_id": check_id,
                "check_name": cr.get("check_name", ""),
                "origin": "GLOBAL_PLAYBOOK",
                "severity": cr.get("severity", "medium"),
                "applicable_doc_types": None,
            }

    # Проход 2: DOCUMENT_TYPE / CONDITIONAL
    for cr in check_results:
        origin = (cr.get("origin") or "").upper()
        if origin == "GLOBAL_PLAYBOOK":
            continue
        check_id = cr.get("check_id", "")
        resolved_origin = "CONDITIONAL" if cr.get("conditional_check_triggered") else "DOCUMENT_TYPE"
        if check_id not in seen_checks:
            seen_checks[check_id] = {
                "check_id": check_id,
                "check_name": cr.get("check_name", ""),
                "origin": resolved_origin,
                "severity": cr.get("severity", "medium"),
                "applicable_doc_types": [],
            }
        applicable = seen_checks[check_id]["applicable_doc_types"]
        doc_type = cr.get("doc_type", "Generic")
        if applicable is not None and doc_type not in applicable:
            applicable.append(doc_type)

    checks_list: list[CheckMetaDTO] = []
    global_check_ids: list[str] = []
    doc_type_check_ids: dict[str, list[str]] = defaultdict(list)

    for idx, (check_id, meta) in enumerate(seen_checks.items()):
        checks_list.append(
            CheckMetaDTO(
                check_id=meta["check_id"],
                check_name=meta["check_name"],
                origin=meta["origin"],
                severity=meta["severity"],
                order_index=idx,
                applicable_doc_types=meta["applicable_doc_types"],
            )
        )
        if meta["origin"] == "GLOBAL_PLAYBOOK":
            global_check_ids.append(check_id)
        else:
            for doc_type in (meta["applicable_doc_types"] or []):
                if check_id not in doc_type_check_ids[doc_type]:
                    doc_type_check_ids[doc_type].append(check_id)

    # ------------------------------------------------------------------
    # Шаг 2. Индексы extracted values
    # ------------------------------------------------------------------
    sv_index_segment: dict[tuple[str, str, str], list[ExtractedFieldDTO]] = defaultdict(list)
    sv_index_fallback: dict[tuple[str, str], list[ExtractedFieldDTO]] = defaultdict(list)

    for cr in check_results:
        doc_id = cr.get("document_id", "")
        check_id = cr.get("check_id", "")
        segment_id = cr.get("segment_id") or ""
        structured_data = cr.get("structured_data") or {}

        for field_name, field_value in structured_data.items():
            # Нормализация значения
            if isinstance(field_value, dict) and "value" in field_value:
                raw_display_value = field_value.get("value")
            else:
                raw_display_value = field_value

            if raw_display_value is None or str(raw_display_value) in ("not_found", "not_defined", "None", ""):
                continue

            display_value = str(raw_display_value)

            # Infer format
            name_lower = field_name.lower()
            if any(x in name_lower for x in ("amount", "price", "sum", "cost")):
                field_format = "money"
            elif any(x in name_lower for x in ("date", "expiry", "term")):
                field_format = "date"
            elif any(x in name_lower for x in ("party", "parties", "entity")):
                field_format = "entity_name"
            else:
                field_format = "text"

            extracted_field = ExtractedFieldDTO(
                field_name=field_name,
                field_value=display_value,
                field_format=field_format,
            )
            sv_index_segment[(doc_id, segment_id, check_id)].append(extracted_field)
            sv_index_fallback[(doc_id, check_id)].append(extracted_field)

    # ------------------------------------------------------------------
    # Шаг 3. Индекс результатов на уровне файла (для legacy file-rows)
    # ------------------------------------------------------------------
    result_index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for cr in check_results:
        doc_id = cr.get("document_id", "")
        check_id = cr.get("check_id", "")
        result_index[(doc_id, check_id)].append(cr)

    # Порядок документов (стабильный, по первому появлению)
    doc_order: dict[str, None] = {}
    for cr in check_results:
        doc_order[cr.get("document_id", "")] = None

    # ------------------------------------------------------------------
    # Шаг 4. Segment-ориентированные строки
    # ------------------------------------------------------------------
    segment_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for cr in check_results:
        doc_id = cr.get("document_id", "")
        segment_id = cr.get("segment_id") or ""
        segment_groups[(doc_id, segment_id)].append(cr)

    segment_rows: list[SegmentMatrixRowDTO] = []

    for (doc_id, seg_id), rows_for_segment in segment_groups.items():
        doc_meta = documents.get(doc_id, {})
        r0 = rows_for_segment[0]

        by_check: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for cr in rows_for_segment:
            by_check[cr.get("check_id", "")].append(cr)

        segment_results: dict[str, MatrixCellDTO] = {}

        for check_id, rows_for_check in by_check.items():
            best = _select_best_row(rows_for_check)

            # Приоритет: segment-aware, затем fallback
            extracted = sv_index_segment.get((doc_id, seg_id, check_id))
            if extracted is None:
                extracted = sv_index_fallback.get((doc_id, check_id), [])

            segment_results[check_id] = MatrixCellDTO(
                result=best.get("result", "unclear"),
                severity=best.get("severity", "medium"),
                snippet=(best.get("display_text") or best.get("value_text") or "")[:300],
                page=best.get("page"),
                clause_uid=best.get("clause_uid", ""),
                extracted=extracted,
                confidence=best.get("confidence", 0.0) or 0.0,
                qc_status=best.get("qc_status", "pending"),
                qc_by=best.get("qc_by"),
                qc_comment=best.get("qc_comment"),
                qc_at=best.get("qc_at").isoformat() if best.get("qc_at") else None,
                conditional_check_triggered=best.get("conditional_check_triggered", False),
                trigger_name=best.get("trigger_name", ""),
                segment_id=best.get("segment_id") or None,
                segment_type=best.get("segment_type"),
                segment_title=best.get("segment_title"),
                segment_order=best.get("segment_order"),
                is_primary_segment=best.get("is_primary_segment"),
                chunk_id=best.get("chunk_id"),
                chunk_index=best.get("chunk_index"),
                display_text=best.get("display_text"),
                review_status=best.get("review_status"),
                review_message=best.get("review_message"),
                needs_manual_review=best.get("needs_manual_review", False),
                ui_mode=best.get("ui_mode"),
                output_locale=best.get("output_locale") or best.get("presentation_locale"),
                presentation_locale=best.get("presentation_locale"),
                presentation_content_version=best.get(
                    "presentation_content_version"
                ),
                presentation_source_locale=best.get(
                    "presentation_source_locale"
                ),
                presentation_status=best.get("presentation_status"),
                presentation_is_fallback=best.get(
                    "presentation_is_fallback",
                    True,
                ),
                canonical_check_name=best.get("canonical_check_name"),
                canonical_display_text=best.get(
                    "canonical_display_text"
                ),
                canonical_review_message=best.get(
                    "canonical_review_message"
                ),
            )

        segment_rows.append(
            SegmentMatrixRowDTO(
                document_id=doc_id,
                document_name=doc_meta.get("name", ""),
                doc_type=doc_meta.get("doc_type", "Generic"),
                folder_path=doc_meta.get("folder_path"),
                segment_id=seg_id or None,
                segment_type=r0.get("segment_type"),
                segment_title=r0.get("segment_title"),
                segment_order=r0.get("segment_order"),
                is_primary_segment=r0.get("is_primary_segment"),
                status=doc_meta.get("status", "completed"),
                classification_level=doc_meta.get("classification_level", ""),
                classification_confidence=float(doc_meta.get("classification_confidence", 0.0)),
                requires_manual_review=bool(doc_meta.get("classification_requires_review")),
                results=segment_results,
            )
        )

    # ------------------------------------------------------------------
    # Шаг 5. Legacy file-ориентированные строки (backward compatibility)
    # ------------------------------------------------------------------
    file_rows: list[DocumentMatrixRowDTO] = []

    for doc_id in doc_order:
        doc_meta = documents.get(doc_id, {})
        file_results: dict[str, MatrixCellDTO] = {}

        for check_id in seen_checks:
            export_rows = result_index.get((doc_id, check_id))
            if not export_rows:
                continue

            # Берём лучший результат для этого (doc, check)
            best = _select_best_row(export_rows)

            file_results[check_id] = MatrixCellDTO(
                result=best.get("result", "unclear"),
                severity=best.get("severity", "medium"),
                snippet=(best.get("display_text") or best.get("value_text") or "")[:300],
                page=best.get("page"),
                clause_uid=best.get("clause_uid", ""),
                extracted=sv_index_fallback.get((doc_id, check_id), []),
                confidence=best.get("confidence", 0.0) or 0.0,
                qc_status=best.get("qc_status", "pending"),
                qc_by=best.get("qc_by"),
                qc_comment=best.get("qc_comment"),
                qc_at=best.get("qc_at").isoformat() if best.get("qc_at") else None,
                conditional_check_triggered=best.get("conditional_check_triggered", False),
                trigger_name=best.get("trigger_name", ""),
                segment_id=None,
                segment_type=None,
                segment_title=None,
                segment_order=None,
                is_primary_segment=None,
                chunk_id=None,
                chunk_index=None,
                display_text=best.get("display_text"),
                review_status=best.get("review_status"),
                review_message=best.get("review_message"),
                needs_manual_review=best.get("needs_manual_review", False),
                ui_mode=best.get("ui_mode"),
                output_locale=best.get("output_locale") or best.get("presentation_locale"),
                presentation_locale=best.get("presentation_locale"),
                presentation_content_version=best.get(
                    "presentation_content_version"
                ),
                presentation_source_locale=best.get(
                    "presentation_source_locale"
                ),
                presentation_status=best.get("presentation_status"),
                presentation_is_fallback=best.get(
                    "presentation_is_fallback",
                    True,
                ),
                canonical_check_name=best.get("canonical_check_name"),
                canonical_display_text=best.get(
                    "canonical_display_text"
                ),
                canonical_review_message=best.get(
                    "canonical_review_message"
                ),
            )

        file_rows.append(
            DocumentMatrixRowDTO(
                document_id=doc_id,
                document_name=doc_meta.get("name", ""),
                doc_type=doc_meta.get("doc_type", "Generic"),
                folder_path=doc_meta.get("folder_path"),
                status=doc_meta.get("status", "completed"),
                classification_level=doc_meta.get("classification_level", ""),
                classification_confidence=float(doc_meta.get("classification_confidence", 0.0)),
                requires_manual_review=bool(doc_meta.get("classification_requires_review")),
                results=file_results,
            )
        )

    # ------------------------------------------------------------------
    # Шаг 6. Сортировка по риску
    # ------------------------------------------------------------------
    file_rows.sort(key=_sort_key)
    segment_rows.sort(key=_sort_key)

    # ------------------------------------------------------------------
    # Шаг 7. Финальная сборка
    # ------------------------------------------------------------------
    severity_counts = _count_severity(check_results)
    quality_metrics = _count_quality_metrics(check_results, documents)

    return DDMatrixResponseDTO(
        deal_id=deal_id,
        run_id=run_id,
        deal_name=deal_name,
        output_locale=(
            check_results[0].get("output_locale")
            or check_results[0].get("presentation_locale")
            if check_results
            else None
        ),
        presentation_locale=(
            check_results[0].get("presentation_locale")
            if check_results
            else None
        ),
        checks=checks_list,
        global_check_ids=global_check_ids,
        doc_type_check_ids=dict(doc_type_check_ids),
        documents=file_rows,
        segment_documents=segment_rows,
        total_documents=len(documents),
        total_checks=len(check_results),
        severity_counts=severity_counts,
        quarantine_count=quality_metrics["quarantine_count"],
        degraded_count=quality_metrics["degraded_count"],
        evidence_validity_rate=round(quality_metrics["evidence_validity_rate"], 3),
    )


    
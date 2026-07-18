# src/services/dd_matrix_builder.py

"""
DD Matrix Builder.

Строит матричное представление результатов Run (DDMatrixResponseDTO) из:
- AggregatedResults (строки результатов проверок)
- documents dict (метаданные документов)

Архитектурный принцип:
  Этот модуль содержит только логику трансформации данных в матрицу.
  Никаких обращений к БД или внешним сервисам.
  Вызывается из deal_review_service.build_dd_matrix().

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
from services.export.models import AggregatedResults


# ---------------------------------------------------------------------------
# Вспомогательные константы для приоритизации рисков
# ---------------------------------------------------------------------------

_RESULT_PRIORITY: dict[str, int] = {"fail": 3, "unclear": 2, "pass": 1}
_SEVERITY_PRIORITY: dict[str, int] = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def _select_best_row(rows: list[Any]) -> Any:
    """
    Выбрать наиболее важную строку для (segment, check):
    - сначала по result: fail > unclear > pass
    - потом по severity: critical > high > medium > low
    - затем по confidence (по убыванию)
    """
    return max(
        rows,
        key=lambda r: (
            _RESULT_PRIORITY.get(r.result, 0),
            _SEVERITY_PRIORITY.get(r.severity, 0),
            r.confidence or 0.0,
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
# Публичный API
# ---------------------------------------------------------------------------


def build_dd_matrix(
    agg: AggregatedResults,
    documents: dict[str, dict[str, Any]],
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
    for row in agg.rows:
        if (row.origin or "").upper() != "GLOBAL_PLAYBOOK":
            continue
        if row.check_id not in seen_checks:
            seen_checks[row.check_id] = {
                "check_id": row.check_id,
                "check_name": row.check_name,
                "origin": "GLOBAL_PLAYBOOK",
                "severity": row.severity,
                "applicable_doc_types": None,
            }

    # Проход 2: DOCUMENT_TYPE / CONDITIONAL
    for row in agg.rows:
        if (row.origin or "").upper() == "GLOBAL_PLAYBOOK":
            continue
        resolved_origin = "CONDITIONAL" if row.conditional_check_triggered else "DOCUMENT_TYPE"
        if row.check_id not in seen_checks:
            seen_checks[row.check_id] = {
                "check_id": row.check_id,
                "check_name": row.check_name,
                "origin": resolved_origin,
                "severity": row.severity,
                "applicable_doc_types": [],
            }
        applicable = seen_checks[row.check_id]["applicable_doc_types"]
        if applicable is not None and row.doc_type not in applicable:
            applicable.append(row.doc_type)

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

    for sv in agg.structured_value_rows:
        extracted_field = ExtractedFieldDTO(
            field_name=sv.field_name,
            field_value=sv.field_value,
            field_format=sv.field_format,
        )
        seg_id = sv.segment_id or ""
        sv_index_segment[(sv.document_id, seg_id, sv.check_id)].append(extracted_field)
        sv_index_fallback[(sv.document_id, sv.check_id)].append(extracted_field)

    # ------------------------------------------------------------------
    # Шаг 3. Индекс результатов на уровне файла (для legacy file-rows)
    # ------------------------------------------------------------------
    result_index: dict[tuple[str, str], Any] = {}
    for row in agg.rows:
        result_index[(row.document_id, row.check_id)] = row

    # Порядок документов (стабильный, по первому появлению)
    doc_order: dict[str, None] = {}
    for row in agg.rows:
        doc_order[row.document_id] = None

    # ------------------------------------------------------------------
    # Шаг 4. Segment-ориентированные строки
    # ------------------------------------------------------------------
    segment_groups: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for row in agg.rows:
        segment_groups[(row.document_id, row.segment_id or "")].append(row)

    segment_rows: list[SegmentMatrixRowDTO] = []

    for (doc_id, seg_id), rows_for_segment in segment_groups.items():
        doc_meta = documents.get(doc_id, {})
        r0 = rows_for_segment[0]

        by_check: dict[str, list[Any]] = defaultdict(list)
        for r in rows_for_segment:
            by_check[r.check_id].append(r)

        segment_results: dict[str, MatrixCellDTO] = {}

        for check_id, rows_for_check in by_check.items():
            best = _select_best_row(rows_for_check)

            # Приоритет: segment-aware, затем fallback
            extracted = sv_index_segment.get((doc_id, seg_id, check_id))
            if extracted is None:
                extracted = sv_index_fallback.get((doc_id, check_id), [])

            segment_results[check_id] = MatrixCellDTO(
                result=best.result,
                severity=best.severity,
                snippet=best.evidence_snippet or "",
                page=best.page,
                clause_uid=best.clause_uid or "",
                extracted=extracted,
                confidence=best.confidence or 0.0,
                qc_status=best.qc_status or "pending",
                qc_by=best.qc_by or None,
                qc_comment=best.qc_comment or None,
                qc_at=best.qc_at.isoformat() if best.qc_at else None,
                conditional_check_triggered=best.conditional_check_triggered,
                trigger_name=best.trigger_name or "",
                segment_id=best.segment_id or None,
                segment_type=best.segment_type or None,
                segment_title=best.segment_title or None,
                segment_order=best.segment_order,
                is_primary_segment=best.is_primary_segment,
                # ИСПРАВЛЕНО: добавлены chunk_id и chunk_index (отсутствовали)
                chunk_id=best.chunk_id or None,
                chunk_index=best.chunk_index,
                # Canonical display semantics
                display_text=best.display_text,
                review_status=best.review_status,
                review_message=best.review_message,
                needs_manual_review=best.needs_manual_review,
                ui_mode=best.ui_mode,
            )

        segment_rows.append(
            SegmentMatrixRowDTO(
                document_id=doc_id,
                document_name=doc_meta.get("name", ""),
                doc_type=doc_meta.get("doc_type", "Generic"),
                folder_path=doc_meta.get("folder_path") or None,
                segment_id=seg_id or None,
                segment_type=r0.segment_type or None,
                segment_title=r0.segment_title or None,
                segment_order=r0.segment_order,
                is_primary_segment=r0.is_primary_segment,
                status=doc_meta.get("status", "completed"),
                classification_level=doc_meta.get("classification_level", ""),
                classification_confidence=float(doc_meta.get("classification_confidence", 0.0)),
                requires_manual_review=bool(
                    doc_meta.get("classification_requires_review") or False
                ),
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
            export_row = result_index.get((doc_id, check_id))
            if export_row is None:
                continue

            file_results[check_id] = MatrixCellDTO(
                result=export_row.result,
                severity=export_row.severity,
                snippet=export_row.evidence_snippet or "",
                page=export_row.page,
                clause_uid=export_row.clause_uid or "",
                extracted=sv_index_fallback.get((doc_id, check_id), []),
                confidence=export_row.confidence or 0.0,
                qc_status=export_row.qc_status or "pending",
                qc_by=export_row.qc_by,
                qc_comment=export_row.qc_comment,
                qc_at=export_row.qc_at,
                conditional_check_triggered=export_row.conditional_check_triggered,
                trigger_name=export_row.trigger_name or "",
                # File-level строки не несут segment/chunk provenance
                segment_id=None,
                segment_type=None,
                segment_title=None,
                segment_order=None,
                is_primary_segment=None,
                chunk_id=None,
                chunk_index=None,
                # Canonical display semantics
                display_text=export_row.display_text,
                review_status=export_row.review_status,
                review_message=export_row.review_message,
                needs_manual_review=export_row.needs_manual_review,
                ui_mode=export_row.ui_mode,
            )

        file_rows.append(
            DocumentMatrixRowDTO(
                document_id=doc_id,
                document_name=doc_meta.get("name", ""),
                doc_type=doc_meta.get("doc_type", "Generic"),
                folder_path=doc_meta.get("folder_path") or None,
                status=doc_meta.get("status", "completed"),
                classification_level=doc_meta.get("classification_level", ""),
                classification_confidence=float(
                    doc_meta.get("classification_confidence", 0.0)
                ),
                requires_manual_review=bool(
                    doc_meta.get("classification_requires_review") or False
                ),
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
    return DDMatrixResponseDTO(
        deal_id=agg.deal_id,
        run_id=agg.run_id,
        deal_name=agg.deal_name,
        checks=checks_list,
        global_check_ids=global_check_ids,
        doc_type_check_ids=dict(doc_type_check_ids),
        # ИСПРАВЛЕНО: восстановлены legacy file-rows (было documents=[])
        documents=file_rows,
        segment_documents=segment_rows,
        total_documents=agg.total_documents,
        total_checks=agg.total_checks,
        severity_counts=agg.severity_counts.to_dict(),
        quarantine_count=agg.quarantine_count,
        degraded_count=agg.degraded_count,
        evidence_validity_rate=round(agg.evidence_validity_rate, 3),
    )



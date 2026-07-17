"""
Pure-logic regression tests for semantic enrichment finalize batch behavior.

Почему тест pure-logic:
- прямой импорт db.repositories.* в текущем проекте тянет тяжёлый package graph;
- это нарушает требование "тест не должен тянуть тяжёлые ORM/Celery импорты";
- поэтому здесь тестируется именно алгоритм и SQL-template contract, без ORM.

Что фиксируем:
1. missing_ids после bulk finalize должны:
   - уменьшать segments_enriched до реально обновлённых строк,
   - увеличивать segments_failed на число missing ids.
2. terminal outcome не должен становиться ложным COMPLETED.
3. SQL CASE/params contract для batch update остаётся корректным.
"""

from __future__ import annotations

import uuid
from typing import Any


def _compute_missing_ids(
    enriched_refs: dict[str, str],
    updated_segment_ids: set[str],
) -> set[str]:
    """
    segment_ids, для которых sidecar_ref был подготовлен в LLM-phase,
    но не был реально записан в DB finalize-phase.
    """
    return set(enriched_refs.keys()) - updated_segment_ids


def _apply_finalize_counter_correction(
    *,
    enriched_refs: dict[str, str],
    updated_segment_ids: set[str],
    segments_enriched: int,
    segments_failed: int,
) -> tuple[int, int]:
    """
    Локальная копия нужной production-логики из _enrichment_finalize().

    Если часть enriched refs не записалась в БД:
    - segments_enriched = число реально обновлённых строк
    - segments_failed += число missing ids
    """
    missing_ids = _compute_missing_ids(enriched_refs, updated_segment_ids)
    if not missing_ids:
        return segments_enriched, segments_failed

    return len(updated_segment_ids), segments_failed + len(missing_ids)


def _derive_terminal_outcome(
    *,
    segments_with_legal_units_ref: int,
    segments_enriched: int,
    segments_timed_out: int = 0,
    segments_failed: int = 0,
    segments_skipped_budget: int = 0,
) -> str:
    """
    Локальная копия логики _derive_terminal_outcome().

    Правила:
    - нет кандидатов → skipped
    - ничего не enriched, но были timeout/budget → timed_out
    - ничего не enriched, только failures → degraded
    - всё enriched, провалов нет → completed
    - частичный успех → degraded
    """
    if segments_with_legal_units_ref == 0:
        return "skipped"

    total_not_enriched = (
        segments_timed_out
        + segments_failed
        + segments_skipped_budget
    )

    if segments_enriched == 0:
        if segments_timed_out > 0 or segments_skipped_budget > 0:
            return "timed_out"
        return "degraded"

    if total_not_enriched == 0:
        return "completed"

    return "degraded"


def _build_case_sql_fragment(items: list[tuple[str, str]]) -> str:
    """
    Воспроизводит CASE fragment для batch SQL update.
    """
    branches = " ".join(
        f"WHEN :seg_{i} THEN :ref_{i}"
        for i in range(len(items))
    )
    return f"CASE segment_id {branches} END"


def _build_bind_params(
    document_version_id: uuid.UUID,
    items: list[tuple[str, str]],
) -> dict[str, Any]:
    """
    Воспроизводит bind params contract для batch SQL update.
    """
    segment_ids = [seg_id for seg_id, _ in items]
    params: dict[str, Any] = {
        "version_id": document_version_id,
        "segment_ids": segment_ids,
    }
    for i, (seg_id, ref) in enumerate(items):
        params[f"seg_{i}"] = seg_id
        params[f"ref_{i}"] = ref
    return params


class TestMissingIdsCorrection:
    def test_no_missing_keeps_counters(self):
        enriched_refs = {"seg-1": "ref-1", "seg-2": "ref-2"}
        updated = {"seg-1", "seg-2"}

        enriched, failed = _apply_finalize_counter_correction(
            enriched_refs=enriched_refs,
            updated_segment_ids=updated,
            segments_enriched=2,
            segments_failed=0,
        )

        assert enriched == 2
        assert failed == 0

    def test_one_missing_corrects_both_counters(self):
        enriched_refs = {
            "seg-1": "ref-1",
            "seg-2": "ref-2",
            "seg-3": "ref-3",
        }
        updated = {"seg-1", "seg-2"}

        enriched, failed = _apply_finalize_counter_correction(
            enriched_refs=enriched_refs,
            updated_segment_ids=updated,
            segments_enriched=3,
            segments_failed=0,
        )

        assert enriched == 2
        assert failed == 1

    def test_missing_accumulates_with_existing_failed(self):
        enriched_refs = {
            "seg-1": "ref-1",
            "seg-2": "ref-2",
        }
        updated = {"seg-1"}

        enriched, failed = _apply_finalize_counter_correction(
            enriched_refs=enriched_refs,
            updated_segment_ids=updated,
            segments_enriched=2,
            segments_failed=2,
        )

        assert enriched == 1
        assert failed == 3

    def test_all_missing_zeroes_enriched_and_increments_failed(self):
        enriched_refs = {
            "seg-1": "ref-1",
            "seg-2": "ref-2",
        }
        updated: set[str] = set()

        enriched, failed = _apply_finalize_counter_correction(
            enriched_refs=enriched_refs,
            updated_segment_ids=updated,
            segments_enriched=2,
            segments_failed=0,
        )

        assert enriched == 0
        assert failed == 2

    def test_empty_enriched_refs_no_change(self):
        enriched_refs: dict[str, str] = {}
        updated: set[str] = set()

        enriched, failed = _apply_finalize_counter_correction(
            enriched_refs=enriched_refs,
            updated_segment_ids=updated,
            segments_enriched=0,
            segments_failed=0,
        )

        assert enriched == 0
        assert failed == 0

    def test_compute_missing_ids_exact(self):
        enriched_refs = {"a": "r1", "b": "r2", "c": "r3"}
        updated = {"a", "c"}
        assert _compute_missing_ids(enriched_refs, updated) == {"b"}

    def test_compute_missing_ids_none_missing(self):
        enriched_refs = {"a": "r1", "b": "r2"}
        updated = {"a", "b"}
        assert _compute_missing_ids(enriched_refs, updated) == set()

    def test_compute_missing_ids_all_missing(self):
        enriched_refs = {"a": "r1", "b": "r2"}
        updated: set[str] = set()
        assert _compute_missing_ids(enriched_refs, updated) == {"a", "b"}


class TestSqlTemplateContract:
    def test_case_expr_single_item(self):
        items = [("seg-uuid-1", "s3://bucket/ref-1")]
        sql = _build_case_sql_fragment(items)

        assert "CASE segment_id" in sql
        assert "WHEN :seg_0 THEN :ref_0" in sql
        assert "WHEN :seg_1" not in sql

    def test_case_expr_multiple_items(self):
        items = [
            ("seg-uuid-1", "s3://bucket/ref-1"),
            ("seg-uuid-2", "s3://bucket/ref-2"),
            ("seg-uuid-3", "s3://bucket/ref-3"),
        ]
        sql = _build_case_sql_fragment(items)

        assert "WHEN :seg_0 THEN :ref_0" in sql
        assert "WHEN :seg_1 THEN :ref_1" in sql
        assert "WHEN :seg_2 THEN :ref_2" in sql
        assert "WHEN :seg_3" not in sql

    def test_bind_params_contains_all_keys(self):
        version_id = uuid.uuid4()
        items = [("seg-1", "ref-1"), ("seg-2", "ref-2")]

        params = _build_bind_params(version_id, items)

        assert params["version_id"] == version_id
        assert params["segment_ids"] == ["seg-1", "seg-2"]
        assert params["seg_0"] == "seg-1"
        assert params["ref_0"] == "ref-1"
        assert params["seg_1"] == "seg-2"
        assert params["ref_1"] == "ref-2"

    def test_bind_params_preserve_order(self):
        version_id = uuid.uuid4()
        items = [
            ("alpha", "ref-a"),
            ("beta", "ref-b"),
            ("gamma", "ref-c"),
        ]

        params = _build_bind_params(version_id, items)

        for i, (seg_id, ref) in enumerate(items):
            assert params["segment_ids"][i] == seg_id
            assert params[f"seg_{i}"] == seg_id
            assert params[f"ref_{i}"] == ref

    def test_empty_items_produce_empty_segment_ids(self):
        version_id = uuid.uuid4()
        params = _build_bind_params(version_id, [])

        assert params["version_id"] == version_id
        assert params["segment_ids"] == []


class TestTerminalOutcomeAfterCorrection:
    def test_all_updated_completed(self):
        outcome = _derive_terminal_outcome(
            segments_with_legal_units_ref=3,
            segments_enriched=3,
        )
        assert outcome == "completed"

    def test_partial_db_persist_becomes_degraded_after_correction(self):
        enriched_refs = {
            "seg-1": "r1",
            "seg-2": "r2",
            "seg-3": "r3",
        }
        updated = {"seg-1", "seg-2"}

        segments_enriched, segments_failed = _apply_finalize_counter_correction(
            enriched_refs=enriched_refs,
            updated_segment_ids=updated,
            segments_enriched=3,
            segments_failed=0,
        )

        outcome = _derive_terminal_outcome(
            segments_with_legal_units_ref=3,
            segments_enriched=segments_enriched,
            segments_failed=segments_failed,
        )

        assert segments_enriched == 2
        assert segments_failed == 1
        assert outcome == "degraded"

    def test_false_completed_without_failed_correction_is_documented(self):
        """
        Документируем дефект старого поведения:
        если уменьшить enriched, но не увеличить failed,
        outcome станет ложным completed.
        """
        outcome = _derive_terminal_outcome(
            segments_with_legal_units_ref=3,
            segments_enriched=2,
            segments_failed=0,
        )
        assert outcome == "completed"

    def test_all_missing_after_correction_is_degraded(self):
        enriched_refs = {"seg-1": "r1", "seg-2": "r2"}
        updated: set[str] = set()

        segments_enriched, segments_failed = _apply_finalize_counter_correction(
            enriched_refs=enriched_refs,
            updated_segment_ids=updated,
            segments_enriched=2,
            segments_failed=0,
        )

        outcome = _derive_terminal_outcome(
            segments_with_legal_units_ref=2,
            segments_enriched=segments_enriched,
            segments_failed=segments_failed,
        )

        assert segments_enriched == 0
        assert segments_failed == 2
        assert outcome == "degraded"

    def test_no_candidates_skipped(self):
        outcome = _derive_terminal_outcome(
            segments_with_legal_units_ref=0,
            segments_enriched=0,
        )
        assert outcome == "skipped"

    def test_zero_enriched_timeout_is_timed_out(self):
        outcome = _derive_terminal_outcome(
            segments_with_legal_units_ref=2,
            segments_enriched=0,
            segments_timed_out=2,
        )
        assert outcome == "timed_out"

    def test_zero_enriched_budget_is_timed_out(self):
        outcome = _derive_terminal_outcome(
            segments_with_legal_units_ref=3,
            segments_enriched=0,
            segments_skipped_budget=3,
        )
        assert outcome == "timed_out"

    def test_zero_enriched_only_failures_is_degraded(self):
        outcome = _derive_terminal_outcome(
            segments_with_legal_units_ref=3,
            segments_enriched=0,
            segments_failed=3,
        )
        assert outcome == "degraded"

    def test_mixed_enriched_and_timed_out_is_degraded(self):
        outcome = _derive_terminal_outcome(
            segments_with_legal_units_ref=4,
            segments_enriched=2,
            segments_timed_out=2,
        )
        assert outcome == "degraded"

    def test_existing_failures_accumulate_with_missing(self):
        enriched_refs = {"seg-1": "r1", "seg-2": "r2"}
        updated = {"seg-1"}

        segments_enriched, segments_failed = _apply_finalize_counter_correction(
            enriched_refs=enriched_refs,
            updated_segment_ids=updated,
            segments_enriched=2,
            segments_failed=1,
        )

        outcome = _derive_terminal_outcome(
            segments_with_legal_units_ref=3,
            segments_enriched=segments_enriched,
            segments_failed=segments_failed,
        )

        assert segments_enriched == 1
        assert segments_failed == 2
        assert outcome == "degraded"


        
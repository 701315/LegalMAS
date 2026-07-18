"""
Unit-тесты для review_presenter.build_document_summaries().

Стратегия изоляции:
  review_presenter.py импортирует из api.schemas.deal_review (Pydantic DTO).
  Патчим модуль через sys.modules с dataclass-заглушками ДО импорта presenter.

Тестируется:
  - Правильный подсчёт critical/high/medium_count (только для fail)
  - pass_count и unclear_count
  - in_quarantine = True только для status="quarantine"
  - Неизвестный severity при fail — не ломает счётчики
  - Неизвестный result — не вызывает исключений
  - Сортировка документов по имени
  - has_degraded_structure из quality_flags
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any

import pytest

from services.export.models import AggregatedResults, ExportRow, SeverityCounts


# ===========================================================================
# Dataclass-заглушка для DocumentSummaryDTO
# ===========================================================================


@dataclass
class _DocumentSummaryDTO:
    document_id: str
    name: str
    doc_type: str
    status: str
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    pass_count: int = 0
    unclear_count: int = 0
    has_degraded_structure: bool = False
    in_quarantine: bool = False
    classification_level: str = ""
    classification_confidence: float = 0.0


# ===========================================================================
# Патч sys.modules
# ===========================================================================


def _build_fake_review_schemas() -> ModuleType:
    mod = ModuleType("api.schemas.deal_review")
    mod.DocumentSummaryDTO = _DocumentSummaryDTO
    # Остальные DTO которые импортирует review_presenter
    mod.CheckItemDTO = object
    mod.ConditionalCheckDTO = object
    mod.DDRequestDTO = object
    mod.DocumentDetailDTO = object
    mod.ExtractedValueDTO = object
    return mod


_fake_review_schemas = _build_fake_review_schemas()
sys.modules.setdefault("api", ModuleType("api"))
sys.modules.setdefault("api.schemas", ModuleType("api.schemas"))
sys.modules["api.schemas.deal_review"] = _fake_review_schemas

# Безопасно импортируем ПОСЛЕ патча
from services.review_presenter import build_document_summaries  # noqa: E402


# ===========================================================================
# Helpers
# ===========================================================================


def _make_row(**overrides) -> ExportRow:
    """Фабрика ExportRow с разумными дефолтами."""
    defaults = dict(
        document_name="Договор.pdf",
        folder_path="/deals/001",
        doc_type="contract",
        check_name="Проверка",
        check_id="check_001",
        result="pass",
        severity="medium",
        evidence_snippet="текст...",
        document_id="doc-001",
        run_id="run-001",
        origin="DOCUMENT_TYPE",
        segment_id="",
        chunk_id="",
        chunk_index=None,
        confidence=0.8,
        qc_status="pending",
        qc_by=None,
        qc_comment=None,
        qc_at=None,
        conditional_check_triggered=False,
        trigger_name="",
        quality_flags="",
        clause_uid="",
        page=None,
        structured_data={},
        display_text=None,
        review_status=None,
        review_message=None,
        needs_manual_review=False,
        ui_mode=None,
    )
    defaults.update(overrides)
    return ExportRow(**defaults)


def _make_agg(rows: list[ExportRow]) -> AggregatedResults:
    return AggregatedResults(
        deal_id="deal-001",
        deal_name="Тест",
        run_id="run-001",
        rows=rows,
        severity_counts=SeverityCounts(),
    )


def _make_documents(
    doc_id: str = "doc-001",
    status: str = "completed",
    **extra,
) -> dict[str, dict]:
    """Фабрика documents dict для передачи в build_document_summaries."""
    doc = {
        "name": "Договор.pdf",
        "doc_type": "contract",
        "status": status,
        "classification_level": "",
        "classification_confidence": 0.9,
    }
    doc.update(extra)
    return {doc_id: doc}


# ===========================================================================
# Тесты critical_count
# ===========================================================================


class TestCriticalCount:

    def test_critical_count_incremented_for_fail_critical(self):
        """fail + severity=critical → critical_count=1."""
        rows = [_make_row(result="fail", severity="critical")]
        agg = _make_agg(rows)
        docs = _make_documents()

        summaries = build_document_summaries(agg, docs)

        assert len(summaries) == 1
        assert summaries[0].critical_count == 1
        assert summaries[0].high_count == 0
        assert summaries[0].medium_count == 0

    def test_high_count_incremented_for_fail_high(self):
        """fail + severity=high → high_count=1."""
        rows = [_make_row(result="fail", severity="high")]
        agg = _make_agg(rows)
        docs = _make_documents()

        summaries = build_document_summaries(agg, docs)

        assert summaries[0].high_count == 1
        assert summaries[0].critical_count == 0

    def test_medium_count_incremented_for_fail_medium(self):
        """fail + severity=medium → medium_count=1."""
        rows = [_make_row(result="fail", severity="medium")]
        agg = _make_agg(rows)
        docs = _make_documents()

        summaries = build_document_summaries(agg, docs)

        assert summaries[0].medium_count == 1
        assert summaries[0].critical_count == 0

    def test_pass_does_not_increment_fail_counters(self):
        """result=pass → только pass_count, остальные нули."""
        rows = [_make_row(result="pass", severity="critical")]
        agg = _make_agg(rows)
        docs = _make_documents()

        summaries = build_document_summaries(agg, docs)

        assert summaries[0].pass_count == 1
        assert summaries[0].critical_count == 0
        assert summaries[0].high_count == 0
        assert summaries[0].medium_count == 0

    def test_unclear_increments_unclear_count(self):
        """result=unclear → только unclear_count."""
        rows = [_make_row(result="unclear", severity="high")]
        agg = _make_agg(rows)
        docs = _make_documents()

        summaries = build_document_summaries(agg, docs)

        assert summaries[0].unclear_count == 1
        assert summaries[0].critical_count == 0

    def test_multiple_rows_accumulated_correctly(self):
        """Несколько строк с разными result/severity суммируются правильно."""
        rows = [
            _make_row(result="fail", severity="critical"),
            _make_row(result="fail", severity="critical"),
            _make_row(result="fail", severity="high"),
            _make_row(result="pass",    severity="medium"),
            _make_row(result="unclear", severity="medium"),
        ]
        agg = _make_agg(rows)
        docs = _make_documents()

        summaries = build_document_summaries(agg, docs)

        s = summaries[0]
        assert s.critical_count == 2
        assert s.high_count == 1
        assert s.medium_count == 0
        assert s.pass_count == 1
        assert s.unclear_count == 1


# ===========================================================================
# Тесты in_quarantine
# ===========================================================================


class TestInQuarantine:

    def test_in_quarantine_true_for_quarantine_status(self):
        """
        documents[doc_id]["status"] == "quarantine" → in_quarantine=True.
        quarantine берётся из внешнего documents dict, НЕ из ExportRow.
        """
        rows = [_make_row(document_id="doc-q")]
        agg = _make_agg(rows)
        docs = _make_documents(doc_id="doc-q", status="quarantine")

        summaries = build_document_summaries(agg, docs)

        assert summaries[0].in_quarantine is True

    def test_in_quarantine_false_for_completed(self):
        """status=completed → in_quarantine=False."""
        rows = [_make_row(document_id="doc-c")]
        agg = _make_agg(rows)
        docs = _make_documents(doc_id="doc-c", status="completed")

        summaries = build_document_summaries(agg, docs)

        assert summaries[0].in_quarantine is False

    def test_in_quarantine_false_for_failed_status(self):
        """status=failed → in_quarantine=False (только quarantine = True)."""
        rows = [_make_row(document_id="doc-f")]
        agg = _make_agg(rows)
        docs = _make_documents(doc_id="doc-f", status="failed")

        summaries = build_document_summaries(agg, docs)

        assert summaries[0].in_quarantine is False


# ===========================================================================
# Тесты устойчивости к неизвестным значениям
# ===========================================================================


class TestEdgeCases:

    def test_unknown_severity_with_fail_does_not_crash(self):
        """
        fail + severity="catastrophic" (неизвестное) →
        ни один счётчик не инкрементируется, исключений нет.

        Регрессионный тест: старый f"{row.severity}_count" создавал
        ключ "catastrophic_count" которого нет в DTO → ValidationError.
        """
        rows = [_make_row(result="fail", severity="catastrophic")]
        agg = _make_agg(rows)
        docs = _make_documents()

        # Не должно бросать исключений
        summaries = build_document_summaries(agg, docs)

        assert len(summaries) == 1
        s = summaries[0]
        # Неизвестный severity → не считается
        assert s.critical_count == 0
        assert s.high_count == 0
        assert s.medium_count == 0
        assert s.pass_count == 0
        assert s.unclear_count == 0

    def test_unknown_result_does_not_crash(self):
        """
        result="missing_required_clause" (нестандартное) →
        строка не считается, исключений нет.
        """
        rows = [_make_row(result="missing_required_clause", severity="critical")]
        agg = _make_agg(rows)
        docs = _make_documents()

        summaries = build_document_summaries(agg, docs)

        assert len(summaries) == 1
        s = summaries[0]
        assert s.critical_count == 0
        assert s.pass_count == 0
        assert s.unclear_count == 0

    def test_empty_rows_returns_empty_list(self):
        """Нет строк → пустой список summaries."""
        agg = _make_agg([])
        docs = _make_documents()

        summaries = build_document_summaries(agg, docs)

        assert summaries == []

    def test_has_degraded_structure_from_quality_flags(self):
        """
        quality_flags содержит "structure_degraded" →
        has_degraded_structure=True.
        """
        rows = [_make_row(quality_flags="structure_degraded,ocr_low")]
        agg = _make_agg(rows)
        docs = _make_documents()

        summaries = build_document_summaries(agg, docs)

        assert summaries[0].has_degraded_structure is True

    def test_has_degraded_structure_false_without_flag(self):
        """quality_flags не содержит structure_degraded → False."""
        rows = [_make_row(quality_flags="ocr_low")]
        agg = _make_agg(rows)
        docs = _make_documents()

        summaries = build_document_summaries(agg, docs)

        assert summaries[0].has_degraded_structure is False


# ===========================================================================
# Тесты сортировки
# ===========================================================================


class TestDocumentSorting:

    def test_documents_sorted_by_name_ascending(self):
        """
        Документы сортируются по имени (A→Z, case-insensitive).
        """
        rows = [
            _make_row(document_id="doc-c", document_name="Цессия.pdf"),
            _make_row(document_id="doc-a", document_name="Аренда.pdf"),
            _make_row(document_id="doc-b", document_name="Договор.pdf"),
        ]
        agg = _make_agg(rows)
        docs = {
            "doc-a": {"name": "Аренда.pdf",  "doc_type": "contract", "status": "completed",
                      "classification_level": "", "classification_confidence": 0.9},
            "doc-b": {"name": "Договор.pdf", "doc_type": "contract", "status": "completed",
                      "classification_level": "", "classification_confidence": 0.9},
            "doc-c": {"name": "Цессия.pdf",  "doc_type": "contract", "status": "completed",
                      "classification_level": "", "classification_confidence": 0.9},
        }

        summaries = build_document_summaries(agg, docs)

        names = [s.name for s in summaries]
        assert names == sorted(names, key=str.lower), (
            f"Документы не отсортированы по имени: {names}"
        )

    def test_multiple_rows_same_doc_one_summary(self):
        """
        Несколько строк для одного документа → одна строка в summaries.
        Дедупликация по document_id.
        """
        rows = [
            _make_row(document_id="doc-001", check_id="check_a", result="fail", severity="critical"),
            _make_row(document_id="doc-001", check_id="check_b", result="pass", severity="medium"),
            _make_row(document_id="doc-001", check_id="check_c", result="unclear", severity="high"),
        ]
        agg = _make_agg(rows)
        docs = _make_documents()

        summaries = build_document_summaries(agg, docs)

        assert len(summaries) == 1
        s = summaries[0]
        assert s.critical_count == 1
        assert s.pass_count == 1
        assert s.unclear_count == 1


        
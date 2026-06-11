# tests/unit/engine/checks/test_display_semantics_pipeline.py

"""
Pipeline integration tests for canonical display semantics (Target Contracts Spec v2).

Проверяет сквозной контур:
  ExportRow (aggregator) → MatrixCellDTO (deal_review_service) → ReviewFinding (selector)

Критерии готовности (из Spec v2):
  1. display_text заполнен для новых анализов с factual result.
  2. quality_flags не содержит canonical user_* semantics.
  3. evidence_snippet приоритизирует display_text над value_text.
  4. Segment rows получают только свои extracted values (segment-aware sv_index).
  5. Aggregator и build_dd_matrix не переформируют semantic text.
  6. MatrixCellDTO несёт display_text, review_status, review_message,
     needs_manual_review, ui_mode — thin projection без изменений.
  7. ReviewFinding несёт те же поля — thin projection из MatrixCellDTO.
"""

from __future__ import annotations

import pytest

from services.export.aggregator import aggregate_results
from services.export.models import (
    AggregatedResults,
    ExportRow,
    StructuredValueRow,
    SeverityCounts,
)
from services.deal_review_service import build_dd_matrix, build_document_detail
from api.schemas.deal_review import MatrixCellDTO


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_check_result(
    *,
    check_id: str = "glaw",
    check_name: str = "Governing Law",
    document_id: str = "doc1",
    result: str = "pass",
    severity: str = "medium",
    value_text: str = "machine_reason_code",
    display_text: str | None = "Применимое право: Российская Федерация",
    review_status: str | None = "ok",
    review_message: str | None = None,
    needs_manual_review: bool = False,
    ui_mode: str | None = "extraction",
    machine_reason_code: str | None = None,
    confidence: float = 0.9,
    structured_data: dict | None = None,
    quality_flags: dict | None = None,
    segment_id: str | None = None,
    origin: str = "GLOBAL_PLAYBOOK",
) -> dict:
    return {
        "check_id": check_id,
        "check_name": check_name,
        "document_id": document_id,
        "result": result,
        "severity": severity,
        "value_text": value_text,
        "display_text": display_text,
        "review_status": review_status,
        "review_message": review_message,
        "needs_manual_review": needs_manual_review,
        "ui_mode": ui_mode,
        "machine_reason_code": machine_reason_code,
        "confidence": confidence,
        "structured_data": structured_data or {},
        "quality_flags": quality_flags or {},
        "segment_id": segment_id,
        "segment_type": None,
        "segment_title": None,
        "segment_order": None,
        "is_primary_segment": None,
        "chunk_id": None,
        "chunk_index": None,
        "page": None,
        "clause_uid": "",
        "detector_used": "",
        "qc_status": "pending",
        "qc_by": None,
        "qc_comment": None,
        "qc_at": None,
        "conditional_check_triggered": False,
        "trigger_name": "",
        "origin": origin,
    }


def _make_doc(
    *,
    doc_id: str = "doc1",
    name: str = "Contract.pdf",
    doc_type: str = "Contract",
    status: str = "completed",
) -> dict[str, dict]:
    return {
        doc_id: {
            "name": name,
            "folder_path": "/",
            "doc_type": doc_type,
            "status": status,
            "classification_level": "",
            "classification_confidence": 0.0,
            "applicable_triggers": [],
            "classification_requires_review": False,
        }
    }


# ---------------------------------------------------------------------------
# Группа 1: aggregator — ExportRow canonical fields
# ---------------------------------------------------------------------------


class TestAggregatorExportRow:
    """ExportRow несёт canonical display semantics без переформирования."""

    def test_display_text_priority_over_value_text(self):
        """evidence_snippet берёт display_text, а не value_text."""
        cr = _make_check_result(
            value_text="machine_reason_code_xyz",
            display_text="Применимое право: РФ",
        )
        agg = aggregate_results("d1", "Deal", "r1", [cr], _make_doc())

        row = agg.rows[0]
        assert row.evidence_snippet == "Применимое право: РФ"

    def test_value_text_fallback_when_no_display_text(self):
        """evidence_snippet падает на value_text если display_text пустой."""
        cr = _make_check_result(
            value_text="Текст из value_text",
            display_text=None,
        )
        agg = aggregate_results("d1", "Deal", "r1", [cr], _make_doc())

        row = agg.rows[0]
        assert row.evidence_snippet == "Текст из value_text"

    def test_display_text_stored_in_export_row(self):
        """display_text сохраняется в ExportRow без изменений."""
        cr = _make_check_result(display_text="Factual result text")
        agg = aggregate_results("d1", "Deal", "r1", [cr], _make_doc())

        row = agg.rows[0]
        assert row.display_text == "Factual result text"

    def test_review_status_stored_in_export_row(self):
        cr = _make_check_result(review_status="ok")
        agg = aggregate_results("d1", "Deal", "r1", [cr], _make_doc())
        assert agg.rows[0].review_status == "ok"

    def test_review_message_stored_in_export_row(self):
        cr = _make_check_result(review_message="Рекомендуем проверить пункт 4.1")
        agg = aggregate_results("d1", "Deal", "r1", [cr], _make_doc())
        assert agg.rows[0].review_message == "Рекомендуем проверить пункт 4.1"

    def test_needs_manual_review_stored_in_export_row(self):
        cr = _make_check_result(needs_manual_review=True)
        agg = aggregate_results("d1", "Deal", "r1", [cr], _make_doc())
        assert agg.rows[0].needs_manual_review is True

    def test_needs_manual_review_false_by_default(self):
        cr = _make_check_result(needs_manual_review=False)
        agg = aggregate_results("d1", "Deal", "r1", [cr], _make_doc())
        assert agg.rows[0].needs_manual_review is False

    def test_ui_mode_stored_in_export_row(self):
        cr = _make_check_result(ui_mode="clause_presence")
        agg = aggregate_results("d1", "Deal", "r1", [cr], _make_doc())
        assert agg.rows[0].ui_mode == "clause_presence"

    def test_none_display_text_stored_as_none(self):
        cr = _make_check_result(display_text=None)
        agg = aggregate_results("d1", "Deal", "r1", [cr], _make_doc())
        assert agg.rows[0].display_text is None

    def test_quality_flags_no_legacy_ui_keys(self):
        """quality_flags не содержит canonical user_* semantics."""
        cr = _make_check_result(
            quality_flags={
                "low_confidence": True,
                # legacy keys — не должны попадать в ExportRow.quality_flags str
                "user_status": "fail",
                "user_message": "some message",
                "needs_manual_review": True,
            }
        )
        agg = aggregate_results("d1", "Deal", "r1", [cr], _make_doc())
        flags_str = agg.rows[0].quality_flags
        # quality_flags в ExportRow — это строка из ключей где value=True
        assert "user_status" not in flags_str
        assert "user_message" not in flags_str

    def test_aggregator_does_not_reformat_display_text(self):
        """Aggregator не переформирует display_text — передаёт as-is."""
        original = "Golden parachute: present (§12.3)"
        cr = _make_check_result(display_text=original)
        agg = aggregate_results("d1", "Deal", "r1", [cr], _make_doc())
        assert agg.rows[0].display_text == original

    def test_top_risk_evidence_snippet_uses_display_text(self):
        """TopRisk.evidence_snippet тоже получает display_text через ExportRow."""
        cr = _make_check_result(
            result="fail",
            severity="critical",
            display_text="Критическое нарушение: отсутствует §4.2",
            value_text="machine_fail_code",
        )
        agg = aggregate_results("d1", "Deal", "r1", [cr], _make_doc())

        assert len(agg.top_risks) == 1
        assert agg.top_risks[0].evidence_snippet == "Критическое нарушение: отсутствует §4.2"


# ---------------------------------------------------------------------------
# Группа 2: build_dd_matrix — MatrixCellDTO canonical fields
# ---------------------------------------------------------------------------


class TestBuildDdMatrixCellSemantics:
    """MatrixCellDTO несёт canonical display semantics — thin projection."""

    def _build_matrix(
        self, check_results: list[dict], docs: dict | None = None
    ):
        if docs is None:
            docs = _make_doc()
        agg = aggregate_results("d1", "Deal", "r1", check_results, docs)
        return build_dd_matrix(agg, docs)

    def test_display_text_in_matrix_cell(self):
        cr = _make_check_result(display_text="Применимое право: РФ")
        matrix = self._build_matrix([cr])

        seg = matrix.segment_documents[0]
        cell = seg.results["glaw"]
        assert cell.display_text == "Применимое право: РФ"

    def test_review_status_in_matrix_cell(self):
        cr = _make_check_result(review_status="ok")
        matrix = self._build_matrix([cr])

        cell = matrix.segment_documents[0].results["glaw"]
        assert cell.review_status == "ok"

    def test_review_message_in_matrix_cell(self):
        cr = _make_check_result(review_message="Проверьте актуальность")
        matrix = self._build_matrix([cr])

        cell = matrix.segment_documents[0].results["glaw"]
        assert cell.review_message == "Проверьте актуальность"

    def test_needs_manual_review_true_in_matrix_cell(self):
        cr = _make_check_result(needs_manual_review=True)
        matrix = self._build_matrix([cr])

        cell = matrix.segment_documents[0].results["glaw"]
        assert cell.needs_manual_review is True

    def test_needs_manual_review_false_in_matrix_cell(self):
        cr = _make_check_result(needs_manual_review=False)
        matrix = self._build_matrix([cr])

        cell = matrix.segment_documents[0].results["glaw"]
        assert cell.needs_manual_review is False

    def test_ui_mode_in_matrix_cell(self):
        cr = _make_check_result(ui_mode="risk_flag")
        matrix = self._build_matrix([cr])

        cell = matrix.segment_documents[0].results["glaw"]
        assert cell.ui_mode == "risk_flag"

    def test_none_display_text_in_matrix_cell(self):
        cr = _make_check_result(display_text=None)
        matrix = self._build_matrix([cr])

        cell = matrix.segment_documents[0].results["glaw"]
        assert cell.display_text is None

    def test_matrix_does_not_reformat_display_text(self):
        """build_dd_matrix не переформирует display_text."""
        original = "Оговорка об ответственности: обнаружена (стр. 7)"
        cr = _make_check_result(display_text=original)
        matrix = self._build_matrix([cr])

        cell = matrix.segment_documents[0].results["glaw"]
        assert cell.display_text == original

    def test_file_level_row_also_gets_display_text(self):
        """Legacy DocumentMatrixRowDTO тоже несёт display_text."""
        cr = _make_check_result(display_text="Factual text")
        matrix = self._build_matrix([cr])

        file_row = matrix.documents[0]
        cell = file_row.results.get("glaw")
        assert cell is not None
        assert cell.display_text == "Factual text"

    def test_select_best_row_prefers_fail_display_text(self):
        """select_best_row выбирает fail строку — её display_text и попадает в ячейку."""
        cr_pass = _make_check_result(
            result="pass", severity="medium",
            display_text="Норма соблюдена",
            segment_id="seg1",
        )
        cr_fail = _make_check_result(
            result="fail", severity="critical",
            display_text="Критическое нарушение §4",
            segment_id="seg1",
        )
        docs = _make_doc()
        matrix = self._build_matrix([cr_pass, cr_fail], docs)

        seg = next(s for s in matrix.segment_documents if s.segment_id == "seg1")
        cell = seg.results["glaw"]
        assert cell.result == "fail"
        assert cell.display_text == "Критическое нарушение §4"


# ---------------------------------------------------------------------------
# Группа 3: segment-aware sv_index
# ---------------------------------------------------------------------------


class TestSegmentAwareSvIndex:
    """Каждый сегмент получает только свои extracted values."""

    def _build_matrix_with_two_segments(self):
        cr1 = _make_check_result(
            check_id="amount",
            check_name="Contract Amount",
            segment_id="seg1",
            display_text="Сумма: 5 000 000 RUB",
            structured_data={"amount": "5000000"},
        )
        cr2 = _make_check_result(
            check_id="amount",
            check_name="Contract Amount",
            segment_id="seg2",
            display_text="Сумма: 2 000 000 RUB",
            structured_data={"amount": "2000000"},
        )
        docs = _make_doc()
        agg = aggregate_results("d1", "Deal", "r1", [cr1, cr2], docs)
        return build_dd_matrix(agg, docs)

    def test_seg1_gets_only_seg1_extracted(self):
        matrix = self._build_matrix_with_two_segments()
        seg1 = next(s for s in matrix.segment_documents if s.segment_id == "seg1")
        extracted = seg1.results["amount"].extracted
        assert len(extracted) == 1
        assert extracted[0].field_value == "5000000"

    def test_seg2_gets_only_seg2_extracted(self):
        matrix = self._build_matrix_with_two_segments()
        seg2 = next(s for s in matrix.segment_documents if s.segment_id == "seg2")
        extracted = seg2.results["amount"].extracted
        assert len(extracted) == 1
        assert extracted[0].field_value == "2000000"

    def test_seg1_display_text_is_seg1_specific(self):
        matrix = self._build_matrix_with_two_segments()
        seg1 = next(s for s in matrix.segment_documents if s.segment_id == "seg1")
        assert seg1.results["amount"].display_text == "Сумма: 5 000 000 RUB"

    def test_seg2_display_text_is_seg2_specific(self):
        matrix = self._build_matrix_with_two_segments()
        seg2 = next(s for s in matrix.segment_documents if s.segment_id == "seg2")
        assert seg2.results["amount"].display_text == "Сумма: 2 000 000 RUB"

    def test_no_cross_segment_contamination(self):
        """seg1 не содержит extracted values seg2 и наоборот."""
        matrix = self._build_matrix_with_two_segments()

        seg1 = next(s for s in matrix.segment_documents if s.segment_id == "seg1")
        seg2 = next(s for s in matrix.segment_documents if s.segment_id == "seg2")

        seg1_values = {e.field_value for e in seg1.results["amount"].extracted}
        seg2_values = {e.field_value for e in seg2.results["amount"].extracted}

        assert "2000000" not in seg1_values
        assert "5000000" not in seg2_values

    def test_two_segment_rows_created(self):
        matrix = self._build_matrix_with_two_segments()
        seg_ids = {s.segment_id for s in matrix.segment_documents}
        assert "seg1" in seg_ids
        assert "seg2" in seg_ids


# ---------------------------------------------------------------------------
# Группа 4: build_document_detail — CheckItemDTO canonical fields
# ---------------------------------------------------------------------------


class TestBuildDocumentDetailSemantics:
    """CheckItemDTO несёт canonical display semantics — thin projection."""

    def _build_detail(self, cr: dict, doc_id: str = "doc1"):
        docs = _make_doc(doc_id=doc_id)
        agg = aggregate_results("d1", "Deal", "r1", [cr], docs)
        return build_document_detail(agg, docs, doc_id)

    def test_display_text_in_check_item(self):
        cr = _make_check_result(display_text="Применимое право: РФ")
        detail = self._build_detail(cr)
        assert detail.checks[0].display_text == "Применимое право: РФ"

    def test_review_status_in_check_item(self):
        cr = _make_check_result(review_status="needs_review")
        detail = self._build_detail(cr)
        assert detail.checks[0].review_status == "needs_review"

    def test_review_message_in_check_item(self):
        cr = _make_check_result(review_message="Требуется проверка §4.2")
        detail = self._build_detail(cr)
        assert detail.checks[0].review_message == "Требуется проверка §4.2"

    def test_needs_manual_review_in_check_item(self):
        cr = _make_check_result(needs_manual_review=True)
        detail = self._build_detail(cr)
        assert detail.checks[0].needs_manual_review is True

    def test_ui_mode_in_check_item(self):
        cr = _make_check_result(ui_mode="extraction")
        detail = self._build_detail(cr)
        assert detail.checks[0].ui_mode == "extraction"

    def test_none_display_text_in_check_item(self):
        cr = _make_check_result(display_text=None)
        detail = self._build_detail(cr)
        assert detail.checks[0].display_text is None

    def test_detail_does_not_reformat_display_text(self):
        original = "Оговорка: обнаружена (§7.1, стр. 12)"
        cr = _make_check_result(display_text=original)
        detail = self._build_detail(cr)
        assert detail.checks[0].display_text == original


# ---------------------------------------------------------------------------
# Группа 5: multi-check / multi-doc сценарии
# ---------------------------------------------------------------------------


class TestMultiCheckMultiDoc:
    """Корректность при нескольких чеках и документах."""

    def test_each_check_gets_own_display_text(self):
        docs = {
            "doc1": {
                "name": "Contract.pdf", "folder_path": "/",
                "doc_type": "Contract", "status": "completed",
                "classification_level": "", "classification_confidence": 0.0,
                "applicable_triggers": [], "classification_requires_review": False,
            }
        }
        cr1 = _make_check_result(
            check_id="glaw", check_name="Governing Law",
            display_text="Применимое право: РФ", ui_mode="extraction",
        )
        cr2 = _make_check_result(
            check_id="termination", check_name="Termination Clause",
            display_text="Оговорка о расторжении: обнаружена",
            ui_mode="clause_presence",
        )
        agg = aggregate_results("d1", "Deal", "r1", [cr1, cr2], docs)
        matrix = build_dd_matrix(agg, docs)

        seg = matrix.segment_documents[0]
        assert seg.results["glaw"].display_text == "Применимое право: РФ"
        assert seg.results["termination"].display_text == "Оговорка о расторжении: обнаружена"

    def test_different_docs_get_independent_cells(self):
        docs = {
            "doc1": {
                "name": "Contract_A.pdf", "folder_path": "/",
                "doc_type": "Contract", "status": "completed",
                "classification_level": "", "classification_confidence": 0.0,
                "applicable_triggers": [], "classification_requires_review": False,
            },
            "doc2": {
                "name": "Contract_B.pdf", "folder_path": "/",
                "doc_type": "Contract", "status": "completed",
                "classification_level": "", "classification_confidence": 0.0,
                "applicable_triggers": [], "classification_requires_review": False,
            },
        }
        cr1 = _make_check_result(
            document_id="doc1", display_text="Право doc1: РФ",
        )
        cr2 = _make_check_result(
            document_id="doc2", display_text="Право doc2: Англия",
        )
        agg = aggregate_results("d1", "Deal", "r1", [cr1, cr2], docs)
        matrix = build_dd_matrix(agg, docs)

        seg_doc1 = next(s for s in matrix.segment_documents if s.document_id == "doc1")
        seg_doc2 = next(s for s in matrix.segment_documents if s.document_id == "doc2")

        assert seg_doc1.results["glaw"].display_text == "Право doc1: РФ"
        assert seg_doc2.results["glaw"].display_text == "Право doc2: Англия"

    def test_needs_manual_review_propagates_per_check(self):
        """needs_manual_review для одного чека не влияет на другой."""
        docs = _make_doc()
        cr1 = _make_check_result(
            check_id="glaw", needs_manual_review=True,
        )
        cr2 = _make_check_result(
            check_id="termination", needs_manual_review=False,
        )
        agg = aggregate_results("d1", "Deal", "r1", [cr1, cr2], docs)
        matrix = build_dd_matrix(agg, docs)

        seg = matrix.segment_documents[0]
        assert seg.results["glaw"].needs_manual_review is True
        assert seg.results["termination"].needs_manual_review is False


# ---------------------------------------------------------------------------
# Группа 6: граничные случаи
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Граничные и деградированные случаи."""

    def test_empty_display_text_string_treated_as_none_for_evidence(self):
        """Пустая строка display_text — fallback на value_text для evidence_snippet."""
        cr = _make_check_result(
            display_text="",
            value_text="Fallback text",
        )
        agg = aggregate_results("d1", "Deal", "r1", [cr], _make_doc())
        # display_text="" — falsy, поэтому берём value_text
        assert agg.rows[0].evidence_snippet == "Fallback text"

    def test_all_none_semantics_fields(self):
        """Все canonical поля None — система не падает."""
        cr = _make_check_result(
            display_text=None,
            review_status=None,
            review_message=None,
            needs_manual_review=False,
            ui_mode=None,
        )
        agg = aggregate_results("d1", "Deal", "r1", [cr], _make_doc())
        docs = _make_doc()
        matrix = build_dd_matrix(agg, docs)

        cell = matrix.segment_documents[0].results["glaw"]
        assert cell.display_text is None
        assert cell.review_status is None
        assert cell.review_message is None
        assert cell.needs_manual_review is False
        assert cell.ui_mode is None

    def test_no_check_results_returns_empty_matrix(self):
        docs = _make_doc()
        agg = aggregate_results("d1", "Deal", "r1", [], docs)
        matrix = build_dd_matrix(agg, docs)

        assert matrix.segment_documents == []
        assert matrix.documents == []

    def test_unsegmented_doc_gets_single_root_segment_row(self):
        """Документ без segment_id → одна строка с segment_id=None."""
        cr = _make_check_result(segment_id=None)
        docs = _make_doc()
        agg = aggregate_results("d1", "Deal", "r1", [cr], docs)
        matrix = build_dd_matrix(agg, docs)

        assert len(matrix.segment_documents) == 1
        assert matrix.segment_documents[0].segment_id is None

    def test_display_text_survives_full_pipeline(self):
        """
        End-to-end: check_result → aggregate → build_dd_matrix.
        display_text не теряется и не изменяется ни на одном слое.
        """
        original = "Применимое право: Российская Федерация (п. 15.1)"
        cr = _make_check_result(display_text=original)
        docs = _make_doc()

        agg = aggregate_results("d1", "Deal", "r1", [cr], docs)
        assert agg.rows[0].display_text == original

        matrix = build_dd_matrix(agg, docs)
        cell = matrix.segment_documents[0].results["glaw"]
        assert cell.display_text == original

        detail = build_document_detail(agg, docs, "doc1")
        assert detail.checks[0].display_text == original

    def test_review_status_needs_review_for_fail_critical(self):
        """fail + critical → review_status="needs_review" проходит сквозь pipeline."""
        cr = _make_check_result(
            result="fail",
            severity="critical",
            review_status="needs_review",
            needs_manual_review=True,
            display_text="Критическое нарушение: отсутствует оговорка",
        )
        docs = _make_doc()
        agg = aggregate_results("d1", "Deal", "r1", [cr], docs)
        matrix = build_dd_matrix(agg, docs)

        cell = matrix.segment_documents[0].results["glaw"]
        assert cell.review_status == "needs_review"
        assert cell.needs_manual_review is True
        assert cell.display_text == "Критическое нарушение: отсутствует оговорка"

    def test_pass_check_with_extraction_display_text(self):
        """pass + extraction ui_mode: display_text показывает factual value."""
        cr = _make_check_result(
            result="pass",
            severity="medium",
            review_status="ok",
            ui_mode="extraction",
            display_text="Дата подписания: 15.03.2024",
        )
        docs = _make_doc()
        agg = aggregate_results("d1", "Deal", "r1", [cr], docs)
        matrix = build_dd_matrix(agg, docs)

        cell = matrix.segment_documents[0].results["glaw"]
        assert cell.result == "pass"
        assert cell.display_text == "Дата подписания: 15.03.2024"
        assert cell.review_status == "ok"



        
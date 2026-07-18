"""
Unit-тесты для dd_matrix_builder.build_dd_matrix() и вспомогательных функций.

Стратегия изоляции от тяжёлых импортов:
  dd_matrix_builder.py импортирует из api.schemas.deal_review (Pydantic DTO).
  Мы патчим этот модуль через sys.modules ПЕРЕД импортом тестируемого кода,
  заменяя Pydantic-классы на простые dataclass-заглушки.
  Это позволяет тестировать чистую логику трансформации без FastAPI/SQLAlchemy.

Тестируется:
  - _select_best_row: приоритизация fail > unclear > pass, critical > high
  - _sort_key: quarantine последний, critical fails первые
  - build_dd_matrix: группировка по сегментам, file_rows, chunk_id в MatrixCellDTO
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any

import pytest

from services.export.models import AggregatedResults, ExportRow, SeverityCounts


# ===========================================================================
# Dataclass-заглушки вместо Pydantic DTO
# ===========================================================================
# Заглушки повторяют СИГНАТУРУ конструктора реальных DTO,
# но без Pydantic-валидации. Это позволяет тестировать логику
# маппинга без подъёма FastAPI.


@dataclass
class _MatrixCellDTO:
    result: str
    severity: str
    snippet: str = ""
    page: Any = None
    clause_uid: str = ""
    extracted: list = field(default_factory=list)
    confidence: float = 0.0
    qc_status: str = "pending"
    qc_by: Any = None
    qc_comment: Any = None
    qc_at: Any = None
    conditional_check_triggered: bool = False
    trigger_name: str = ""
    segment_id: Any = None
    segment_type: Any = None
    segment_title: Any = None
    segment_order: Any = None
    is_primary_segment: Any = None
    chunk_id: Any = None
    chunk_index: Any = None
    display_text: Any = None
    review_status: Any = None
    review_message: Any = None
    needs_manual_review: bool = False
    ui_mode: Any = None


@dataclass
class _CheckMetaDTO:
    check_id: str
    check_name: str
    origin: str
    severity: str
    order_index: int = 0
    applicable_doc_types: Any = None


@dataclass
class _DocumentMatrixRowDTO:
    document_id: str
    document_name: str
    doc_type: str
    folder_path: Any
    status: str = "completed"
    classification_level: str = ""
    classification_confidence: float = 0.0
    requires_manual_review: bool = False
    results: dict = field(default_factory=dict)


@dataclass
class _SegmentMatrixRowDTO:
    document_id: str
    document_name: str
    doc_type: str
    folder_path: Any
    segment_id: Any = None
    segment_type: Any = None
    segment_title: Any = None
    segment_order: Any = None
    is_primary_segment: Any = None
    status: str = "completed"
    classification_level: str = ""
    classification_confidence: float = 0.0
    requires_manual_review: bool = False
    results: dict = field(default_factory=dict)


@dataclass
class _ExtractedFieldDTO:
    field_name: str
    field_value: str
    field_format: str


@dataclass
class _DDMatrixResponseDTO:
    deal_id: str
    run_id: str
    deal_name: str
    checks: list = field(default_factory=list)
    global_check_ids: list = field(default_factory=list)
    doc_type_check_ids: dict = field(default_factory=dict)
    documents: list = field(default_factory=list)
    segment_documents: list = field(default_factory=list)
    total_documents: int = 0
    total_checks: int = 0
    severity_counts: Any = None
    quarantine_count: int = 0
    degraded_count: int = 0
    evidence_validity_rate: float = 1.0


# ===========================================================================
# Патч sys.modules — выполняется до импорта тестируемого модуля
# ===========================================================================

def _build_fake_schemas_module() -> ModuleType:
    """Создать фиктивный модуль api.schemas.deal_review с заглушками."""
    mod = ModuleType("api.schemas.deal_review")
    mod.MatrixCellDTO = _MatrixCellDTO
    mod.CheckMetaDTO = _CheckMetaDTO
    mod.DocumentMatrixRowDTO = _DocumentMatrixRowDTO
    mod.SegmentMatrixRowDTO = _SegmentMatrixRowDTO
    mod.ExtractedFieldDTO = _ExtractedFieldDTO
    mod.DDMatrixResponseDTO = _DDMatrixResponseDTO
    return mod


# Патчим ДО импорта dd_matrix_builder
_fake_schemas = _build_fake_schemas_module()
sys.modules.setdefault("api", ModuleType("api"))
sys.modules.setdefault("api.schemas", ModuleType("api.schemas"))
sys.modules["api.schemas.deal_review"] = _fake_schemas

# Теперь безопасно импортировать — получит заглушки, не Pydantic
from services.dd_matrix_builder import _select_best_row, _sort_key, build_dd_matrix  # noqa: E402


# ===========================================================================
# Fixtures
# ===========================================================================


def _make_export_row(**overrides) -> ExportRow:
    """
    Фабрика ExportRow с разумными дефолтами.
    Переопределяй только то что нужно для конкретного теста.
    """
    defaults = dict(
        document_name="Договор_001.pdf",
        folder_path="/deals/001",
        doc_type="contract",
        check_name="Проверка сторон",
        check_id="parties_check",
        result="pass",
        severity="medium",
        evidence_snippet="Стороны согласовали...",
        document_id="doc-001",
        run_id="run-001",
        origin="DOCUMENT_TYPE",
        segment_id="",
        segment_type="",
        segment_title="",
        segment_order=None,
        is_primary_segment=None,
        chunk_id="",
        chunk_index=None,
        confidence=0.8,
        qc_status="pending",
        qc_by=None,
        qc_comment=None,
        qc_at=None,
        conditional_check_triggered=False,
        trigger_name="",
        display_text=None,
        review_status=None,
        review_message=None,
        needs_manual_review=False,
        ui_mode=None,
        structured_data={},
        clause_uid="",
        page=None,
        quality_flags="",
    )
    defaults.update(overrides)
    return ExportRow(**defaults)


def _make_agg(rows: list[ExportRow], **overrides) -> AggregatedResults:
    """Фабрика AggregatedResults с минимальными полями."""
    defaults = dict(
        deal_id="deal-001",
        deal_name="Сделка Тест",
        run_id="run-001",
        rows=rows,
        severity_counts=SeverityCounts(),
        structured_value_rows=[],
        total_documents=1,
        total_checks=len(rows),
        quarantine_count=0,
        degraded_count=0,
        evidence_validity_rate=1.0,
    )
    defaults.update(overrides)
    return AggregatedResults(**defaults)


# ===========================================================================
# _select_best_row
# ===========================================================================


class TestSelectBestRow:
    """Тесты логики приоритизации строк внутри (segment, check) группы."""

    @dataclass
    class _Row:
        """Минимальная заглушка для _select_best_row (нужны только 3 поля)."""
        result: str
        severity: str
        confidence: float = 0.0

    def test_fail_beats_pass(self):
        rows = [
            self._Row("pass", "critical", 0.9),
            self._Row("fail", "medium", 0.5),
        ]
        best = _select_best_row(rows)
        assert best.result == "fail"

    def test_fail_beats_unclear(self):
        rows = [
            self._Row("unclear", "high", 0.8),
            self._Row("fail", "medium", 0.3),
        ]
        best = _select_best_row(rows)
        assert best.result == "fail"

    def test_unclear_beats_pass(self):
        rows = [
            self._Row("pass", "critical", 0.95),
            self._Row("unclear", "low", 0.1),
        ]
        best = _select_best_row(rows)
        assert best.result == "unclear"

    def test_critical_beats_high_when_both_fail(self):
        rows = [
            self._Row("fail", "high", 0.9),
            self._Row("fail", "critical", 0.5),
        ]
        best = _select_best_row(rows)
        assert best.severity == "critical"

    def test_high_beats_medium_when_both_fail(self):
        rows = [
            self._Row("fail", "medium", 0.9),
            self._Row("fail", "high", 0.3),
        ]
        best = _select_best_row(rows)
        assert best.severity == "high"

    def test_confidence_is_tiebreaker(self):
        """При одинаковом result+severity побеждает higher confidence."""
        rows = [
            self._Row("fail", "critical", confidence=0.6),
            self._Row("fail", "critical", confidence=0.9),
            self._Row("fail", "critical", confidence=0.3),
        ]
        best = _select_best_row(rows)
        assert best.confidence == pytest.approx(0.9)

    def test_single_row_returns_itself(self):
        row = self._Row("pass", "medium", 0.5)
        best = _select_best_row([row])
        assert best is row


# ===========================================================================
# _sort_key
# ===========================================================================


class TestSortKey:

    def test_quarantine_sorts_last(self):
        """quarantine строки должны идти ПОСЛЕ completed строк."""

        @dataclass
        class _FakeRow:
            status: str
            results: dict = field(default_factory=dict)

        completed = _FakeRow(status="completed", results={
            "c1": _MatrixCellDTO(result="fail", severity="critical"),
        })
        quarantine = _FakeRow(status="quarantine", results={})

        key_completed = _sort_key(completed)
        key_quarantine = _sort_key(quarantine)

        # Меньший ключ = выше в отсортированном списке
        assert key_completed < key_quarantine

    def test_more_critical_fails_sorts_first(self):
        """Больше critical fail → меньший ключ → выше в списке."""

        @dataclass
        class _FakeRow:
            status: str
            results: dict = field(default_factory=dict)

        one_critical = _FakeRow(status="completed", results={
            "c1": _MatrixCellDTO(result="fail", severity="critical"),
        })
        two_critical = _FakeRow(status="completed", results={
            "c1": _MatrixCellDTO(result="fail", severity="critical"),
            "c2": _MatrixCellDTO(result="fail", severity="critical"),
        })

        assert _sort_key(two_critical) < _sort_key(one_critical)


# ===========================================================================
# build_dd_matrix — интеграционные тесты логики
# ===========================================================================


class TestBuildDdMatrix:

    def test_groups_rows_by_segment(self):
        """
        Строки с разными segment_id → разные SegmentMatrixRow.
        Один документ, два сегмента → два segment_documents.
        """
        rows = [
            _make_export_row(
                document_id="doc-001",
                check_id="check_a",
                segment_id="seg-1",
                result="fail",
                severity="high",
            ),
            _make_export_row(
                document_id="doc-001",
                check_id="check_a",
                segment_id="seg-2",
                result="pass",
                severity="medium",
            ),
        ]
        agg = _make_agg(rows)
        documents = {
            "doc-001": {
                "name": "Договор.pdf",
                "doc_type": "contract",
                "folder_path": "/deals",
                "status": "completed",
                "classification_level": "",
                "classification_confidence": 0.9,
            }
        }

        result = build_dd_matrix(agg, documents)

        assert len(result.segment_documents) == 2
        seg_ids = {s.segment_id for s in result.segment_documents}
        assert "seg-1" in seg_ids
        assert "seg-2" in seg_ids

    def test_select_best_row_used_in_segment_grouping(self):
        """
        Для одного (segment, check) с несколькими строками
        выбирается лучшая: fail > pass.
        """
        rows = [
            _make_export_row(
                document_id="doc-001",
                check_id="check_a",
                segment_id="seg-1",
                result="pass",
                severity="medium",
            ),
            _make_export_row(
                document_id="doc-001",
                check_id="check_a",
                segment_id="seg-1",
                result="fail",
                severity="critical",
            ),
        ]
        agg = _make_agg(rows)
        documents = {
            "doc-001": {
                "name": "Договор.pdf",
                "doc_type": "contract",
                "folder_path": "/deals",
                "status": "completed",
                "classification_level": "",
                "classification_confidence": 0.9,
            }
        }

        result = build_dd_matrix(agg, documents)

        assert len(result.segment_documents) == 1
        seg_row = result.segment_documents[0]
        cell = seg_row.results["check_a"]
        assert cell.result == "fail"
        assert cell.severity == "critical"

    def test_file_rows_are_not_empty(self):
        """
        Legacy file_rows (documents) заполнены, не пустой список.
        Регрессионный тест: был баг где documents=[] (пустой список).
        """
        rows = [
            _make_export_row(
                document_id="doc-001",
                check_id="check_a",
                result="fail",
                severity="high",
            ),
        ]
        agg = _make_agg(rows)
        documents = {
            "doc-001": {
                "name": "Договор.pdf",
                "doc_type": "contract",
                "folder_path": "/deals",
                "status": "completed",
                "classification_level": "",
                "classification_confidence": 0.9,
            }
        }

        result = build_dd_matrix(agg, documents)

        assert len(result.documents) == 1, (
            f"Ожидался 1 legacy file-row, получено {len(result.documents)}"
        )
        assert result.documents[0].document_id == "doc-001"

    def test_chunk_id_and_chunk_index_present_in_matrix_cell(self):
        """
        chunk_id и chunk_index пробрасываются в MatrixCellDTO из ExportRow.
        Регрессионный тест: поля отсутствовали до исправления.
        """
        rows = [
            _make_export_row(
                document_id="doc-001",
                check_id="check_a",
                segment_id="seg-1",
                result="fail",
                severity="critical",
                chunk_id="chunk-abc-123",
                chunk_index=5,
            ),
        ]
        agg = _make_agg(rows)
        documents = {
            "doc-001": {
                "name": "Договор.pdf",
                "doc_type": "contract",
                "folder_path": "/deals",
                "status": "completed",
                "classification_level": "",
                "classification_confidence": 0.9,
            }
        }

        result = build_dd_matrix(agg, documents)

        assert len(result.segment_documents) == 1
        cell = result.segment_documents[0].results["check_a"]
        assert cell.chunk_id == "chunk-abc-123", (
            f"chunk_id должен быть 'chunk-abc-123', получено: {cell.chunk_id!r}"
        )
        assert cell.chunk_index == 5, (
            f"chunk_index должен быть 5, получено: {cell.chunk_index!r}"
        )

    def test_global_playbook_checks_registered_first(self):
        """
        GLOBAL_PLAYBOOK чеки идут перед DOCUMENT_TYPE в checks_list.
        Проверяем order_index.
        """
        rows = [
            _make_export_row(
                check_id="doc_check",
                origin="DOCUMENT_TYPE",
                result="pass",
                severity="medium",
            ),
            _make_export_row(
                check_id="global_check",
                origin="GLOBAL_PLAYBOOK",
                result="pass",
                severity="low",
            ),
        ]
        agg = _make_agg(rows)
        documents = {
            "doc-001": {
                "name": "Договор.pdf",
                "doc_type": "contract",
                "folder_path": "/deals",
                "status": "completed",
                "classification_level": "",
                "classification_confidence": 0.9,
            }
        }

        result = build_dd_matrix(agg, documents)

        global_check = next(c for c in result.checks if c.check_id == "global_check")
        doc_check = next(c for c in result.checks if c.check_id == "doc_check")

        assert global_check.order_index < doc_check.order_index

    def test_severity_counts_passed_through(self):
        """severity_counts из AggregatedResults передаётся в ответ."""
        counts = SeverityCounts(critical=2, high=1, medium=0, pass_count=5, unclear=1)
        rows = [_make_export_row()]
        agg = _make_agg(rows, severity_counts=counts)
        documents = {
            "doc-001": {
                "name": "Договор.pdf",
                "doc_type": "contract",
                "folder_path": "/deals",
                "status": "completed",
                "classification_level": "",
                "classification_confidence": 0.9,
            }
        }

        result = build_dd_matrix(agg, documents)

        # severity_counts передаётся как dict (to_dict())
        assert result.severity_counts["critical"] == 2
        assert result.severity_counts["high"] == 1


        
"""Unit tests для Span Splitter (Layer 6) и Table Semantics (Layer 7)."""

import pytest
from services.document_layout.schemas import CanonicalTable, CanonicalTableCell, TableTopologyType
from services.document_layout.span_splitter import SpanSplitter
from services.document_layout.table_semantics import TableSemanticsProcessor


class TestSpanSplitter:
    def test_splits_inline_backslash(self):
        splitter = SpanSplitter()
        res = splitter.split_span("Здание 1 \\ Building 1", target_language="ru")
        assert res.is_split_successful is True
        assert res.target_text == "Здание 1"
        assert res.split_method == "separator"

    def test_splits_script_boundary(self):
        splitter = SpanSplitter()
        res = splitter.split_span("REAL ESTATE AGREEMENT ДОГОВОР КУПЛИ-ПРОДАЖИ", target_language="ru")
        assert res.is_split_successful is True
        assert res.target_text == "ДОГОВОР КУПЛИ-ПРОДАЖИ"
        assert res.split_method == "script_boundary"


class TestTableSemantics:
    def test_detects_inline_cell_topology_and_filters_ru(self):
        table = CanonicalTable(
            table_id="table:0005",
            page=16,
            num_rows=2,
            num_cols=2,
            language="mixed",
            cells=[
                CanonicalTableCell(row=0, col=0, text="Объекты \\ Objects"),
                CanonicalTableCell(row=0, col=1, text="Стоимость \\ Price"),
                CanonicalTableCell(row=1, col=0, text="Здание 1 \\ Building 1"),
                CanonicalTableCell(row=1, col=1, text="500 000.00"),
            ],
            markdown="",
        )

        from services.document_layout.span_splitter import SpanSplitter
        splitter = SpanSplitter()
        processor = TableSemanticsProcessor(splitter=splitter)

        result = processor.process_table(table, target_language="ru")
        text = result.markdown_text
        topology = result.topology

        # Робастная проверка Enum без импорта класса TableTopology
        assert (
            getattr(topology, "name", None) == "INLINE_CELL"
            or getattr(topology, "value", None) == "inline_cell"
            or str(topology).endswith("INLINE_CELL")
            or str(topology) == "inline_cell"
        )
        assert "Объекты" in text
        assert "Objects" not in text
        assert "Здание 1" in text
        assert "Building 1" not in text
        assert "500 000.00" in text



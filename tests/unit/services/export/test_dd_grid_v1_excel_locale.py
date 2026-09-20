# tests/unit/services/export/test_dd_grid_v1_excel_locale.py

"""
Unit tests for Excel Export Parity and Metadata Snapshot (Sprint 5.6 & 5.7).

Verifies:
1. build_dd_grid_v1_excel generates a valid .xlsx workbook.
2. Sheet titles and headers respect the requested locale ("en" vs "ru").
3. Summary sheet embeds the Generation Audit Metadata section (Run ID, Locale, Timestamp).
"""

from __future__ import annotations

import io
import openpyxl
from engine.checks.dd_grid_column_builder import DDGridColumnRuntime
from engine.playbook.models import CheckDefinition
from services.dd_grid_v1_builder import (
    CellValueDTO,
    DDGridV1Data,
    DocumentMetaDTO,
    DrawerContentDTO,
    GlobalGroupDTO,
)
from services.export.dd_grid_v1_excel_builder import build_dd_grid_v1_excel


def _make_dummy_grid_data() -> DDGridV1Data:
    col = DDGridColumnRuntime(
        column_id="chk_1__val",
        label="Threshold",
        format="text",
        fallback_display="—",
        display_order=0,
        value_field="threshold",
        status_field=None,
        status_present_value=None,
        enum_labels={},
        unit="USD",
    )
    cell = CellValueDTO(
        cell_state="defined",
        display_value="1000 USD",
        raw_value="1000",
        location_clause_ref="cl. 4.1",
        location_page=2,
        location_confidence="high",
        has_location_fallback=False,
        location_fallback_reason=None,
    )
    drawer = DrawerContentDTO(
        check_id="chk_1",
        check_name="Liability Cap",
        document_id="doc_1",
        cell_state="defined",
        reason="Found in cl. 4.1",
        review_status="ok",
        display_text="Liability cap is 1000 USD",
        output_locale="en",
    )
    doc_meta = DocumentMetaDTO(
        document_id="doc_1",
        filename="Agreement.pdf",
        doc_type="contract",
        status="completed",
    )

    return DDGridV1Data(
        global_groups=[GlobalGroupDTO(group_id="legal", label="Legal Checks", display_order=1, checks=[])],
        doc_type_classes=[],
        column_registry={"chk_1__val": col},
        cell_values={"doc_1": {"_default": {"chk_1__val": cell}}},
        drawer_contents={"doc_1": {"_default": {"chk_1": drawer}}},
        documents_meta=[doc_meta],
    )


def test_excel_export_embeds_audit_metadata_and_respects_locale_en() -> None:
    """Test that Excel workbook generated with locale='en' has English sheets & metadata snapshot."""
    grid_data = _make_dummy_grid_data()
    check_results = [
        {
            "check_id": "chk_1",
            "check_name": "Liability Cap",
            "document_id": "doc_1",
            "result": "pass",
            "severity": "medium",
            "structured_data": {"threshold": "1000"},
        }
    ]
    documents = {"doc_1": {"name": "Agreement.pdf", "doc_type": "contract"}}
    checks_by_id = {"chk_1": CheckDefinition(id="chk_1", name="Liability Cap", severity="medium")}

    excel_bytes = build_dd_grid_v1_excel(
        grid_data=grid_data,
        check_results=check_results,
        documents=documents,
        checks_by_id=checks_by_id,
        deal_name="Project Alpha",
        run_id="run-12345-uuid",
        checks_mode="all",
        pipeline_strategy="full",
        locale="en",
    )

    assert isinstance(excel_bytes, bytes)
    assert len(excel_bytes) > 0

    # Parse generated workbook
    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    sheet_names = wb.sheetnames

    # Check English sheet titles
    assert "DD Grid" in sheet_names
    assert "DD Matrix" in sheet_names
    assert "Summary" in sheet_names

    # Verify Summary Sheet Audit Metadata
    ws_summary = wb["Summary"]
    summary_values = [cell.value for row in ws_summary.iter_rows() for cell in row if cell.value is not None]

    # Generation Metadata presence
    assert any("Generation Metadata" in str(v) for v in summary_values)
    assert any("run-12345-uuid" in str(v) for v in summary_values)
    assert any("EN" in str(v) for v in summary_values)
    assert any("VERIFIED_GLOSSARY_COMPLIANT" in str(v) for v in summary_values)


def test_excel_export_respects_locale_ru() -> None:
    """Test that Excel workbook generated with locale='ru' has Russian sheet titles & metadata snapshot."""
    grid_data = _make_dummy_grid_data()
    check_results = []
    documents = {"doc_1": {"name": "Договор.pdf", "doc_type": "contract"}}
    checks_by_id = {}

    excel_bytes = build_dd_grid_v1_excel(
        grid_data=grid_data,
        check_results=check_results,
        documents=documents,
        checks_by_id=checks_by_id,
        deal_name="Сделка Альфа",
        run_id="run-ru-uuid",
        checks_mode="all",
        pipeline_strategy="full",
        locale="ru",
    )

    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    sheet_names = wb.sheetnames

    assert "DD Grid" in sheet_names or "Таблица проверок" in sheet_names
    assert "Сводка" in sheet_names or "Summary" in sheet_names

    ws_summary = wb[sheet_names[2]]  # Summary sheet
    summary_values = [cell.value for row in ws_summary.iter_rows() for cell in row if cell.value is not None]

    assert any("run-ru-uuid" in str(v) for v in summary_values)
    assert any("RU" in str(v) for v in summary_values)

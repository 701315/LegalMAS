# src/services/export/requests_builder.py

"""
Standalone export builders for the "Requests" section.

Thin wrappers around the request-list builders already used by the
Summary (Excel) and Report (Word) exporters:

  - summary_builder._build_requests_sheet — writes a single "Request
    List" sheet into an openpyxl Workbook.
  - report_builder._build_dd_requests_for_report + _add_request_list —
    materialise a list[dict] of requests and render it as a Word
    appendix.

Both take a caller-owned Workbook / Document and the same
(check_results, documents, checks_by_id, locale) tuple as the rest of
the export pipeline, which makes them trivially reusable here.

Why a separate module:

  The existing summary/report exporters produce multi-section files
  (Overview + Top Risks + By Type + Request List + ...). The Request
  tab needs the same content but only the request section — a single
  sheet in XLSX and a single appendix in DOCX. Duplicating the request
  rendering logic would drift; extracting it into this module keeps a
  single source of truth.

This module performs no DB access, no locale resolution and no
presentation overlay. The caller is responsible for:
  - resolving the effective output locale;
  - running apply_presentations_for_read() on check_results;
  - providing documents and checks_by_id.
"""

from __future__ import annotations

import io
from typing import Any

from openpyxl import Workbook

from engine.playbook.models import CheckDefinition
from services.export.report_builder import (
    _add_request_list,
    _build_dd_requests_for_report,
)
from services.export.summary_builder import _build_requests_sheet

__all__ = ["build_requests_xlsx", "build_requests_docx"]


def build_requests_xlsx(
    check_results: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
    checks_by_id: dict[str, CheckDefinition],
    locale: str = "en",
) -> bytes:
    """
    Build a single-sheet XLSX containing the DD request list.

    Sheet title, headers and cell formats come from
    summary_builder._build_requests_sheet so the file is byte-for-byte
    consistent with the request section of the multi-sheet Deal Summary
    Excel export.
    """
    wb = Workbook()
    _build_requests_sheet(wb, check_results, documents, checks_by_id, locale=locale)

    # Remove the default empty "Sheet" if it is still present.
    # (_build_requests_sheet creates a new named sheet, so openpyxl's
    # default sheet is left orphaned at index 0.)
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.read()


def build_requests_docx(
    check_results: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
    checks_by_id: dict[str, CheckDefinition],
    locale: str = "en",
) -> bytes:
    """
    Build a DOCX containing only the request appendix.

    Reuses report_builder's request materialisation and rendering so
    the file matches Appendix A of the DD Report exactly.
    """
    # Local import to avoid a module-level cycle: report_builder is
    # already imported at the top for the helper functions, but
    # Document is only needed inside this function.
    from docx import Document

    dd_requests = _build_dd_requests_for_report(
        check_results, documents, checks_by_id, locale=locale,
    )

    doc = Document()
    _add_request_list(doc, dd_requests, locale=locale)

    output = io.BytesIO()
    doc.save(output)
    output.seek(0)
    return output.read()

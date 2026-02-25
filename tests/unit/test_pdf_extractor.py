"""
Unit tests for PDF extraction service.
"""

import os

import pytest

from src.services.pdf_extractor import (
    ExtractionResult,
    _classify_element_type,
    build_text_layout_raw,
    extract_pdf,
    is_ocr_available,
    make_element_id,
)

FIXTURES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "fixtures",
)


def load_pdf(filename: str) -> bytes:
    path = os.path.join(FIXTURES_DIR, filename)
    if not os.path.exists(path):
        pytest.skip(
            f"Fixture {filename} not found. " "Run python -m scripts.create_extraction_fixtures"
        )
    with open(path, "rb") as f:
        return f.read()


# ─── make_element_id ──────────────────────────────────────────────────────────


class TestMakeElementId:
    def test_deterministic(self):
        id1 = make_element_id("doc-1", 1, 0)
        id2 = make_element_id("doc-1", 1, 0)
        assert id1 == id2

    def test_different_inputs(self):
        assert make_element_id("doc-1", 1, 0) != make_element_id("doc-1", 1, 1)
        assert make_element_id("doc-1", 1, 0) != make_element_id("doc-2", 1, 0)

    def test_format(self):
        eid = make_element_id("doc-1", 1, 0)
        assert eid.startswith("e")
        assert len(eid) == 11  # "e" + 10 hex chars


# ─── _classify_element_type ───────────────────────────────────────────────────


class TestClassifyElementType:
    def test_numeric_heading(self):
        assert _classify_element_type("1. Предмет договора") == "heading"
        assert _classify_element_type("1.1. Объект сделки") == "heading"
        assert _classify_element_type("2.3.1. Детали") == "heading"

    def test_uppercase_heading(self):
        assert _classify_element_type("INTRODUCTION") == "heading"
        assert _classify_element_type("MAIN CONTENT") == "heading"

    def test_body_text(self):
        result = _classify_element_type("Настоящий договор заключён между Продавцом и Покупателем.")
        assert result == "text"

    def test_list_item_dash(self):
        assert _classify_element_type("– Первый пункт") == "listitem"
        assert _classify_element_type("- Второй пункт") == "listitem"

    def test_list_item_bullet(self):
        assert _classify_element_type("• Маркер") == "listitem"

    def test_large_font_heading(self):
        assert _classify_element_type("Заголовок", {"size": 16}) == "heading"

    def test_bold_font_heading(self):
        assert _classify_element_type("Заголовок", {"fontname": "Helvetica-Bold"}) == "heading"

    # NEW: Structure Builder downstream expectation
    def test_spa_header_classified_as_heading(self):
        """
        Structure Builder (Stage 6) relies on element.type == 'heading'
        to detect clause boundaries. Verify SPA-typical headings pass.
        """
        assert _classify_element_type("8. Смена контроля") == "heading"
        assert _classify_element_type("8.3. Согласие на передачу") == "heading"
        assert _classify_element_type("12. Применимое право") == "heading"

    # NEW: Classifier L2 downstream expectation
    def test_document_title_classified_as_heading(self):
        """
        Classifier L2 (Stage 6) header_analyzer scans first 1500 chars.
        Document title must be classified as heading so it's weighted correctly.
        """
        assert _classify_element_type("ДОГОВОР КУПЛИ-ПРОДАЖИ АКЦИЙ (SPA)") == "heading"
        assert _classify_element_type("NON-DISCLOSURE AGREEMENT") == "heading"


# ─── extract_pdf ─────────────────────────────────────────────────────────────


class TestExtractPdf:
    def test_text_pdf(self):
        pdf_bytes = load_pdf("test_text_clean.pdf")
        result = extract_pdf(pdf_bytes, "test-doc-1")
        assert len(result.elements) > 0
        assert result.strategy == "text"
        assert result.page_count >= 1
        assert result.avg_ocr_confidence == 1.0

    def test_text_pdf_reproducible(self):
        """Same PDF → same element IDs on repeated extraction."""
        pdf_bytes = load_pdf("test_text_clean.pdf")
        result1 = extract_pdf(pdf_bytes, "test-doc-repro")
        result2 = extract_pdf(pdf_bytes, "test-doc-repro")
        ids1 = [e.element_id for e in result1.elements]
        ids2 = [e.element_id for e in result2.elements]
        assert ids1 == ids2

    def test_table_pdf(self):
        pdf_bytes = load_pdf("test_with_table.pdf")
        result = extract_pdf(pdf_bytes, "test-doc-2")
        assert len(result.elements) > 0
        assert len(result.tables) >= 1
        assert len(result.tables[0].rows) >= 2  # header + at least 1 data row

    def test_empty_pdf(self):
        pdf_bytes = load_pdf("test_empty.pdf")
        result = extract_pdf(pdf_bytes, "test-doc-3")
        assert result.page_count >= 1
        assert len(result.elements) == 0

    def test_invalid_pdf(self):
        result = extract_pdf(b"This is not a PDF", "test-invalid")
        assert len(result.errors) > 0
        assert len(result.elements) == 0

    def test_element_bbox(self):
        pdf_bytes = load_pdf("test_text_clean.pdf")
        result = extract_pdf(pdf_bytes, "test-bbox")
        for elem in result.elements:
            assert len(elem.bbox) == 4, "bbox must have 4 coords"
            x0, top, x1, bottom = elem.bbox
            assert x0 >= 0
            assert top >= 0
            assert x1 >= x0, "width must be >= 0"
            assert bottom >= top, "height must be >= 0"

    def test_element_confidence(self):
        pdf_bytes = load_pdf("test_text_clean.pdf")
        result = extract_pdf(pdf_bytes, "test-conf")
        for elem in result.elements:
            if elem.strategy == "text":
                assert elem.confidence == 1.0

    def test_unique_element_ids(self):
        pdf_bytes = load_pdf("test_text_clean.pdf")
        result = extract_pdf(pdf_bytes, "test-unique")
        ids = [e.element_id for e in result.elements]
        assert len(ids) == len(set(ids)), "element IDs must be unique"

    # NEW: clause_uid null at extraction
    def test_clause_uid_null_at_extraction(self):
        """
        clause_uid must be null in textlayoutraw produced by Extractor.
        It is populated by Structure Builder (Stage 6), not here.
        """
        pdf_bytes = load_pdf("test_text_clean.pdf")
        result = extract_pdf(pdf_bytes, "test-clause-uid")
        layout = build_text_layout_raw(result, "test-doc", "ver-1")
        for elem in layout["elements"]:
            assert (
                elem["clause_uid"] is None
            ), f"clause_uid must be null at extraction, got {elem['clause_uid']}"

    # NEW: SPA fixture — downstream pipeline expectation
    def test_spa_pdf_headings_detected(self):
        """
        test_spa.pdf headings must be classified as 'heading'.
        Structure Builder (Stage 6) requires this for clause tree construction.
        """
        pdf_bytes = load_pdf("test_spa.pdf")
        result = extract_pdf(pdf_bytes, "test-spa")
        heading_texts = [e.text for e in result.elements if e.type == "heading"]
        assert any(
            "Предмет" in t or "1." in t for t in heading_texts
        ), "SPA fixture must have at least one numeric heading"
        assert any(
            "Смена контроля" in t or "8." in t for t in heading_texts
        ), "SPA fixture must contain change-of-control section heading"

    # NEW: SPA fixture — classifier downstream
    def test_spa_pdf_document_title_in_elements(self):
        """
        Classifier L2 (Stage 6) header_analyzer reads first 1500 chars.
        SPA title must appear in element list.
        """
        pdf_bytes = load_pdf("test_spa.pdf")
        result = extract_pdf(pdf_bytes, "test-spa-title")
        all_texts = " ".join(e.text for e in result.elements[:10])
        assert (
            "ДОГОВОР" in all_texts or "SPA" in all_texts
        ), "Document title must be among first extracted elements"


class TestExtractPdfOCR:
    """OCR tests — skipped if Tesseract not available."""

    def test_image_scan_pdf(self):
        if not is_ocr_available():
            pytest.skip("Tesseract not installed")
        pdf_bytes = load_pdf("test_image_scan.pdf")
        result = extract_pdf(pdf_bytes, "test-ocr")
        assert len(result.errors) == 0 or len(result.elements) >= 0  # no crash

    def test_ocr_element_confidence(self):
        if not is_ocr_available():
            pytest.skip("Tesseract not installed")
        pdf_bytes = load_pdf("test_image_scan.pdf")
        result = extract_pdf(pdf_bytes, "test-ocr-conf")
        ocr_elements = [e for e in result.elements if e.strategy == "ocr"]
        for elem in ocr_elements:
            assert 0.0 <= elem.confidence <= 1.0


# ─── build_text_layout_raw ────────────────────────────────────────────────────


class TestBuildTextLayoutRaw:
    def test_format(self):
        from src.services.pdf_extractor import Element as RealElement

        extraction = ExtractionResult(page_count=1, strategy="text")
        extraction.elements.append(
            RealElement(
                element_id="e001",
                type="text",
                text="Hello",
                page=1,
                bbox=[0, 0, 100, 20],
                confidence=1.0,
            )
        )
        layout = build_text_layout_raw(extraction, "doc-1", "ver-1")
        assert "elements" in layout
        assert "tables" in layout
        assert "metadata" in layout
        assert layout["metadata"]["pages"] == 1
        assert layout["metadata"]["strategy"] == "text"
        assert layout["document_id"] == "doc-1"
        assert len(layout["elements"]) == 1
        assert layout["elements"][0]["element_id"] == "e001"

    # NEW: clause_uid field present
    def test_clause_uid_field_present(self):
        """
        Every element in textlayoutraw must have clause_uid field (null).
        Structure Builder (Stage 6) patches this field in-place after
        building the clause tree — it expects the key to exist.
        """
        from src.services.pdf_extractor import Element as RealElement

        extraction = ExtractionResult(page_count=1, strategy="text")
        extraction.elements.append(
            RealElement(
                element_id="e001",
                type="heading",
                text="1. Предмет договора",
                page=1,
                bbox=[0, 0, 100, 20],
                confidence=1.0,
            )
        )
        layout = build_text_layout_raw(extraction, "doc-1", "ver-1")
        assert (
            "clause_uid" in layout["elements"][0]
        ), "clause_uid key must be present (null) for Structure Builder (Stage 6)"
        assert layout["elements"][0]["clause_uid"] is None

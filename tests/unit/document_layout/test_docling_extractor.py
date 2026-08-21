"""Unit tests для Docling Extractor (Phase 1)."""

from unittest.mock import MagicMock
import pytest
from services.document_layout.docling_extractor import (
    DoclingExtractor,
    _convert_bbox_to_fitz,
    _extract_marker,
)


class TestBboxConversion:
    def test_docling_to_fitz_bbox_conversion(self):
        """Проверяет корректность переворота оси Y (bottom-left -> top-left)."""
        mock_bbox = MagicMock()
        mock_bbox.l = 50.0
        mock_bbox.r = 200.0
        mock_bbox.b = 700.0
        mock_bbox.t = 720.0

        page_height = 800.0
        fitz_bbox = _convert_bbox_to_fitz(mock_bbox, page_height)

        assert fitz_bbox is not None
        x0, y0_top, x1, y1_top = fitz_bbox
        assert x0 == 50.0
        assert x1 == 200.0
        assert y0_top == 80.0
        assert y1_top == 100.0
        assert y0_top < y1_top

    def test_null_bbox_returns_none(self):
        assert _convert_bbox_to_fitz(None, 800.0) is None


class TestMarkerExtraction:
    def test_numeric_marker(self):
        marker, is_marker_only = _extract_marker("1.1.2 Текст пункта договора")
        assert marker == "1.1.2"
        assert is_marker_only is False

    def test_marker_only(self):
        marker, is_marker_only = _extract_marker("3.2")
        assert marker == "3.2"
        assert is_marker_only is True

    def test_bullet_marker(self):
        marker, is_marker_only = _extract_marker("• Пункт списка")
        assert marker == "•"
        assert is_marker_only is False

    def test_no_marker(self):
        marker, is_marker_only = _extract_marker("Обычный абзац текста без маркера.")
        assert marker is None
        assert is_marker_only is False


class TestDoclingExtractorExtraction:
    def test_extractor_with_mocked_document(self):
        mock_converter = MagicMock()
        mock_doc = MagicMock()

        mock_page = MagicMock()
        mock_page.size.width = 600.0
        mock_page.size.height = 800.0
        mock_doc.pages = {1: mock_page}

        mock_text = MagicMock()
        mock_text.text = "1. Предмет Договора"
        mock_text.label.value = "section_header"
        mock_prov = MagicMock()
        mock_prov.page_no = 1
        mock_prov.bbox.l = 50.0
        mock_prov.bbox.r = 250.0
        mock_prov.bbox.b = 750.0
        mock_prov.bbox.t = 770.0
        mock_text.prov = [mock_prov]

        mock_doc.texts = [mock_text]
        mock_doc.tables = []

        mock_converter.convert.return_value.document = mock_doc

        extractor = DoclingExtractor(converter=mock_converter)
        atoms, tables, pages, sha256 = extractor.extract(
            pdf_bytes=b"%PDF-mock",
            document_id="00000000-0000-0000-0000-000000000001",
            document_version_id="00000000-0000-0000-0000-000000000002",
        )

        assert len(atoms) == 1
        assert atoms[0].element_id == "atom:000000"
        assert atoms[0].text == "1. Предмет Договора"
        assert atoms[0].marker == "1."
        assert atoms[0].label == "section_header"
        assert atoms[0].page == 1
        assert atoms[0].bbox == (50.0, 30.0, 250.0, 50.0)

        assert len(pages) == 1
        assert len(pages[0].atoms) == 1
        assert len(tables) == 0
        assert len(sha256) == 64

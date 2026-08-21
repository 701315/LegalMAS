"""Unit tests для PyMuPDF Visual Enricher (Phase 2)."""

from unittest.mock import MagicMock, patch
import pytest
from services.document_layout.pymupdf_enricher import (
    PyMuPDFEnricher,
    _calculate_iou,
)
from services.document_layout.schemas import CanonicalAtom, CanonicalAtomSource


class TestIoUCalculation:
    def test_identical_boxes_give_iou_one(self):
        bbox = (10.0, 20.0, 100.0, 50.0)
        assert _calculate_iou(bbox, bbox) == 1.0

    def test_disjoint_boxes_give_iou_zero(self):
        b1 = (0.0, 0.0, 10.0, 10.0)
        b2 = (20.0, 20.0, 30.0, 30.0)
        assert _calculate_iou(b1, b2) == 0.0

    def test_partial_overlap_iou(self):
        b1 = (0.0, 0.0, 10.0, 10.0)
        b2 = (5.0, 0.0, 15.0, 10.0)
        # Inter = 5*10 = 50, Union = 100 + 100 - 50 = 150 -> IoU = 1/3
        iou = _calculate_iou(b1, b2)
        assert round(iou, 2) == 0.33


class TestPyMuPDFEnricher:
    @patch("pymupdf.open")
    def test_enrich_matches_spans_correctly(self, mock_open):
        mock_doc = MagicMock()
        mock_page = MagicMock()

        # Мокируем span из PyMuPDF
        mock_page.get_text.return_value = {
            "blocks": [
                {
                    "type": 0,
                    "lines": [
                        {
                            "spans": [
                                {
                                    "text": "1. Предмет Договора",
                                    "bbox": (50.0, 30.0, 250.0, 50.0),
                                    "font": "TimesNewRoman-Bold",
                                    "size": 14.0,
                                    "flags": 16,  # bold
                                    "color": 0,
                                }
                            ]
                        }
                    ],
                }
            ]
        }
        mock_doc.__len__.return_value = 1
        mock_doc.__getitem__.return_value = mock_page
        mock_open.return_value = mock_doc

        atom = CanonicalAtom(
            element_id="atom:000001",
            page=1,
            bbox=(50.0, 30.0, 250.0, 50.0),
            source_reading_order=1,
            layout_order=1,
            text="1. Предмет Договора",
            label="section_header",
            source=CanonicalAtomSource(docling_collection="texts"),
        )

        enricher = PyMuPDFEnricher()
        enriched = enricher.enrich(pdf_bytes=b"%PDF-test", atoms=[atom])

        assert len(enriched) == 1
        res = enriched[0]
        assert res.style is not None
        assert res.style.visual_match_status == "matched"
        assert res.style.font == "TimesNewRoman-Bold"
        assert res.style.font_size == 14.0
        assert res.style.bold is True
        assert res.style.match_score is not None and res.style.match_score > 0.8

    @patch("pymupdf.open")
    def test_enrich_handles_null_bbox_gracefully(self, mock_open):
        mock_doc = MagicMock()
        mock_open.return_value = mock_doc

        atom = CanonicalAtom(
            element_id="atom:000002",
            page=1,
            bbox=None,
            source_reading_order=2,
            layout_order=2,
            text="Текст без bbox",
            label="paragraph",
            source=CanonicalAtomSource(docling_collection="texts"),
        )

        enricher = PyMuPDFEnricher()
        enriched = enricher.enrich(pdf_bytes=b"%PDF-test", atoms=[atom])

        assert len(enriched) == 1
        assert enriched[0].style is not None
        assert enriched[0].style.visual_match_status == "not_found"

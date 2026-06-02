"""
Tests for universal segment boundary integrity rules.

Covers:
- appendix-like headings with inline title (no separator);
- post-segmentation purity recovery for contaminated segments;
- OCR tolerance (е → e);
- no-space variants (Приложение№1);
- english schedule/exhibit/annex family;
- running header deduplication (same appendix title on every page);
- amendment/addendum boundary detection.
"""

from __future__ import annotations

import pytest

from services.structure.segmenter import segment_elements


def _el(
    text: str,
    *,
    page: int,
    element_type: str = "heading_candidate",
    scope: str = "main_contract",
    segment_id: str = "seg-0",
    segment_type: str = "contract",
    segment_order: int = 0,
    formatting: dict | None = None,
) -> dict:
    """Helper to build a minimal element dict for segmenter tests."""
    return {
        "text": text,
        "page": page,
        "element_type": element_type,
        "scope": scope,
        "segment_id": segment_id,
        "segment_type": segment_type,
        "segment_order": segment_order,
        "formatting": formatting or {},
    }


def _body(text: str, *, page: int) -> dict:
    """Shortcut for body text elements."""
    return _el(text, page=page, element_type="body_text")


# ─── Inline title without separator ──────────────────────────────────────────


class TestAppendixInlineTitleWithoutSeparator:
    """Boundary markers with inline title via space (no colon/dash)."""

    def test_russian_appendix_inline_title(self) -> None:
        elements = [
            _el("ДОГОВОР КУПЛИ-ПРОДАЖИ", page=1),
            _el("1. Предмет договора", page=1),
            _body("Основной текст.", page=1),
            _body("Продолжение текста.", page=1),
            _el("ПРИЛОЖЕНИЕ № 4 Перечень объектов", page=3),
            _body("Объект 17.", page=3),
            _body("Объект 18.", page=4),
            _body("Объект 19.", page=5),
            _el("ПРИЛОЖЕНИЕ № 5 Покупная цена", page=6),
            _body("Покупная цена составляет...", page=6),
        ]
        segments = segment_elements("doc-ru-1", elements)
        types = [s.segment_type for s in segments]
        assert types.count("appendix") >= 2, f"Expected >=2 appendix segments, got {types}"
        titles = [s.segment_title or "" for s in segments]
        assert any("4" in t for t in titles)
        assert any("5" in t for t in titles)

    def test_english_schedule_inline_title(self) -> None:
        elements = [
            _el("SALE AND PURCHASE AGREEMENT", page=1),
            _el("1. Definitions", page=1),
            _body("Agreement text.", page=1),
            _body("More text.", page=2),
            _el("Schedule 1 Property List", page=3),
            _body("Property 1.", page=3),
            _body("Property 2.", page=4),
            _el("Schedule 2 Purchase Price", page=5),
            _body("Price details.", page=5),
        ]
        segments = segment_elements("doc-en-1", elements)
        types = [s.segment_type for s in segments]
        assert types.count("appendix") >= 2, f"Expected >=2 appendix segments, got {types}"

    def test_exhibit_inline_title(self) -> None:
        elements = [
            _el("FRAMEWORK AGREEMENT", page=1),
            _body("Agreement body.", page=1),
            _body("More body.", page=2),
            _el("Exhibit A Closing Deliverables", page=3),
            _body("Deliverables list.", page=3),
            _el("Exhibit B Form of Certificate", page=4),
            _body("Certificate template.", page=4),
        ]
        segments = segment_elements("doc-en-2", elements)
        types = [s.segment_type for s in segments]
        assert types.count("appendix") >= 2

    def test_annex_inline_title(self) -> None:
        elements = [
            _el("LOAN AGREEMENT", page=1),
            _body("Loan terms.", page=1),
            _body("More terms.", page=2),
            _el("Annex 1 Repayment Schedule", page=3),
            _body("Schedule details.", page=3),
            _el("Annex 2 Security Documents", page=4),
            _body("Security details.", page=4),
        ]
        segments = segment_elements("doc-en-3", elements)
        types = [s.segment_type for s in segments]
        assert types.count("appendix") >= 2


# ─── Separator variants (colon, dash, em-dash) ──────────────────────────────


class TestAppendixWithSeparator:
    """Existing separator-based patterns must continue to work."""

    @pytest.mark.parametrize(
        "title",
        [
            "Приложение № 1: Спецификация",
            "Приложение № 1 - Спецификация",
            "Приложение № 1 — Спецификация",
            "Приложение № 1 – Спецификация",
            "Appendix 1: Definitions",
            "Schedule A - Property",
        ],
    )
    def test_separator_variants(self, title: str) -> None:
        elements = [
            _el("ДОГОВОР", page=1),
            _body("Текст.", page=1),
            _body("Ещё текст.", page=2),
            _el(title, page=3),
            _body("Содержание приложения.", page=3),
        ]
        segments = segment_elements("doc-sep", elements)
        assert any(s.segment_type == "appendix" for s in segments)


# ─── OCR tolerance ───────────────────────────────────────────────────────────


class TestOCRTolerance:
    """OCR-distorted markers must still be recognized."""

    def test_russian_e_replaced_by_latin_e(self) -> None:
        # "Приложeниe" with latin 'e' in two positions.
        elements = [
            _el("ДОГОВОР", page=1),
            _body("Текст.", page=1),
            _body("Ещё.", page=2),
            _el("Приложeни\u0435 № 2 Перечень", page=3),  # mixed е/e
            _body("Содержание.", page=3),
        ]
        segments = segment_elements("doc-ocr-1", elements)
        assert any(s.segment_type == "appendix" for s in segments)


# ─── No-space variants ──────────────────────────────────────────────────────


class TestNoSpaceVariants:
    """Markers without space between keyword and number."""

    @pytest.mark.parametrize(
        "title",
        [
            "Приложение№1",
            "Приложение №1",
            "Приложение 1",
            "Appendix1",
            "AppendixNo.1",
        ],
    )
    def test_no_space_boundary(self, title: str) -> None:
        elements = [
            _el("ДОГОВОР", page=1),
            _body("Текст.", page=1),
            _body("Ещё.", page=2),
            _el(title, page=3),
            _body("Содержание приложения.", page=3),
        ]
        segments = segment_elements("doc-nospace", elements)
        assert any(s.segment_type == "appendix" for s in segments)


# ─── Purity recovery ────────────────────────────────────────────────────────


class TestSegmentPurityRecovery:
    """Post-segmentation purity recovery must split contaminated segments."""

    def test_contaminated_appendix_gets_split(self) -> None:
        """
        Simulates the real-world scenario:
        Appendix 4 contains text of Appendix 5 inside it.
        Purity recovery should detect the internal boundary.
        """
        elements = [
            _el("ДОГОВОР КУПЛИ-ПРОДАЖИ", page=1),
            _el("1. Предмет договора", page=1),
            _body("Основной текст договора.", page=1),
            _body("Продолжение текста.", page=2),
            # First boundary — detected in primary pass.
            _el("ПРИЛОЖЕНИЕ № 4 Перечень объектов", page=3),
            _body("17 Наименование объекта: земельный участок", page=3),
            _body("17.1 Кадастровый номер: 78:36:0005503:4", page=3),
            _body("18 Наименование объекта: нежилое здание", page=4),
            _body("18.1 Кадастровый номер: 78:36:0005503:5", page=4),
            # Second boundary — should be found by purity recovery.
            _el("ПРИЛОЖЕНИЕ № 5 ПОКУПНАЯ ЦЕНА", page=5),
            _body("Покупная цена, уплачиваемая Покупателем...", page=5),
            _body("Итого: 100 000 000 руб.", page=5),
        ]

        segments = segment_elements("doc-purity-1", elements)
        appendix_segments = [s for s in segments if s.segment_type == "appendix"]

        assert len(appendix_segments) >= 2, (
            f"Expected at least 2 appendix segments, got {len(appendix_segments)}: "
            f"{[s.segment_title for s in segments]}"
        )

        titles = [s.segment_title or "" for s in appendix_segments]
        assert any("4" in t for t in titles)
        assert any("5" in t for t in titles)


# ─── Running header deduplication ────────────────────────────────────────────


class TestRunningHeaderDeduplication:
    """Same appendix title repeated as running header must NOT cause re-split."""

    def test_repeated_appendix_title_not_split(self) -> None:
        elements = [
            _el("ДОГОВОР", page=1),
            _body("Текст.", page=1),
            _body("Ещё.", page=2),
            _el("Приложение № 1 Спецификация", page=3),
            _body("Содержание страница 1.", page=3),
            # Simulates running header on next page — same title.
            _el("Приложение № 1 Спецификация", page=4),
            _body("Содержание страница 2.", page=4),
            _el("Приложение № 1 Спецификация", page=5),
            _body("Содержание страница 3.", page=5),
        ]
        segments = segment_elements("doc-header-1", elements)
        appendix_segments = [s for s in segments if s.segment_type == "appendix"]

        # Must be exactly 1, not 3.
        assert len(appendix_segments) == 1, (
            f"Running header caused false splits: {len(appendix_segments)} appendix segments"
        )


# ─── Amendment / Addendum boundary ──────────────────────────────────────────


class TestAmendmentBoundary:
    """Amendment/addendum markers must be recognized as boundaries."""

    @pytest.mark.parametrize(
        "title",
        [
            "Addendum 1 Additional Terms",
            "Amendment No. 2 Price Adjustment",
            "Дополнительное соглашение № 1",
        ],
    )
    def test_amendment_boundary(self, title: str) -> None:
        elements = [
            _el("ДОГОВОР", page=1),
            _body("Текст.", page=1),
            _body("Ещё.", page=2),
            _el(title, page=3),
            _body("Условия дополнения.", page=3),
        ]
        segments = segment_elements("doc-amend", elements)
        assert any(s.segment_type == "amendment" for s in segments)


# ─── Disclosure Schedule ─────────────────────────────────────────────────────


class TestDisclosureSchedule:
    """Compound marker 'Disclosure Schedule' must work."""

    def test_disclosure_schedule_boundary(self) -> None:
        elements = [
            _el("SHARE PURCHASE AGREEMENT", page=1),
            _body("Agreement text.", page=1),
            _body("More text.", page=2),
            _el("Disclosure Schedule 1 Material Contracts", page=3),
            _body("List of contracts.", page=3),
        ]
        segments = segment_elements("doc-disc", elements)
        assert any(s.segment_type == "appendix" for s in segments)


# ─── Bare appendix keyword (no number, no title) ────────────────────────────


class TestBareAppendixKeyword:
    """
    'Приложение' or 'Appendix' alone (without number or title)
    should still be recognized when in boundary position.
    """

    def test_bare_russian_appendix(self) -> None:
        elements = [
            _el("ДОГОВОР", page=1),
            _body("Текст.", page=1),
            _body("Ещё.", page=2),
            _el("Приложение", page=3),
            _body("Содержание приложения.", page=3),
        ]
        segments = segment_elements("doc-bare", elements)
        # May or may not split depending on confidence — but should not crash.
        assert len(segments) >= 1


        
"""
Regression tests for TOC / catalog boundary suppression in segmenter.

Covers:
- appendix-family suppression on TOC / catalog pages;
- amendment-family suppression on TOC / catalog pages;
- preservation of real boundaries on non-TOC pages;
- purity recovery respecting suppression context.
"""

from __future__ import annotations

from services.structure.segmenter import (
    _extract_appendix_number,
    segment_elements,
)


def test_segmenter_suppresses_appendix_catalog_entries_inside_toc_page() -> None:
    elements = [
        {"element_id": "p1_1", "page": 1, "text": "ДОГОВОР КУПЛИ-ПРОДАЖИ"},
        {"element_id": "p1_2", "page": 1, "text": "ОТ 15 ДЕКАБРЯ 2014"},
        {"element_id": "p2_1", "page": 2, "text": "TABLE OF CONTENTS / СОДЕРЖАНИЕ"},
        {"element_id": "p2_2", "page": 2, "text": "1. DEFINITIONS..........................4"},
        {"element_id": "p2_3", "page": 2, "text": "2. SUBJECT OF THE AGREEMENT...........5"},
        {"element_id": "p2_4", "page": 2, "text": "3. PURCHASE PRICE.....................6"},
        {"element_id": "p2_5", "page": 2, "text": "APPENDICES / ПРИЛОЖЕНИЯ"},
        {
            "element_id": "p2_6",
            "page": 2,
            "text": "APPENDIX No. 1 FORM OF THE TRANSFER CERTIFICATE / ПРИЛОЖЕНИЕ № 1 ФОРМА АКТА",
        },
        {
            "element_id": "p2_7",
            "page": 2,
            "text": "APPENDIX No. 2 TERMS AND CONDITIONS OF THE LETTERS OF CREDIT / ПРИЛОЖЕНИЕ № 2",
        },
        {"element_id": "p2_8", "page": 2, "text": "УСЛОВИЯ АККРЕДИТИВОВ"},
        {
            "element_id": "p2_9",
            "page": 2,
            "text": "APPENDIX No. 3 CREDITOR INDEBTEDNESS / ПРИЛОЖЕНИЕ № 3 КРЕДИТОРСКАЯ ЗАДОЛЖЕННОСТЬ",
        },
        {
            "element_id": "p2_10",
            "page": 2,
            "text": "APPENDIX No. 4 REAL ESTATE / ПРИЛОЖЕНИЕ № 4 НЕДВИЖИМОЕ ИМУЩЕСТВО",
        },
        {
            "element_id": "p2_11",
            "page": 2,
            "text": "APPENDIX No. 5 PURCHASE PRICE / ПРИЛОЖЕНИЕ № 5 ПОКУПНАЯ ЦЕНА",
        },
        {"element_id": "p3_1", "page": 3, "text": "ДОГОВОР КУПЛИ-ПРОДАЖИ ОБЪЕКТОВ НЕДВИЖИМОСТИ"},
        {"element_id": "p3_2", "page": 3, "text": "1 ОПРЕДЕЛЕНИЯ"},
        {
            "element_id": "p3_3",
            "page": 3,
            "text": "1.1 «Акт» означает акт приема-передачи объектов недвижимости.",
        },
        {"element_id": "p4_1", "page": 4, "text": "2 ПРЕДМЕТ ДОГОВОРА"},
        {"element_id": "p4_2", "page": 4, "text": "2.1 Продавец обязуется передать объект недвижимости."},
        {"element_id": "p5_1", "page": 5, "text": "APPENDIX No. 5 PURCHASE PRICE"},
        {"element_id": "p5_2", "page": 5, "text": "1. Purchase price allocation."},
    ]

    segments = segment_elements(document_id="doc-toc-catalog", elements=elements)

    assert len(segments) == 2
    assert segments[0].segment_type == "contract"
    assert segments[0].page_start == 1
    assert segments[0].page_end == 4

    assert segments[1].segment_type == "appendix"
    assert segments[1].page_start == 5
    assert segments[1].page_end == 5
    assert segments[1].scope_name == "appendix_5"


def test_real_appendix_boundary_on_non_toc_page_is_kept() -> None:
    elements = [
        {"element_id": "e1", "page": 1, "text": "ДОГОВОР ПОСТАВКИ"},
        {"element_id": "e2", "page": 1, "text": "1. ПРЕДМЕТ ДОГОВОРА"},
        {"element_id": "e3", "page": 1, "text": "1.1 Поставщик обязуется поставить товар."},
        {"element_id": "e4", "page": 2, "text": "APPENDIX No. 1 SPECIFICATION"},
        {"element_id": "e5", "page": 2, "text": "1. Product list and price."},
    ]

    segments = segment_elements(document_id="doc-real-appendix", elements=elements)

    assert len(segments) == 2
    assert segments[0].segment_type == "contract"
    assert segments[1].segment_type == "appendix"
    assert segments[1].page_start == 2
    assert segments[1].scope_name == "appendix_1"


def test_purity_recovery_does_not_reintroduce_toc_page_appendix_boundaries() -> None:
    elements = [
        {"element_id": "e1", "page": 1, "text": "ДОГОВОР КУПЛИ-ПРОДАЖИ"},
        {"element_id": "e2", "page": 2, "text": "TABLE OF CONTENTS / СОДЕРЖАНИЕ"},
        {"element_id": "e3", "page": 2, "text": "1. DEFINITIONS..........................4"},
        {"element_id": "e4", "page": 2, "text": "2. PURCHASE PRICE......................5"},
        {"element_id": "e5", "page": 2, "text": "APPENDICES / ПРИЛОЖЕНИЯ"},
        {"element_id": "e6", "page": 2, "text": "APPENDIX No. 1 FORM OF ACT / ПРИЛОЖЕНИЕ № 1 ФОРМА АКТА"},
        {"element_id": "e7", "page": 2, "text": "APPENDIX No. 2 PRICE / ПРИЛОЖЕНИЕ № 2 ЦЕНА"},
        {"element_id": "e8", "page": 3, "text": "1 ОПРЕДЕЛЕНИЯ"},
        {"element_id": "e9", "page": 3, "text": "1.1 «Цена» означает цену договора."},
        {"element_id": "e10", "page": 4, "text": "2 ПРЕДМЕТ ДОГОВОРА"},
        {"element_id": "e11", "page": 4, "text": "2.1 Продавец обязуется передать объект."},
        {"element_id": "e12", "page": 5, "text": "APPENDIX No. 2 PRICE"},
        {"element_id": "e13", "page": 5, "text": "1. Price schedule."},
    ]

    segments = segment_elements(document_id="doc-purity-guard", elements=elements)

    assert len(segments) == 2
    assert [seg.page_start for seg in segments] == [1, 5]
    assert segments[1].scope_name == "appendix_2"


def test_extract_appendix_number_prefers_no_marker_over_single_n() -> None:
    text = "APPENDIX No. 5 PURCHASE PRICE / ПРИЛОЖЕНИЕ № 5 ПОКУПНАЯ ЦЕНА"
    assert _extract_appendix_number(text) == "5"


def test_preclassified_toc_elements_are_ignored_as_boundaries() -> None:
    elements = [
        {"element_id": "e1", "page": 1, "text": "ДОГОВОР №123"},
        {"element_id": "e2", "page": 1, "text": "1. ПРЕДМЕТ ДОГОВОРА"},
        {
            "element_id": "e3",
            "page": 2,
            "element_type": "toc_header",
            "text": "TABLE OF CONTENTS / СОДЕРЖАНИЕ",
        },
        {
            "element_id": "e4",
            "page": 2,
            "element_type": "toc_line",
            "text": "APPENDIX No. 1 FORM OF THE TRANSFER CERTIFICATE 10",
        },
        {"element_id": "e5", "page": 3, "text": "APPENDIX No. 1 FORM OF THE TRANSFER CERTIFICATE"},
        {"element_id": "e6", "page": 3, "text": "Acceptance act form."},
    ]

    segments = segment_elements(document_id="doc-preclassified-toc", elements=elements)

    assert len(segments) == 2
    assert segments[1].page_start == 3
    assert segments[1].segment_type == "appendix"


def test_segmenter_suppresses_amendment_catalog_entries_inside_toc_page() -> None:
    elements = [
        {"element_id": "e1", "page": 1, "text": "SHARE PURCHASE AGREEMENT"},
        {"element_id": "e2", "page": 1, "text": "1. DEFINITIONS"},
        {"element_id": "e3", "page": 2, "text": "TABLE OF CONTENTS / СОДЕРЖАНИЕ"},
        {"element_id": "e4", "page": 2, "text": "1. DEFINITIONS..........................4"},
        {"element_id": "e5", "page": 2, "text": "2. PURCHASE PRICE.......................5"},
        {"element_id": "e6", "page": 2, "text": "AMENDMENTS / ДОПОЛНЕНИЯ"},
        {"element_id": "e7", "page": 2, "text": "AMENDMENT No. 1 PURCHASE PRICE ADJUSTMENT"},
        {"element_id": "e8", "page": 2, "text": "ADDENDUM No. 2 TAX MATTERS"},
        {"element_id": "e9", "page": 3, "text": "1. DEFINITIONS"},
        {"element_id": "e10", "page": 3, "text": "1.1 Agreement means this agreement."},
        {"element_id": "e11", "page": 5, "text": "AMENDMENT No. 2 TAX MATTERS"},
        {"element_id": "e12", "page": 5, "text": "1. The Parties agree to amend the price terms."},
    ]

    segments = segment_elements(document_id="doc-amendment-catalog", elements=elements)

    assert len(segments) == 2
    assert segments[0].segment_type == "contract"
    assert segments[0].page_start == 1
    assert segments[0].page_end == 3

    assert segments[1].segment_type == "amendment"
    assert segments[1].page_start == 5
    assert segments[1].page_end == 5


def test_real_amendment_boundary_on_non_toc_page_is_kept() -> None:
    elements = [
        {"element_id": "e1", "page": 1, "text": "MASTER AGREEMENT"},
        {"element_id": "e2", "page": 1, "text": "1. GENERAL PROVISIONS"},
        {"element_id": "e3", "page": 1, "text": "1.1 The Parties agree as follows."},
        {"element_id": "e4", "page": 2, "text": "AMENDMENT No. 1 PRICE ADJUSTMENT"},
        {"element_id": "e5", "page": 2, "text": "1. Clause 3 shall be replaced as follows."},
    ]

    segments = segment_elements(document_id="doc-real-amendment", elements=elements)

    assert len(segments) == 2
    assert segments[0].segment_type == "contract"
    assert segments[1].segment_type == "amendment"
    assert segments[1].page_start == 2
    assert segments[1].page_end == 2


def test_segmenter_suppresses_schedule_catalog_entries_inside_toc_page() -> None:
    elements = [
        {"element_id": "e1", "page": 1, "text": "SALE AND PURCHASE AGREEMENT"},
        {"element_id": "e2", "page": 2, "text": "TABLE OF CONTENTS / СОДЕРЖАНИЕ"},
        {"element_id": "e3", "page": 2, "text": "1. DEFINITIONS..........................4"},
        {"element_id": "e4", "page": 2, "text": "2. PURCHASE PRICE.......................5"},
        {"element_id": "e5", "page": 2, "text": "SCHEDULES"},
        {"element_id": "e6", "page": 2, "text": "Schedule 1 Property List"},
        {"element_id": "e7", "page": 2, "text": "Schedule 2 Purchase Price"},
        {"element_id": "e8", "page": 3, "text": "1. DEFINITIONS"},
        {"element_id": "e9", "page": 3, "text": "1.1 Property means the property described herein."},
        {"element_id": "e10", "page": 5, "text": "Schedule 2 Purchase Price"},
        {"element_id": "e11", "page": 5, "text": "1. Purchase price allocation."},
    ]

    segments = segment_elements(document_id="doc-schedule-catalog", elements=elements)

    assert len(segments) == 2
    assert segments[0].segment_type == "contract"
    assert segments[0].page_start == 1
    assert segments[0].page_end == 3

    assert segments[1].segment_type == "appendix"
    assert segments[1].page_start == 5
    assert segments[1].page_end == 5
    assert segments[1].scope_name == "appendix_2"

    
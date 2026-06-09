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

def test_inline_appendix_listing_inside_body_clause_is_not_boundary() -> None:
    elements = [
        {"element_id": "e1", "page": 1, "text": "ДОГОВОР ГЕНЕРАЛЬНОГО ПОДРЯДА"},
        {"element_id": "e2", "page": 1, "text": "1 ТЕРМИНЫ И ОПРЕДЕЛЕНИЯ"},
        {"element_id": "e3", "page": 1, "text": "1.1 Определение означает определение."},
        {"element_id": "e4", "page": 3, "text": "2 ПРЕДМЕТ ДОГОВОРА"},
        {"element_id": "e5", "page": 3, "text": "2.1 Подрядчик обязуется выполнить работы."},
        {"element_id": "e6", "page": 5, "text": "3 ОБЩИЕ УСЛОВИЯ"},
        {"element_id": "e7", "page": 5, "text": "3.7 Срок действия Договора"},
        {"element_id": "e8", "page": 5, "text": "Настоящий Договор считается исполненным."},
        {"element_id": "e9", "page": 6, "text": "3.8 Части Договора"},
        {
            "element_id": "e10",
            "page": 6,
            "text": "Неотъемлемыми приложениями к настоящему Договору являются:",
        },
        {"element_id": "e11", "page": 6, "text": "Приложение 1. Техническое задание;"},
        {"element_id": "e12", "page": 6, "text": "Приложение 2. Виды работ;"},
        {"element_id": "e13", "page": 6, "text": "Приложение 3. Кадастровый паспорт Здания;"},
        {"element_id": "e14", "page": 6, "text": "Приложение 4. График производства работ."},
        {
            "element_id": "e15",
            "page": 6,
            "text": "Приложение 5: Распределение Цены Договора по группам работ;",
        },
        {"element_id": "e16", "page": 7, "text": "4 СРОК ВЫПОЛНЕНИЯ РАБОТ"},
        {"element_id": "e17", "page": 7, "text": "4.1 Срок выполнения работ"},
        {"element_id": "e18", "page": 7, "text": "4.1.1 Дата начала Реконструкции установлена не позднее."},
        {"element_id": "e19", "page": 8, "text": "5 ЦЕНА ДОГОВОРА"},
        {"element_id": "e20", "page": 8, "text": "5.1 Общая стоимость работ составляет."},
    ]

    segments = segment_elements(document_id="doc-inline-appendix-listing", elements=elements)

    assert len(segments) == 1
    assert segments[0].segment_type == "contract"
    assert segments[0].page_start == 1
    assert segments[0].page_end == 8

def test_inline_amendment_listing_inside_body_clause_is_not_boundary() -> None:
    elements = [
        {"element_id": "e1", "page": 1, "text": "MASTER AGREEMENT"},
        {"element_id": "e2", "page": 1, "text": "1 GENERAL PROVISIONS"},
        {"element_id": "e3", "page": 1, "text": "1.1 The Parties agree as follows."},
        {"element_id": "e4", "page": 2, "text": "2 TERM OF AGREEMENT"},
        {"element_id": "e5", "page": 2, "text": "2.1 This Agreement remains in force."},
        {"element_id": "e6", "page": 3, "text": "3 CONTRACT DOCUMENTS"},
        {"element_id": "e7", "page": 3, "text": "3.8 Amendments"},
        {
            "element_id": "e8",
            "page": 3,
            "text": "The following amendments form an integral part of this Agreement:",
        },
        {"element_id": "e9", "page": 3, "text": "Amendment No. 1 Price Adjustment"},
        {"element_id": "e10", "page": 3, "text": "Amendment No. 2 Tax Matters"},
        {"element_id": "e11", "page": 4, "text": "4 PAYMENT TERMS"},
        {"element_id": "e12", "page": 4, "text": "4.1 Payment shall be made within 10 days."},
        {"element_id": "e13", "page": 5, "text": "5 LIABILITY"},
        {"element_id": "e14", "page": 5, "text": "5.1 Each Party shall be liable for breach."},
    ]

    segments = segment_elements(document_id="doc-inline-amendment-listing", elements=elements)

    assert len(segments) == 1
    assert segments[0].segment_type == "contract"
    assert segments[0].page_start == 1
    assert segments[0].page_end == 5
    
def test_inflected_russian_appendix_mention_is_not_boundary() -> None:
    elements = [
        {"element_id": "e1", "page": 1, "text": "ДОГОВОР КРАТКОСРОЧНОЙ АРЕНДЫ"},
        {"element_id": "e2", "page": 1, "text": "1. ПРЕДМЕТ ДОГОВОРА"},
        {"element_id": "e3", "page": 2, "text": "4.4. Арендатор отвечает перед третьими лицами за любой ущерб."},
        {"element_id": "e4", "page": 3, "text": "5.4. В дополнение к Арендной плате Арендатор обязуется самостоятельно"},
        {"element_id": "e5", "page": 3, "text": "Приложением Договору. 5 к"},
        {"element_id": "e6", "page": 3, "text": "выплачивать налог на добавленную стоимость."},
        {"element_id": "e7", "page": 3, "text": "Приложением 5 к Договору."},
        {"element_id": "e8", "page": 3, "text": "4.5. Арендатор отвечает перед государственными органами за правильность."},
        {"element_id": "e9", "page": 4, "text": "6. ЗАКЛЮЧИТЕЛЬНЫЕ ПОЛОЖЕНИЯ"},
        {"element_id": "e10", "page": 4, "text": "6.1. Настоящий Договор вступает в силу с момента подписания."},
    ]

    segments = segment_elements(document_id="doc-inflected-russian-appendix-mention", elements=elements)

    assert len(segments) == 1
    assert segments[0].segment_type == "contract"
    assert segments[0].page_start == 1
    assert segments[0].page_end == 4

def test_dense_toc_lines_without_explicit_header_suppress_appendix_entries() -> None:
    elements = [
        {"element_id": "e1", "page": 1, "text": "ДОГОВОР КУПЛИ-ПРОДАЖИ ИМУЩЕСТВА"},
        {"element_id": "e2", "page": 2, "text": "1 ОПРЕДЕЛЕНИЯ...........................................................................................................................3"},
        {"element_id": "e3", "page": 2, "text": "2 ПРЕДМЕТ ДОГОВОРА...............................................................................................................4"},
        {"element_id": "e4", "page": 2, "text": "3 ПОКУПНАЯ ЦЕНА.....................................................................................................................4"},
        {"element_id": "e5", "page": 2, "text": "7 ЗАКЛЮЧИТЕЛЬНЫЕ ПОЛОЖЕНИЯ.......................................................................................5"},
        {"element_id": "e6", "page": 2, "text": "8 РЕКВИЗИТЫ И ПОДПИСИ СТОРОН.......................................................................................6"},
        {"element_id": "e7", "page": 2, "text": "Приложение 2: Имущество"},
        {"element_id": "e8", "page": 2, "text": "Приложение 3: Покупная цена"},
        {"element_id": "e9", "page": 2, "text": "Приложение 1: Форма Акта"},
        {"element_id": "e10", "page": 8, "text": "ПРИЛОЖЕНИЕ 1"},
        {"element_id": "e11", "page": 8, "text": "ФОРМА АКТА"},
        {"element_id": "e12", "page": 8, "text": "1. Стороны подтверждают факт передачи имущества."},
    ]

    segments = segment_elements(document_id="doc-dense-toc-without-header", elements=elements)

    assert len(segments) == 2
    assert segments[0].segment_type == "contract"
    assert segments[0].page_start == 1
    assert segments[0].page_end == 2

    assert segments[1].segment_type == "appendix"
    assert segments[1].page_start == 8
    assert segments[1].page_end == 8
    assert segments[1].scope_name == "appendix_1"

def test_inflected_russian_appendix_mention_is_not_boundary() -> None:
    """Склоняемые формы 'Приложением', 'Приложению' не должны быть границами."""
    elements = [
        {"element_id": "e1", "page": 1, "text": "ДОГОВОР АРЕНДЫ"},
        {"element_id": "e2", "page": 1, "text": "1. ПРЕДМЕТ ДОГОВОРА"},
        {"element_id": "e3", "page": 1, "text": "В соответствии с Приложением 5 к Договору."},
        {"element_id": "e4", "page": 2, "text": "Приложением Договору. 5 к"}, # OCR сломал порядок
        {"element_id": "e5", "page": 2, "text": "2. СРОКИ"},
    ]
    segments = segment_elements(document_id="doc-inflected", elements=elements)
    assert len(segments) == 1
    assert segments[0].segment_type == "contract"

def test_dense_toc_lines_without_explicit_header_suppress_appendix_entries() -> None:
    """Топология оглавления без заголовка СОДЕРЖАНИЕ должна подавлять приложения."""
    elements = [
        {"element_id": "e1", "page": 1, "text": "ДОГОВОР КУПЛИ-ПРОДАЖИ"},
        {"element_id": "e2", "page": 2, "text": "СОДЕРЖАНИ"}, # Разорвано
        {"element_id": "e3", "page": 2, "text": "Е1"},
        {"element_id": "e4", "page": 2, "text": "1 ОПРЕДЕЛЕНИЯ................................3"},
        {"element_id": "e5", "page": 2, "text": "2 ПРЕДМЕТ ДОГОВОРА..................4"},
        {"element_id": "e6", "page": 2, "text": "3 ПОКУПНАЯ ЦЕНА                        5"}, # Терминальный номер
        {"element_id": "e7", "page": 2, "text": "Приложение 1: Форма Акта"},
        {"element_id": "e8", "page": 2, "text": "Приложение 2: Имущество"},
        {"element_id": "e9", "page": 8, "text": "ПРИЛОЖЕНИЕ 1"},
        {"element_id": "e10", "page": 8, "text": "Реальное приложение"},
    ]
    segments = segment_elements(document_id="doc-broken-toc", elements=elements)
    assert len(segments) == 2
    assert segments[0].segment_type == "contract"
    assert segments[1].page_start == 8 # Только реальное приложение на стр. 8

def test_swarm_rule_suppresses_body_internal_listings() -> None:
    """Топология стаи (Swarm Rule) должна убивать списки внутри текста (п. 3.8)."""
    elements = [
        {"element_id": "e1", "page": 1, "text": "ДОГОВОР КУПЛИ-ПРОДАЖИ"},
        {"element_id": "e2", "page": 1, "text": "3.8 Части Договора"},
        {"element_id": "e3", "page": 1, "text": "Неотъемлемыми приложениями являются:"},
        {"element_id": "e4", "page": 1, "text": "Приложение 1. Форма Акта;"},
        {"element_id": "e5", "page": 1, "text": "Приложение 2. Имущество;"},
        {"element_id": "e6", "page": 1, "text": "4 СРОК ВЫПОЛНЕНИЯ РАБОТ"},
        {"element_id": "e7", "page": 2, "text": "ПРИЛОЖЕНИЕ 1"},
        {"element_id": "e8", "page": 2, "text": "Реальное приложение"},
    ]
    segments = segment_elements(document_id="doc-swarm", elements=elements)
    assert len(segments) == 2
    assert segments[0].segment_type == "contract"
    assert segments[1].page_start == 2 # Только реальное на стр. 2

def test_real_appendix_page_with_numeric_content_is_not_suppressed_as_broken_toc() -> None:
    elements = [
        {"element_id": "e1", "page": 1, "text": "ДОГОВОР КУПЛИ-ПРОДАЖИ ИМУЩЕСТВА"},
        {"element_id": "e2", "page": 1, "text": "1. ПРЕДМЕТ ДОГОВОРА"},
        {"element_id": "e3", "page": 2, "text": "ПРИЛОЖЕНИЕ 2"},
        {"element_id": "e4", "page": 2, "text": "ИМУЩЕСТВО"},
        {"element_id": "e5", "page": 2, "text": "1. Автоматическая система пожарной сигнализации"},
        {"element_id": "e6", "page": 2, "text": "Цена: 360 169,49 руб."},
        {"element_id": "e7", "page": 2, "text": "2. Асфальтированная площадка"},
        {"element_id": "e8", "page": 2, "text": "Цена: 1 822 457,00 руб."},
        {"element_id": "e9", "page": 2, "text": "3. Асфальтированная площадка /1"},
        {"element_id": "e10", "page": 2, "text": "Цена: 281 059,32 руб."},
    ]

    segments = segment_elements(document_id="doc-real-appendix-numeric-body", elements=elements)

    assert len(segments) == 2
    assert segments[0].segment_type == "contract"
    assert segments[1].segment_type == "appendix"
    assert segments[1].page_start == 2
    
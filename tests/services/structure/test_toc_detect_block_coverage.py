"""
Широкое покрытие detect_toc_block — все варианты расположения ToC.

Каждый тест декларирует ожидаемое поведение детектора (не подгонка).
При провале — видим, какие классы ToC текущий код обрабатывает неверно.

Категории:
- 1 страница / 2 страницы / титульник + ToC
- разрыв на page_artifact / markdown-таблице / пустой строке
- с page_hint / без page_hint / без dot-leader
- короткое / длинное ToC
- с явным маркером "СОДЕРЖАНИЕ" / без маркера
- документ без ToC
- mixed RU/EN
"""

from __future__ import annotations

import pytest

from services.structure.toc_parser import detect_toc_block


def el(text: str, page: int = 1, type_: str = "list_item") -> dict:
    return {
        "text": text,
        "page": page,
        "type": type_,
        "element_type": "heading_candidate",
        "page_offset": 0.01,
    }


def art(text: str, page: int = 1) -> dict:
    return {"text": text, "page": page, "type": "page_artifact", "page_offset": 0.5}


def tbl(text: str, page: int = 1) -> dict:
    return {"text": text, "page": page, "type": "table", "page_offset": 0.5}


def h(text: str, page: int = 1) -> dict:
    return {
        "text": text,
        "page": page,
        "type": "heading",
        "element_type": "heading_candidate",
        "page_offset": 0.02,
    }


def body(text: str, page: int = 3) -> dict:
    return {"text": text, "page": page, "type": "body_text", "page_offset": 0.5}


# ────────────────────────────────────────────────────────────────────────────
# Кейсы: (name, elements, expected_detected, expected_end)
# ────────────────────────────────────────────────────────────────────────────

CASES = [
    # 1. Простое ToC на стр. 1 (маркер + 5 entries) → end должен быть 6
    (
        "simple_toc_page_1",
        [
            el("СОДЕРЖАНИЕ", 1, "heading"),
            el("1. Определения .......... 3", 1),
            el("2. Предмет .......... 5", 1),
            el("3. Цена .......... 7", 1),
            el("4. Ответственность .......... 9", 1),
            el("5. Прочее .......... 11", 1),
            body("1. ОПРЕДЕЛЕНИЯ", 3),
        ],
        True,
        6,
    ),

    # 2. ToC на стр. 2 после титульника → end = 5
    (
        "toc_after_title_page",
        [
            h("ДОГОВОР", 1),
            el("от 15 Декабря 2014", 1, "body_text"),
            el("СОДЕРЖАНИЕ", 2, "heading"),
            el("1. Определения .......... 3", 2),
            el("2. Предмет .......... 5", 2),
            body("ДОГОВОР", 3),
        ],
        True,
        5,
    ),

    # 3. ToC через 2 страницы с page_artifact в середине
    (
        "toc_across_two_pages",
        [
            el("СОДЕРЖАНИЕ", 1, "heading"),
            el("1. Определения .......... 3", 1),
            el("2. Предмет .......... 5", 1),
            art("2 (16)", 1),
            el("3. Цена .......... 7", 2),
            el("4. Ответственность .......... 9", 2),
            el("5. Прочее .......... 11", 2),
            body("ДОГОВОР", 3),
        ],
        True,
        7,
    ),

    # 4. ToC с markdown-таблицей внутри
    (
        "toc_with_md_table_gap",
        [
            el("СОДЕРЖАНИЕ", 1, "heading"),
            el("1. Определения .......... 3", 1),
            el("2. Предмет .......... 5", 1),
            tbl("| 3 | Цена .......... 7 |", 1),
            el("4. Ответственность .......... 9", 1),
            el("5. Прочее .......... 11", 1),
            body("ДОГОВОР", 3),
        ],
        True,
        6,
    ),

    # 5. ToC без dot-leader, только с page_hint
    (
        "toc_without_dot_leader",
        [
            el("СОДЕРЖАНИЕ", 1, "heading"),
            el("1. Определения 3", 1),
            el("2. Предмет 5", 1),
            el("3. Цена 7", 1),
            el("4. Ответственность 9", 1),
            body("ДОГОВОР", 3),
        ],
        True,
        5,
    ),

    # 6. ToC без page_hint вообще (только uid + title)
    (
        "toc_without_page_hint",
        [
            el("СОДЕРЖАНИЕ", 1, "heading"),
            el("1. Определения", 1),
            el("2. Предмет", 1),
            el("3. Цена", 1),
            el("4. Ответственность", 1),
            body("ДОГОВОР", 3),
        ],
        True,
        5,
    ),

    # 7. ToC с многострочными entries
    (
        "toc_multiline_entries",
        [
            el("СОДЕРЖАНИЕ", 1, "heading"),
            el("1. Определения и термины,", 1),
            el("используемые в Договоре .......... 3", 1),
            el("2. Предмет Договора .......... 5", 1),
            el("3. Цена и порядок расчетов .......... 7", 1),
            body("ДОГОВОР", 3),
        ],
        True,
        5,
    ),

    # 8. Короткое ToC из 3 пунктов
    (
        "short_toc_3_entries",
        [
            el("СОДЕРЖАНИЕ", 1, "heading"),
            el("1. Определения .......... 3", 1),
            el("2. Предмет .......... 5", 1),
            el("3. Прочее .......... 7", 1),
            body("ДОГОВОР", 3),
        ],
        True,
        4,
    ),

    # 9. Длинное ToC (20+ entries)
    (
        "long_toc_20_entries",
        [el("СОДЕРЖАНИЕ", 1, "heading")]
        + [el(f"{i}. Раздел {i} .......... {3 + i}", 1) for i in range(1, 21)]
        + [body("ДОГОВОР", 3)],
        True,
        21,
    ),

    # 10. Документ без ToC — только body
    (
        "no_toc_plain_body",
        [
            h("ДОГОВОР КУПЛИ-ПРОДАЖИ", 1),
            body("Настоящий Договор заключен между...", 1),
            body("1. ОПРЕДЕЛЕНИЯ", 2),
            body("Термины используются в следующем значении...", 2),
        ],
        False,
        0,
    ),

    # 11. Документ без ToC — только параграфы, ничего похожего на TOC
    (
        "no_toc_plain_paragraphs",
        [
            body("Общие положения настоящего соглашения регулируют...", 1),
            body("Стороны обязуются соблюдать условия...", 1),
            body("Все споры рассматриваются в суде...", 2),
        ],
        False,
        0,
    ),

    # 12. ToC на английском
    (
        "toc_english",
        [
            el("TABLE OF CONTENTS", 1, "heading"),
            el("1. Definitions .......... 3", 1),
            el("2. Subject .......... 5", 1),
            el("3. Price .......... 7", 1),
            el("4. Liability .......... 9", 1),
            body("AGREEMENT", 3),
        ],
        True,
        5,
    ),

    # 13. ToC с большим разрывом (>K шумов подряд) → должен прерваться
    (
        "toc_with_large_gap",
        [
            el("СОДЕРЖАНИЕ", 1, "heading"),
            el("1. Определения .......... 3", 1),
            el("2. Предмет .......... 5", 1),
            body("большой параграф контента без нумерации", 1),
            body("продолжение контента", 1),
            body("еще контент", 1),
            body("и еще", 1),
            el("3. Цена .......... 7", 1),
            body("ДОГОВОР", 3),
        ],
        True,
        3,  # прерывается на первом body — не должен пропускать 4 body-параграфа
    ),

    # 14. Титульник + ToC на 2 стр. + тело на 3 стр. — реалистичный договор
    (
        "title_toc_body_realistic",
        [
            h("ДОГОВОР КУПЛИ-ПРОДАЖИ ИМУЩЕСТВА", 1),
            el("от 15 Декабря 2014", 1, "body_text"),
            el("г. Москва", 1, "body_text"),
            el("1 СОДЕРЖАНИЕ", 2, "heading"),
            el("1 ОПРЕДЕЛЕНИЯ...................................................", 2),
            el("2 ПРЕДМЕТ ДОГОВОРА..............................................", 2),
            el("3 ПОКУПНАЯ ЦЕНА.................................................", 2),
            el("4 ПОРЯДОК ПЕРЕДАЧИ ИМУЩЕСТВА....................................", 2),
            el("5 ЗАЯВЛЕНИЯ И ГАРАНТИИ ПРОДАВЦА.................................", 2),
            el("6 ОТВЕТСТВЕННОСТЬ СТОРОН........................................", 2),
            el("7 ЗАКЛЮЧИТЕЛЬНЫЕ ПОЛОЖЕНИЯ......................................", 2),
            el("8 РЕКВИЗИТЫ И ПОДПИСИ СТОРОН....................................", 2),
            tbl("| 1 | ОПРЕДЕЛЕНИЯ.......................", 2),
            el("7.2 ПРИЛОЖЕНИЯ", 2),
            el("7.3 Приложение № 1: Форма Акта", 2),
            el("7.1 Приложение № 3: Покупная цена", 2),
            art("2 (16)", 2),
            h("ДОГОВОР КУПЛИ-ПРОДАЖИ ИМУЩЕСТВА", 3),
            body("(1) Настоящий Договор заключен...", 3),
        ],
        True,
        16,  # ToC = marker(idx 3) + entries(idx 4-15). end = last_entry + 1 = 16.
             # idx 16 (artifact) и idx 17 (body heading) — не ToC entries,
             # правильно классифицируются как post_toc через _preamble_zone.
    ),

    # 15. ToC с пустыми строками внутри
    (
        "toc_with_empty_strings",
        [
            el("СОДЕРЖАНИЕ", 1, "heading"),
            el("1. Определения .......... 3", 1),
            el("", 1),
            el("2. Предмет .......... 5", 1),
            el("", 1),
            el("3. Цена .......... 7", 1),
            body("ДОГОВОР", 3),
        ],
        True,
        6,
    ),

    # 16. ToC с уже виденным uid (дубль uid из тела — не должно помочь)
    (
        "toc_uid_duplicated_in_body",
        [
            el("СОДЕРЖАНИЕ", 1, "heading"),
            el("1. Определения .......... 3", 1),
            el("2. Предмет .......... 5", 1),
            el("3. Цена .......... 7", 1),
            body("1. ОПРЕДЕЛЕНИЯ", 3),  # uid 1 в теле
            body("текст", 3),
            body("2. ПРЕДМЕТ", 4),  # uid 2 в теле
            body("текст", 4),
        ],
        True,
        4,  # ToC закрывается на body, а не поглощает тело из-за совпадения uid
    ),

    # 17. ToC с явным английским "CONTENTS" без точек
    (
        "toc_english_no_dots",
        [
            el("CONTENTS", 1, "heading"),
            el("1 Definitions 3", 1),
            el("2 Subject 5", 1),
            el("3 Price 7", 1),
            el("4 Liability 9", 1),
            body("AGREEMENT", 3),
        ],
        True,
        5,
    ),

    # 18. Только титульник, ToC отсутствует
    (
        "only_title_page",
        [
            h("ДОГОВОР КУПЛИ-ПРОДАЖИ ИМУЩЕСТВА", 1),
            el("от 15 Декабря 2014", 1, "body_text"),
            el("г. Москва", 1, "body_text"),
        ],
        False,
        0,
    ),
]


# Все 18 кейсов проходят после B7.4 (State Machine + extended entry/marker).
# Файл — регрессионный щит для детектора.

@pytest.mark.parametrize(
    "name,elements,expected_detected,expected_end",
    CASES,
    ids=[c[0] for c in CASES],
)
def test_detect_toc_block_coverage(name, elements, expected_detected, expected_end):
    tb = detect_toc_block(elements)
    assert tb.detected == expected_detected, (
        f"[{name}] detected: expected {expected_detected}, got {tb.detected} "
        f"(reason={tb.reason}, start={tb.start_index}, end={tb.end_index})"
    )
    if expected_detected:
        assert tb.end_index == expected_end, (
            f"[{name}] end_index: expected {expected_end}, got {tb.end_index} "
            f"(reason={tb.reason}, start={tb.start_index})"
        )

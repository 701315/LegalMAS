"""
Production-grade tests for deterministic record heading recovery.
Imports directly from real internal module _record_heading_recovery.py.
"""

import pytest
from services.structure._pipeline._record_heading_recovery import (
    attempt_record_heading_recovery,
    _parse_alpha_index,
    _looks_like_initials_noise,
)


def test_alpha_index_gost_cyrillic():
    """ГОСТ-нумерация кириллицы (пропуск Ё, З, Й, О, Ъ, Ы, Ь)."""
    assert _parse_alpha_index("А") == 1
    assert _parse_alpha_index("Б") == 2
    assert _parse_alpha_index("В") == 3
    assert _parse_alpha_index("Г") == 4
    assert _parse_alpha_index("Д") == 5
    assert _parse_alpha_index("Е") == 6
    assert _parse_alpha_index("Ж") == 7
    assert _parse_alpha_index("И") == 8  # З и Й пропущены по ГОСТ
    assert _parse_alpha_index("К") == 9
    assert _parse_alpha_index("а") == 1
    assert _parse_alpha_index("З") is None
    assert _parse_alpha_index("Ё") is None
    assert _parse_alpha_index("О") is None


def test_alpha_index_latin():
    """Латинская нумерация."""
    assert _parse_alpha_index("a") == 1
    assert _parse_alpha_index("b") == 2
    assert _parse_alpha_index("c") == 3


def test_initials_noise_distinguishes_surname_vs_section_title():
    """Проверяет фильтр ФИО vs заголовок раздела."""
    assert _looks_like_initials_noise("А", "Иванов") is True
    assert _looks_like_initials_noise("А", "Петров И.") is True
    assert _looks_like_initials_noise("А", "Демонтаж выбранных Объектов Недвижимости") is False
    assert _looks_like_initials_noise("Б", "Очистка Земельного участка") is False
    assert _looks_like_initials_noise("В", "Благоустройство территории") is False


def test_recovery_alpha_cyrillic_series():
    """Восстановление кириллической ГОСТ-серии (А., Б., В.)."""
    elements = [
        {"element_type": "body_text", "text": "А. Демонтаж выбранных Объектов Недвижимости"},
        {"element_type": "body_text", "text": "Арендатор выполняет демонтаж следующих объектов:"},
        {"element_type": "body_text", "text": "Б. Очистка Земельного участка"},
        {"element_type": "body_text", "text": "Арендатор осуществляет самостоятельно очистку..."},
        {"element_type": "body_text", "text": "В. Благоустройство территории"},
        {"element_type": "body_text", "text": "Порядок благоустройства..."},
    ]
    res = attempt_record_heading_recovery(document_id="doc1", elements=elements)
    assert res.applied is True
    assert res.diagnostics["promoted_count"] == 3
    assert res.elements[0]["element_type"] == "heading_candidate"
    assert res.elements[2]["element_type"] == "heading_candidate"
    assert res.elements[4]["element_type"] == "heading_candidate"
    assert res.elements[1]["element_type"] == "body_text"


def test_recovery_with_allowed_gaps():
    """Допуск пропусков в серии (1, 2, 4, 5 — пропущен 3)."""
    elements = [
        {"element_type": "body_text", "text": "1) Первый пункт работы"},
        {"element_type": "body_text", "text": "2) Второй пункт работы"},
        {"element_type": "body_text", "text": "4) Четвертый пункт работы (3 удален)"},
        {"element_type": "body_text", "text": "5) Пятый пункт работы"},
    ]
    res = attempt_record_heading_recovery(document_id="doc1", elements=elements)
    assert res.applied is True
    assert res.diagnostics["promoted_count"] == 4


def test_recovery_rejects_noise_initials():
    """Чистые инициалы ФИО не образуют record-series."""
    elements = [
        {"element_type": "body_text", "text": "А. Иванов"},
        {"element_type": "body_text", "text": "Б. Петров"},
        {"element_type": "body_text", "text": "В. Сидоров"},
        {"element_type": "body_text", "text": "Г. Васильев"},
    ]
    res = attempt_record_heading_recovery(document_id="doc1", elements=elements)
    assert res.applied is False


def test_recovery_format_isolation_alpha_not_mixed_with_numeric():
    """Разные format_key не склеиваются в одну серию."""
    elements = [
        {"element_type": "body_text", "text": "А. Первый раздел спецификации"},
        {"element_type": "body_text", "text": "1) Числовой пункт другого формата"},
        {"element_type": "body_text", "text": "Б. Второй раздел спецификации"},
        {"element_type": "body_text", "text": "2) Ещё один числовой пункт"},
        {"element_type": "body_text", "text": "В. Третий раздел спецификации"},
        {"element_type": "body_text", "text": "3) Третий числовой пункт"},
    ]
    res = attempt_record_heading_recovery(document_id="doc1", elements=elements)
    assert res.applied is True
    assert res.diagnostics["promoted_count"] == 6

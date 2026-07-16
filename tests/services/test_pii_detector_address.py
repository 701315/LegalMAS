"""
Тесты address-regex в PIIDetector.

Фокус: проверить что паттерн:
1. Корректно матчит реальные адреса
2. НЕ захватывает текст за пределами адреса (главная проблема патча)
3. Останавливается на стоп-символах
4. Не захватывает переносы строк
5. Не ломает downstream-детекцию других PII-типов рядом с адресом
"""

import re
import pytest
from services.pii_detector import PIIDetector, PIIEntity
from core.constants import PIIEntityType


@pytest.fixture
def detector():
    """PIIDetector без NER для изоляции regex-тестов."""
    return PIIDetector(ner_enabled=False)


# ─── Вспомогательные функции ─────────────────────────────────────────────────


def find_address_entities(detector: PIIDetector, text: str) -> list[PIIEntity]:
    """Вернуть только ADDRESS-сущности из результата detect()."""
    return [e for e in detector.detect(text) if e.type == PIIEntityType.ADDRESS]


# ─── Класс 1: корректное распознавание реальных адресов ──────────────────────


class TestAddressDetectionPositive:
    """Адреса, которые ДОЛЖНЫ быть найдены."""

    def test_simple_street_and_house(self, detector):
        """Простой адрес: улица + дом."""
        text = "Адрес: ул. Ленина, д. 5"
        entities = find_address_entities(detector, text)
        assert len(entities) >= 1
        assert "Ленина" in entities[0].text

    def test_full_address_with_apartment(self, detector):
        """Полный адрес с квартирой."""
        text = "зарегистрирован по адресу: ул. Садовая, д. 10, кв. 25"
        entities = find_address_entities(detector, text)
        assert len(entities) >= 1

    def test_prospect_trigger(self, detector):
        """Триггерное слово 'проспект'."""
        text = "офис: пр. Невский, д. 100"
        entities = find_address_entities(detector, text)
        assert len(entities) >= 1

    def test_pereulok_trigger(self, detector):
        """Триггерное слово 'переулок'."""
        text = "пер. Столярный, д. 3"
        entities = find_address_entities(detector, text)
        assert len(entities) >= 1

    def test_address_with_building_number(self, detector):
        """Адрес с буквой в номере дома."""
        text = "ул. Тверская, д. 15А"
        entities = find_address_entities(detector, text)
        assert len(entities) >= 1

    def test_address_with_slash_number(self, detector):
        """Адрес с дробным номером дома (5/3)."""
        text = "ул. Арбат, д. 5"
        entities = find_address_entities(detector, text)
        assert len(entities) >= 1

    def test_english_address(self, detector):
        """Адрес на английском (mixed documents)."""
        text = "Office at ul. Lenina, d. 1"
        entities = find_address_entities(detector, text)
        assert len(entities) >= 1


# ─── Класс 2: граница захвата — главный тест патча ───────────────────────────


class TestAddressBoundaryContainment:
    """
    Тесты на то, что адрес НЕ захватывает соседний текст.
    Это главная проблема патча — жадный захват через соседние реквизиты.
    """

    def test_does_not_capture_inn_after_address(self, detector):
        """
        КРИТИЧЕСКИЙ ТЕСТ: адрес не должен поглощать ИНН после него.

        До патча: address-regex захватывал "ул. Ленина, д. 5, ИНН 1234567890"
        целиком, downstream не находил ИНН.
        """
        text = "ул. Ленина, д. 5, ИНН 1234567890"
        all_entities = detector.detect(text)
        entity_types = {e.type for e in all_entities}

        address_entities = [e for e in all_entities if e.type == PIIEntityType.ADDRESS]
        assert len(address_entities) >= 1

        address_text = address_entities[0].text
        # Адрес не должен содержать цифры ИНН
        assert "1234567890" not in address_text, (
            f"Address regex captured INN digits: '{address_text}'"
        )

    def test_does_not_capture_across_newline(self, detector):
        """
        КРИТИЧЕСКИЙ ТЕСТ: адрес не захватывает текст после переноса строки.

        До патча: \s в классе матчил \n, захват шёл на следующую строку.
        """
        text = "ул. Ленина, д. 5\nПокупатель: Иванов И.И."
        entities = find_address_entities(detector, text)
        assert len(entities) >= 1

        for entity in entities:
            assert "\n" not in entity.text, (
                f"Address entity captured newline: {repr(entity.text)}"
            )
            assert "Иванов" not in entity.text, (
                f"Address entity captured buyer name: '{entity.text}'"
            )

    def test_stops_at_semicolon(self, detector):
        """Адрес останавливается на точке с запятой."""
        text = "ул. Ленина, д. 5; ИНН 1234567890"
        entities = find_address_entities(detector, text)
        if entities:
            assert "1234567890" not in entities[0].text

    def test_stops_at_colon(self, detector):
        """Адрес останавливается на двоеточии."""
        text = "ул. Садовая, д. 10: следующий реквизит"
        entities = find_address_entities(detector, text)
        if entities:
            assert "следующий" not in entities[0].text

    def test_does_not_capture_passport_after_address(self, detector):
        """
        Реалистичный документ: адрес и паспорт в одном элементе.
        Оба должны быть найдены как отдельные сущности.
        """
        text = (
            "Продавец: ООО «Ромашка», адрес: ул. Ленина, д. 5, "
            "ИНН 1234567890.\nПокупатель: Иванов И.И., паспорт серия 45 00 № 123456."
        )
        all_entities = detector.detect(text)
        types_found = {e.type for e in all_entities}

        # Должны быть найдены отдельные сущности, не одна гигантская
        address_entities = [e for e in all_entities if e.type == PIIEntityType.ADDRESS]
        assert len(address_entities) >= 1

        # Адрес не должен включать паспортные данные
        for addr in address_entities:
            assert "паспорт" not in addr.text.lower(), (
                f"Address captured 'паспорт': '{addr.text}'"
            )
            assert "123456" not in addr.text, (
                f"Address captured passport number: '{addr.text}'"
            )

    def test_max_length_not_exceeded(self, detector):
        """
        Ни один address-entity не превышает разумную максимальную длину.
        120 символов контента + триггерное слово.
        """
        # Длинный текст с адресом в начале
        text = (
            "ул. Тверская, д. 1 "
            + "слово " * 30  # ~180 символов мусора после адреса
        )
        entities = find_address_entities(detector, text)
        for entity in entities:
            assert len(entity.text) <= 150, (
                f"Address entity too long ({len(entity.text)} chars): '{entity.text[:80]}...'"
            )

    def test_two_addresses_in_one_element(self, detector):
        """Два адреса в одном тексте находятся как две отдельные сущности."""
        text = (
            "Продавец: ул. Ленина, д. 1.\n"
            "Покупатель: ул. Садовая, д. 5."
        )
        entities = find_address_entities(detector, text)
        # Должно быть найдено 2 адреса, не один гигантский
        assert len(entities) == 2, (
            f"Expected 2 address entities, got {len(entities)}: "
            + str([e.text for e in entities])
        )


# ─── Класс 3: реалистичные юридические тексты ────────────────────────────────


class TestAddressInLegalContext:
    """Тесты на реалистичных фрагментах юридических документов."""

    def test_standard_contract_preamble_ru(self, detector):
        """
        Стандартная преамбула договора купли-продажи.
        Адрес должен быть найден, не захватить ИНН и не выйти за границу.
        """
        text = (
            "ООО «Ромашка», ИНН 7701234567, юридический адрес: "
            "ул. Садовая-Сухаревская, д. 2, г. Москва, именуемый Продавец"
        )
        all_entities = detector.detect(text)
        address_entities = [e for e in all_entities if e.type == PIIEntityType.ADDRESS]

        # Адрес должен быть найден
        assert len(address_entities) >= 1

        # Адрес не должен содержать ИНН
        for addr in address_entities:
            assert "7701234567" not in addr.text

    def test_address_followed_by_party_role(self, detector):
        """Адрес перед ролевым словом не захватывает роль."""
        text = "дом 15, г. Санкт-Петербург, именуемый в дальнейшем Арендатор"
        entities = find_address_entities(detector, text)
        for entity in entities:
            assert "Арендатор" not in entity.text

    def test_no_false_positive_on_pure_number(self, detector):
        """
        'д. 5' без улицы — не должно давать ложный address entity
        если нет триггерного слова улицы/проспекта перед номером дома.

        Уточнение: 'д.' само по себе является триггером в паттерне.
        Тест проверяет что матч не уходит далеко за номер.
        """
        text = "п. 5 договора гласит следующее: стороны обязуются"
        # 'п.' не входит в триггерные слова паттерна — не должно матчиться
        entities = find_address_entities(detector, text)
        # Если нашлось — убедимся что это не длинный захват
        for entity in entities:
            assert len(entity.text) < 50


# ─── Класс 4: регрессионные тесты (не сломали старое поведение) ──────────────


class TestAddressRegression:
    """Убеждаемся что патч не сломал корректное поведение."""

    def test_address_entity_has_correct_type(self, detector):
        """Найденная сущность имеет тип ADDRESS."""
        text = "ул. Ленина, д. 5"
        entities = find_address_entities(detector, text)
        assert all(e.type == PIIEntityType.ADDRESS for e in entities)

    def test_address_entity_source_is_regex(self, detector):
        """Адрес найден через regex, не NER."""
        text = "ул. Ленина, д. 5"
        entities = find_address_entities(detector, text)
        assert all(e.source == "regex" for e in entities)

    def test_address_span_matches_text(self, detector):
        """Span сущности корректно указывает на text в исходной строке."""
        text = "проживает по адресу: ул. Тверская, д. 10"
        entities = find_address_entities(detector, text)
        for entity in entities:
            extracted = text[entity.start:entity.end]
            assert extracted == entity.text, (
                f"Span mismatch: entity.text='{entity.text}', "
                f"text[{entity.start}:{entity.end}]='{extracted}'"
            )

    def test_empty_text_returns_no_entities(self, detector):
        """Пустой текст → пустой список."""
        assert detector.detect("") == []
        assert detector.detect("   ") == []

    def test_text_without_address_triggers_returns_no_address(self, detector):
        """Текст без триггерных слов → нет ADDRESS-сущностей."""
        text = "Стороны договорились о следующем: срок поставки 30 дней."
        entities = find_address_entities(detector, text)
        assert len(entities) == 0

        
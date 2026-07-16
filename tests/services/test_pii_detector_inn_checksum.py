"""
Тесты checksum-валидации ИНН.

Цель:
- no-context 12-digit число должно считаться ИНН только если checksum валиден
- context-based ИНН по слову "ИНН" продолжает распознаваться
- не ломаем остальные паттерны
"""

import pytest

from core.constants import PIIEntityType
from services.pii_detector import PIIDetector, _is_valid_inn_checksum


@pytest.fixture
def detector():
    return PIIDetector(ner_enabled=False)


class TestINNChecksumHelper:
    """Unit tests для внутреннего checksum helper."""

    def test_valid_12_digit_inn_returns_true(self):
        """
        Валидный 12-значный ИНН физлица проходит checksum.

        Используем известный валидный тестовый номер.
        """
        assert _is_valid_inn_checksum("500100732259") is True

    def test_invalid_12_digit_inn_returns_false(self):
        """Невалидный 12-значный ИНН не проходит checksum."""
        assert _is_valid_inn_checksum("500100732258") is False

    def test_non_digit_string_returns_false(self):
        """Нестрогие данные не валидируются как ИНН."""
        assert _is_valid_inn_checksum("50010073AB59") is False

    def test_wrong_length_returns_false(self):
        """Строка неверной длины не валидируется как ИНН."""
        assert _is_valid_inn_checksum("50010073225") is False
        assert _is_valid_inn_checksum("5001007322599") is False


class TestINNDetectionWithChecksum:
    """Интеграционные тесты detect()."""

    def test_no_context_valid_12_digit_inn_detected(self, detector):
        """
        Без контекста валидный 12-значный ИНН должен быть найден.
        """
        text = "Реквизит 500100732259 указан в документе."
        entities = detector.detect(text)

        inns = [e for e in entities if e.type == PIIEntityType.INN]
        assert len(inns) == 1
        assert inns[0].text == "500100732259"

    def test_no_context_invalid_12_digit_number_not_detected_as_inn(self, detector):
        """
        Без контекста невалидное 12-значное число не должно считаться ИНН.
        """
        text = "Реквизит 500100732258 указан в документе."
        entities = detector.detect(text)

        inns = [e for e in entities if e.type == PIIEntityType.INN]
        assert len(inns) == 0

    def test_context_12_digit_inn_detected_even_if_checksum_invalid(self, detector):
        """
        С контекстом 'ИНН' распознаём номер даже при невалидном checksum.
        Это осознанный recall-first компромисс для OCR/грязных документов.
        """
        text = "ИНН 500100732258 указан в карточке клиента."
        entities = detector.detect(text)

        inns = [e for e in entities if e.type == PIIEntityType.INN]
        assert len(inns) == 1
        # После Patch 5 контекстное слово "ИНН" остаётся вне entity
        assert inns[0].text == "500100732258"

    def test_context_10_digit_inn_detected(self, detector):
        """
        10-значный ИНН распознаётся только по контексту и продолжает работать.
        """
        text = "ИНН: 7701234567"
        entities = detector.detect(text)

        inns = [e for e in entities if e.type == PIIEntityType.INN]
        assert len(inns) == 1
        assert inns[0].text == "7701234567"

    def test_random_12_digit_number_not_misclassified(self, detector):
        """
        Произвольный 12-значный номер без контекста не должен давать false positive.
        """
        text = "Номер накладной: 123456789012"
        entities = detector.detect(text)

        inns = [e for e in entities if e.type == PIIEntityType.INN]
        assert len(inns) == 0

    def test_multiple_numbers_only_valid_inn_detected(self, detector):
        """
        Среди нескольких 12-значных чисел без контекста
        должен распознаваться только валидный ИНН.
        """
        text = "Числа: 123456789012, 500100732259, 500100732258."
        entities = detector.detect(text)

        inns = [e for e in entities if e.type == PIIEntityType.INN]
        assert len(inns) == 1
        assert inns[0].text == "500100732259"

    def test_no_regression_for_other_entity_types(self, detector):
        """
        Добавление checksum не должно ломать другие паттерны.
        """
        text = "Email: test@example.com, телефон: +7 999 123-45-67"
        entities = detector.detect(text)

        types = {e.type for e in entities}
        assert PIIEntityType.EMAIL in types
        assert PIIEntityType.PHONE in types

    def test_context_12_digit_inn_not_truncated_to_10_digits(self, detector):
        """
        Контекстный 12-значный ИНН не должен резаться до 10 цифр.
        Regression test for regex alternation order.
        """
        text = "ИНН 500100732259 указан в документе."
        entities = detector.detect(text)

        inns = [e for e in entities if e.type == PIIEntityType.INN]
        assert len(inns) == 1
        assert inns[0].text == "500100732259"

    def test_context_15_digit_ogrnip_not_truncated_to_13_digits(self, detector):
        """
        Контекстный 15-значный ОГРНИП не должен резаться до 13 цифр.
        Regression test for regex alternation order.
        """
        text = "ОГРНИП 304500116000157 зарегистрирован."
        entities = detector.detect(text)

        ogrns = [e for e in entities if e.type == PIIEntityType.OGRN]
        assert len(ogrns) == 1
        assert ogrns[0].text == "304500116000157"
        
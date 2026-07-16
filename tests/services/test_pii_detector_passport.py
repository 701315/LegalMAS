"""
Тесты context-паттернов (Паспорт, ИНН, ОГРН).

Фокус: триггерные слова ("паспорт", "ИНН", "ОГРН") НЕ должны 
включаться в PII-сущность и заменяться токеном.
"""

import pytest
from services.pii_detector import PIIDetector
from core.constants import PIIEntityType


@pytest.fixture
def detector():
    return PIIDetector(ner_enabled=False)


class TestContextPatternsBoundaries:
    """Тесты границ захвата для контекстных паттернов."""

    def test_passport_context_does_not_swallow_label(self, detector):
        """Слово 'паспорт' не попадает в PII entity."""
        text = "Предъявлен паспорт серия 45 00 № 123456, выданный"
        entities = detector.detect(text)
        
        passports = [e for e in entities if e.type == PIIEntityType.PASSPORT]
        assert len(passports) == 1
        
        entity = passports[0]
        assert "паспорт" not in entity.text.lower()
        # Сущность должна содержать только цифры и разделители номера
        assert entity.text.replace(" ", "") == "4500№123456"
        
        # Проверим, что span действительно указывает на часть без 'паспорт'
        assert text[entity.start:entity.end] == entity.text

    def test_inn_context_does_not_swallow_label(self, detector):
        """Слово 'ИНН' не попадает в PII entity."""
        text = "Организация: ООО Ромашка, ИНН: 7701234567, КПП"
        entities = detector.detect(text)
        
        inns = [e for e in entities if e.type == PIIEntityType.INN]
        assert len(inns) == 1
        
        entity = inns[0]
        assert "инн" not in entity.text.lower()
        assert entity.text == "7701234567"
        
    def test_ogrn_context_does_not_swallow_label(self, detector):
        """Слово 'ОГРН' не попадает в PII entity."""
        text = "ОГРН 1037804009077 присвоен"
        entities = detector.detect(text)
        
        ogrns = [e for e in entities if e.type == PIIEntityType.OGRN]
        assert len(ogrns) == 1
        
        entity = ogrns[0]
        assert "огрн" not in entity.text.lower()
        assert entity.text == "1037804009077"

    def test_passport_without_context_still_detected(self, detector):
        """Паспорт без слова 'паспорт' (паттерн из _PATTERNS) работает корректно."""
        text = "Документ 4500 123456 выдан"
        entities = detector.detect(text)
        
        passports = [e for e in entities if e.type == PIIEntityType.PASSPORT]
        assert len(passports) == 1
        
        entity = passports[0]
        assert entity.text == "4500 123456"

    def test_multiple_context_entities(self, detector):
        """Несколько контекстных сущностей в одном тексте."""
        text = "ИНН 7701234567, ОГРН 1037804009077, паспорт серия 45 00 № 123456"
        entities = detector.detect(text)
        
        assert len(entities) == 3
        
        inn = next(e for e in entities if e.type == PIIEntityType.INN)
        ogrn = next(e for e in entities if e.type == PIIEntityType.OGRN)
        passport = next(e for e in entities if e.type == PIIEntityType.PASSPORT)
        
        assert inn.text == "7701234567"
        assert ogrn.text == "1037804009077"
        assert passport.text.replace(" ", "") == "4500№123456"


        
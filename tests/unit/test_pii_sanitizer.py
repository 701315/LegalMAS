"""
Unit-тесты PII Sanitizer.

Покрывают:
  - Regex-детекцию (паспорт, телефон, email, адрес)
  - Preserve-типы (ИНН, ОГРН, кадастр) — НЕ должны токенизироваться
  - ROLE_MAP: имя стороны → SELLER/BUYER при наличии контекста
  - party_role_keywords из YAML
  - applicable_triggers → PIIPolicy.use_role_map=True
  - Шифрование/расшифровка маппинга
  - Null case: текст без PII → sanitized == raw, mapping пустой
"""

import pytest
from cryptography.fernet import Fernet

from src.core.constants import PIIEntityType, PIITokenPolicy
from src.services.pii_detector import (
    PIIDetector,
    PIIEntity,
    get_preserve_types,
    reset_detector,
)
from src.services.pii_encryption import (
    PIIEncryptor,
    decrypt_mapping,
    encrypt_mapping,
    reset_encryptor,
)
from src.services.pii_tokenizer import PIIPolicy, PIITokenizer, TokenizationResult

# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def detector():
    """Детектор без NER для быстрых тестов."""
    return PIIDetector(ner_enabled=False)


@pytest.fixture
def detector_with_ner():
    """Детектор с NER (медленнее, но полнее)."""
    return PIIDetector(ner_enabled=True)


@pytest.fixture
def tokenizer():
    """Токенизатор."""
    return PIITokenizer()


@pytest.fixture(autouse=True)
def reset_singletons():
    """Сбрасываем singleton'ы перед каждым тестом."""
    reset_detector()
    reset_encryptor()
    yield
    reset_detector()
    reset_encryptor()


# ═══════════════════════════════════════════════════════════════════════════════
# Detector tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestPIIDetector:
    """Тесты детектора PII."""

    def test_detect_passport(self, detector):
        """Обнаружение паспорта РФ."""
        entities = detector.detect("Паспорт 4512 123456 выдан")
        types = [e.type for e in entities]
        assert PIIEntityType.PASSPORT in types

    def test_detect_passport_with_series(self, detector):
        """Обнаружение паспорта с пробелом в серии."""
        entities = detector.detect("Паспорт серия 45 12 номер 123456")
        types = [e.type for e in entities]
        assert PIIEntityType.PASSPORT in types

    def test_detect_phone_plus7(self, detector):
        """Обнаружение телефона +7."""
        entities = detector.detect("Телефон: +7 999 123-45-67")
        types = [e.type for e in entities]
        assert PIIEntityType.PHONE in types

    def test_detect_phone_8(self, detector):
        """Обнаружение телефона 8."""
        entities = detector.detect("Звоните: 8 (495) 123-45-67")
        types = [e.type for e in entities]
        assert PIIEntityType.PHONE in types

    def test_detect_email(self, detector):
        """Обнаружение email."""
        entities = detector.detect("Контакт: test@example.com")
        types = [e.type for e in entities]
        assert PIIEntityType.EMAIL in types

        email_entity = next(e for e in entities if e.type == PIIEntityType.EMAIL)
        assert email_entity.text == "test@example.com"

    def test_detect_address(self, detector):
        """Обнаружение адреса."""
        entities = detector.detect("Адрес: ул. Ленина, д. 10")
        types = [e.type for e in entities]
        assert PIIEntityType.ADDRESS in types

    def test_detect_inn_10_digits(self, detector):
        """Обнаружение ИНН юрлица (10 цифр) с контекстом."""
        entities = detector.detect("ИНН 7707083893")
        inn_entities = [e for e in entities if e.type == PIIEntityType.INN]
        assert len(inn_entities) >= 1
        # Контекстный паттерн захватывает "ИНН" + цифры
        assert "7707083893" in inn_entities[0].text

    def test_detect_inn_10_digits_standalone(self, detector):
        """10-значное число без контекста НЕ распознаётся как ИНН (конфликт с паспортом)."""
        # Без контекста "ИНН" 10 цифр не распознаются как ИНН
        entities = detector.detect("Номер: 7707083893")
        inn_entities = [e for e in entities if e.type == PIIEntityType.INN]
        # Должно быть 0, т.к. нет контекста и 10 цифр без пробела — не паспорт
        assert len(inn_entities) == 0

    def test_detect_inn_12_digits(self, detector):
        """Обнаружение ИНН физлица (12 цифр)."""
        entities = detector.detect("ИНН физлица: 123456789012")
        inn_entities = [e for e in entities if e.type == PIIEntityType.INN]
        assert len(inn_entities) >= 1

    def test_detect_ogrn(self, detector):
        """Обнаружение ОГРН."""
        entities = detector.detect("ОГРН 1027700132195")
        ogrn_entities = [e for e in entities if e.type == PIIEntityType.OGRN]
        assert len(ogrn_entities) >= 1

    def test_detect_cadastral(self, detector):
        """Обнаружение кадастрового номера."""
        entities = detector.detect("кадастровый номер 77:01:0001001:1234")
        cadastral = [e for e in entities if e.type == PIIEntityType.CADASTRAL]
        assert len(cadastral) >= 1
        assert "77:01:0001001:1234" in cadastral[0].text

    def test_empty_text(self, detector):
        """Пустой текст → пустой список."""
        assert detector.detect("") == []
        assert detector.detect("   ") == []

    def test_no_pii_text(self, detector):
        """Текст без PII."""
        text = "Настоящий договор заключён в соответствии с ГК РФ."
        entities = detector.detect(text)
        # Не должно быть телефонов, паспортов, email
        sensitive = [
            e
            for e in entities
            if e.type in {PIIEntityType.PHONE, PIIEntityType.PASSPORT, PIIEntityType.EMAIL}
        ]
        assert len(sensitive) == 0

    def test_multiple_entities(self, detector):
        """Несколько сущностей в одном тексте."""
        text = "Паспорт 4512 123456, тел. +7 999 111-22-33, email: test@mail.ru"
        entities = detector.detect(text)
        types = {e.type for e in entities}
        assert PIIEntityType.PASSPORT in types
        assert PIIEntityType.PHONE in types
        assert PIIEntityType.EMAIL in types

    def test_deduplication_no_overlaps(self, detector):
        """Пересекающиеся сущности дедуплицируются."""
        text = "Данные: 1234567890123"  # 13 цифр — ОГРН
        entities = detector.detect(text)

        # Проверяем, что нет пересекающихся spans
        for i, e1 in enumerate(entities):
            for e2 in entities[i + 1 :]:
                assert (
                    e1.end <= e2.start or e2.end <= e1.start
                ), f"Overlapping entities: {e1} and {e2}"


class TestPIIDetectorNER:
    """Тесты с NER (опциональные)."""

    @pytest.mark.skipif(not PIIDetector(ner_enabled=True)._ner, reason="natasha not available")
    def test_detect_person_name(self, detector_with_ner):
        """Обнаружение ФИО через NER."""
        entities = detector_with_ner.detect("Иванов Иван Иванович подписал договор")
        person_names = [e for e in entities if e.type == PIIEntityType.PERSON_NAME]
        assert len(person_names) >= 1


class TestPreserveTypes:
    """Тесты preserve-типов."""

    def test_preserve_types_contains_inn(self):
        """INN в preserve-типах."""
        preserve = get_preserve_types()
        assert PIIEntityType.INN in preserve

    def test_preserve_types_contains_ogrn(self):
        """OGRN в preserve-типах."""
        preserve = get_preserve_types()
        assert PIIEntityType.OGRN in preserve

    def test_preserve_types_contains_cadastral(self):
        """CADASTRAL в preserve-типах."""
        preserve = get_preserve_types()
        assert PIIEntityType.CADASTRAL in preserve

    def test_policy_preserve_action_for_inn(self, detector):
        """PIIPolicy возвращает PRESERVE для ИНН."""
        entities = detector.detect("ИНН 7707083893")
        inn_entities = [e for e in entities if e.type == PIIEntityType.INN]
        assert len(inn_entities) >= 1

        policy = PIIPolicy()
        for ent in inn_entities:
            assert policy.get_action(ent.type) == PIITokenPolicy.PRESERVE

    def test_policy_preserve_action_for_cadastral(self, detector):
        """PIIPolicy возвращает PRESERVE для кадастра."""
        entities = detector.detect("кадастровый номер 77:01:0001001:1234")
        cadastral = [e for e in entities if e.type == PIIEntityType.CADASTRAL]
        assert len(cadastral) >= 1

        policy = PIIPolicy()
        for ent in cadastral:
            assert policy.get_action(ent.type) == PIITokenPolicy.PRESERVE


# ═══════════════════════════════════════════════════════════════════════════════
# Tokenizer tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestPIITokenizer:
    """Тесты токенизатора."""

    def test_tokenize_email(self, tokenizer):
        """Токенизация email."""
        entity = PIIEntity(type=PIIEntityType.EMAIL, start=9, end=25, text="test@example.com")
        policy = PIIPolicy(use_role_map=False)

        result = tokenizer.tokenize("Контакт: test@example.com", [entity], policy)

        assert isinstance(result, TokenizationResult)
        assert "test@example.com" not in result.sanitized_text
        assert "EMAIL1" in result.sanitized_text
        assert result.mapping.get("EMAIL1") == "test@example.com"
        assert result.entities_tokenized == 1

    def test_tokenize_phone(self, tokenizer):
        """Токенизация телефона."""
        entity = PIIEntity(type=PIIEntityType.PHONE, start=5, end=22, text="+7 999 123-45-67")
        policy = PIIPolicy(use_role_map=False)

        result = tokenizer.tokenize("Тел: +7 999 123-45-67", [entity], policy)

        assert "+7 999 123-45-67" not in result.sanitized_text
        assert "PHONE1" in result.sanitized_text
        assert result.entities_tokenized == 1

    def test_preserve_inn(self, tokenizer):
        """ИНН не токенизируется при preserve-политике."""
        entity = PIIEntity(type=PIIEntityType.INN, start=4, end=14, text="7707083893")
        policy = PIIPolicy()  # default preserve_types включает INN

        result = tokenizer.tokenize("ИНН 7707083893", [entity], policy)

        # ИНН должен остаться
        assert "7707083893" in result.sanitized_text
        assert result.entities_preserved == 1
        assert result.entities_tokenized == 0

    def test_role_map_seller(self, tokenizer):
        """ROLE_MAP: имя в контексте 'продавец' → SELLER."""
        entity = PIIEntity(type=PIIEntityType.PERSON_NAME, start=9, end=20, text="Иванов Иван")
        policy = PIIPolicy(use_role_map=True)
        context = "продавец Иванов Иван действует на основании"

        result = tokenizer.tokenize(
            "продавец Иванов Иван действует", [entity], policy, context_window=context
        )

        assert "Иванов Иван" not in result.sanitized_text
        assert "SELLER" in result.sanitized_text
        assert result.entities_role_mapped == 1

    def test_role_map_buyer(self, tokenizer):
        """ROLE_MAP: имя в контексте 'покупатель' → BUYER."""
        entity = PIIEntity(type=PIIEntityType.PERSON_NAME, start=11, end=22, text="Петров Пётр")
        policy = PIIPolicy(use_role_map=True)
        context = "покупатель Петров Пётр обязуется"

        result = tokenizer.tokenize(
            "покупатель Петров Пётр обязуется", [entity], policy, context_window=context
        )

        assert "BUYER" in result.sanitized_text
        assert result.entities_role_mapped == 1

    def test_role_map_fallback_to_tokenize(self, tokenizer):
        """ROLE_MAP без подходящего контекста → fallback на TOKENIZE."""
        entity = PIIEntity(type=PIIEntityType.PERSON_NAME, start=0, end=11, text="Сидоров Сид")
        policy = PIIPolicy(use_role_map=True)
        # Контекст без ключевых слов ролей
        context = "участник договора"

        result = tokenizer.tokenize(
            "Сидоров Сид подписал", [entity], policy, context_window=context
        )

        assert "Сидоров Сид" not in result.sanitized_text
        assert "PERSONNAME1" in result.sanitized_text
        assert result.entities_tokenized == 1
        assert result.entities_role_mapped == 0

    def test_role_map_disabled(self, tokenizer):
        """use_role_map=False → обычная токенизация."""
        entity = PIIEntity(type=PIIEntityType.PERSON_NAME, start=9, end=20, text="Иванов Иван")
        policy = PIIPolicy(use_role_map=False)
        context = "продавец Иванов Иван"  # контекст есть, но role_map выключен

        result = tokenizer.tokenize(
            "продавец Иванов Иван", [entity], policy, context_window=context
        )

        assert "SELLER" not in result.sanitized_text
        assert "PERSONNAME1" in result.sanitized_text
        assert result.entities_tokenized == 1

    def test_multiple_entities_same_type(self, tokenizer):
        """Несколько сущностей одного типа → разные номера."""
        entities = [
            PIIEntity(type=PIIEntityType.PHONE, start=0, end=17, text="+7 999 111-11-11"),
            PIIEntity(type=PIIEntityType.PHONE, start=20, end=37, text="+7 888 222-22-22"),
        ]
        policy = PIIPolicy(use_role_map=False)

        result = tokenizer.tokenize("+7 999 111-11-11 и +7 888 222-22-22", entities, policy)

        assert "PHONE1" in result.sanitized_text
        assert "PHONE2" in result.sanitized_text
        assert len(result.mapping) == 2
        assert result.entities_tokenized == 2

    def test_null_case_no_entities(self, tokenizer):
        """Нет сущностей → текст без изменений."""
        text = "Простой текст без PII"
        policy = PIIPolicy()

        result = tokenizer.tokenize(text, [], policy)

        assert result.sanitized_text == text
        assert result.mapping == {}
        assert result.entities_tokenized == 0
        assert result.entities_preserved == 0

    def test_null_case_only_preserve_entities(self, tokenizer, detector):
        """Только preserve-сущности → текст без изменений, mapping пустой."""
        text = "ИНН 7707083893, ОГРН 1027700132195"
        entities = detector.detect(text)
        policy = PIIPolicy()

        result = tokenizer.tokenize(text, entities, policy)

        # Текст должен остаться без изменений
        assert "7707083893" in result.sanitized_text
        assert "1027700132195" in result.sanitized_text
        assert result.mapping == {}
        assert result.entities_tokenized == 0
        assert result.entities_preserved >= 1


class TestPIIPolicyFromYAML:
    """Тесты party_role_keywords из YAML."""

    def test_custom_party_role_keywords(self, tokenizer):
        """Кастомные party_role_keywords из YAML."""
        entity = PIIEntity(type=PIIEntityType.PERSON_NAME, start=8, end=19, text="Иванов Иван")

        # Кастомный словарь ролей (как из YAML)
        custom_keywords = {
            "заёмщик": "BORROWER",
            "кредитор": "LENDER",
        }

        policy = PIIPolicy(use_role_map=True, party_role_keywords=custom_keywords)
        context = "заёмщик Иванов Иван обязуется"

        result = tokenizer.tokenize(
            "заёмщик Иванов Иван обязуется", [entity], policy, context_window=context
        )

        assert "BORROWER" in result.sanitized_text
        assert result.entities_role_mapped == 1

    def test_custom_keywords_override_default(self, tokenizer):
        """Кастомные keywords используются вместо дефолтных."""
        entity = PIIEntity(type=PIIEntityType.PERSON_NAME, start=9, end=20, text="Иванов Иван")

        # Переопределяем "продавец" на другую роль (без подстроки SELLER)
        custom_keywords = {
            "продавец": "VENDOR",
        }

        policy = PIIPolicy(use_role_map=True, party_role_keywords=custom_keywords)
        context = "продавец Иванов Иван"

        result = tokenizer.tokenize(
            "продавец Иванов Иван", [entity], policy, context_window=context
        )

        # Используется VENDOR из кастомного словаря
        assert "VENDOR" in result.sanitized_text
        assert result.mapping.get("VENDOR") == "Иванов Иван"
        assert result.entities_role_mapped == 1

    def test_empty_custom_keywords_fallback_to_default(self, tokenizer):
        """Пустой dict {} → fallback на дефолтный словарь → SELLER найден."""
        entity = PIIEntity(type=PIIEntityType.PERSON_NAME, start=9, end=20, text="Иванов Иван")

        policy = PIIPolicy(
            use_role_map=True,
            party_role_keywords={},  # Пустой dict
        )
        context = "продавец Иванов Иван"

        result = tokenizer.tokenize(
            "продавец Иванов Иван", [entity], policy, context_window=context
        )

        # Пустой dict → fallback на дефолт → "продавец" → SELLER
        assert "SELLER" in result.sanitized_text
        assert result.entities_role_mapped == 1

    def test_none_keywords_uses_default(self, tokenizer):
        """party_role_keywords=None → используется дефолтный словарь."""
        entity = PIIEntity(type=PIIEntityType.PERSON_NAME, start=9, end=20, text="Иванов Иван")

        policy = PIIPolicy(
            use_role_map=True,
            party_role_keywords=None,  # явно None
        )
        context = "продавец Иванов Иван"

        result = tokenizer.tokenize(
            "продавец Иванов Иван", [entity], policy, context_window=context
        )

        # Должен сработать дефолтный словарь
        assert "SELLER" in result.sanitized_text
        assert result.entities_role_mapped == 1

    def test_custom_keywords_no_match_fallback_tokenize(self, tokenizer):
        """Кастомные keywords без совпадения → fallback на TOKENIZE."""
        entity = PIIEntity(type=PIIEntityType.PERSON_NAME, start=0, end=11, text="Иванов Иван")

        # Кастомный словарь без "участник"
        custom_keywords = {
            "заёмщик": "BORROWER",
        }

        policy = PIIPolicy(use_role_map=True, party_role_keywords=custom_keywords)
        context = "участник Иванов Иван"  # "участник" не в словаре

        result = tokenizer.tokenize(
            "Иванов Иван подписал", [entity], policy, context_window=context
        )

        # Нет совпадения → fallback на TOKENIZE
        assert "PERSONNAME1" in result.sanitized_text
        assert result.entities_tokenized == 1
        assert result.entities_role_mapped == 0


class TestPIIPolicyBuilder:
    """Тесты построения политики."""

    def test_build_with_triggers(self):
        """applicable_triggers → use_role_map=True."""
        policy = PIITokenizer.build_policy_from_triggers(
            applicable_triggers=["sale_purchase"],
        )
        assert policy.use_role_map is True

    def test_build_without_triggers(self):
        """Нет триггеров → use_role_map=False."""
        policy = PIITokenizer.build_policy_from_triggers(
            applicable_triggers=None,
        )
        assert policy.use_role_map is False

    def test_build_empty_triggers(self):
        """Пустой список → use_role_map=False."""
        policy = PIITokenizer.build_policy_from_triggers(
            applicable_triggers=[],
        )
        assert policy.use_role_map is False

    def test_build_with_custom_keywords(self):
        """party_role_keywords передаются в политику."""
        custom_keywords = {"заёмщик": "BORROWER"}

        policy = PIITokenizer.build_policy_from_triggers(
            applicable_triggers=["loan"],
            party_role_keywords=custom_keywords,
        )

        assert policy.use_role_map is True
        assert policy.party_role_keywords == custom_keywords

    def test_build_preserve_party_roles_disabled(self):
        """preserve_party_roles=False явно → use_role_map=False."""
        # Передаём preserve_party_roles=False явно, без monkeypatch
        policy = PIITokenizer.build_policy_from_triggers(
            applicable_triggers=["sale_purchase"],
            preserve_party_roles=False,
        )

        assert policy.use_role_map is False

    def test_build_preserve_party_roles_enabled(self):
        """preserve_party_roles=True явно → use_role_map зависит от triggers."""
        policy = PIITokenizer.build_policy_from_triggers(
            applicable_triggers=["sale_purchase"],
            preserve_party_roles=True,
        )
        assert policy.use_role_map is True

        policy_no_triggers = PIITokenizer.build_policy_from_triggers(
            applicable_triggers=[],
            preserve_party_roles=True,
        )
        assert policy_no_triggers.use_role_map is False  # triggers пустые

    def test_build_empty_keywords_normalized_to_none(self):
        """Пустой dict {} нормализуется в None."""
        policy = PIITokenizer.build_policy_from_triggers(
            applicable_triggers=["loan"],
            party_role_keywords={},  # пустой
        )

        # Пустой dict должен быть нормализован в None
        assert policy.party_role_keywords is None


# ═══════════════════════════════════════════════════════════════════════════════
# Encryption tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestPIIEncryption:
    """Тесты шифрования."""

    def test_encrypt_decrypt_roundtrip(self):
        """Шифрование и дешифрование с валидным ключом."""
        key = Fernet.generate_key().decode()
        encryptor = PIIEncryptor(key)

        original = {"PERSON1": "Иванов Иван", "EMAIL1": "test@example.com"}
        encrypted = encryptor.encrypt_mapping(original)

        assert isinstance(encrypted, bytes)
        # Проверяем что данные зашифрованы (кириллица не видна)
        assert "Иванов".encode() not in encrypted

        decrypted = encryptor.decrypt_mapping(encrypted)
        assert decrypted == original

    def test_encryption_enabled_flag(self):
        """is_encryption_enabled корректно отражает наличие ключа."""
        key = Fernet.generate_key().decode()

        with_key = PIIEncryptor(key)
        assert with_key.is_encryption_enabled is True

        without_key = PIIEncryptor("")
        assert without_key.is_encryption_enabled is False

    def test_dev_mode_plaintext(self):
        """Dev-режим: пустой ключ → plaintext."""
        encryptor = PIIEncryptor("")

        original = {"PERSON1": "Тест"}
        encrypted = encryptor.encrypt_mapping(original)

        # В dev-режиме "зашифрованные" данные — это JSON (plaintext)
        assert "Тест".encode() in encrypted

        decrypted = encryptor.decrypt_mapping(encrypted)
        assert decrypted == original

    def test_generate_key(self):
        """Генерация валидного ключа."""
        key = PIIEncryptor.generate_key()

        assert isinstance(key, str)
        assert len(key) > 0

        # Ключ должен работать
        encryptor = PIIEncryptor(key)
        assert encryptor.is_encryption_enabled is True

    def test_different_keys_incompatible(self):
        """Разные ключи несовместимы."""
        key1 = Fernet.generate_key().decode()
        key2 = Fernet.generate_key().decode()

        encryptor1 = PIIEncryptor(key1)
        encryptor2 = PIIEncryptor(key2)

        original = {"TEST": "data"}
        encrypted = encryptor1.encrypt_mapping(original)

        from src.services.pii_encryption import PIIEncryptionError

        with pytest.raises(PIIEncryptionError):
            encryptor2.decrypt_mapping(encrypted)


class TestPIIEncryptionLegacyFunctions:
    """Тесты legacy-функций encrypt_mapping/decrypt_mapping."""

    def test_encrypt_decrypt_with_settings(self, monkeypatch):
        """encrypt_mapping/decrypt_mapping используют settings."""
        key = Fernet.generate_key().decode()

        # Мокаем settings
        class MockSettings:
            PII_ENCRYPTION_KEY = key

        # Патчим get_settings в модуле encryption
        monkeypatch.setattr("src.core.config.settings", MockSettings())

        # Сбрасываем singleton чтобы перечитать settings
        reset_encryptor()

        original = {"PERSON1": "Иванов Иван", "EMAIL1": "test@example.com"}
        encrypted = encrypt_mapping(original)

        assert isinstance(encrypted, bytes)

        decrypted = decrypt_mapping(encrypted)
        assert decrypted == original

    def test_dev_mode_no_key(self, monkeypatch):
        """Без ключа маппинг хранится в открытом виде (dev)."""

        class MockSettings:
            PII_ENCRYPTION_KEY = ""

        monkeypatch.setattr("src.core.config.settings", MockSettings())

        reset_encryptor()

        original = {"PERSON1": "Тест"}
        encrypted = encrypt_mapping(original)
        decrypted = decrypt_mapping(encrypted)

        assert decrypted == original


# ═══════════════════════════════════════════════════════════════════════════════
# Integration-like tests (detector + tokenizer)
# ═══════════════════════════════════════════════════════════════════════════════


class TestDetectorTokenizerIntegration:
    """Интеграционные тесты детектора и токенизатора."""

    def test_full_pipeline_with_mixed_entities(self, detector, tokenizer):
        """Полный pipeline: детекция + токенизация."""
        text = "Продавец Иванов, тел. +7 999 123-45-67, ИНН 7707083893"

        entities = detector.detect(text)
        policy = PIIPolicy(use_role_map=True)

        result = tokenizer.tokenize(text, entities, policy, context_window=text[:500])

        # Телефон токенизирован
        assert "+7 999 123-45-67" not in result.sanitized_text
        assert "PHONE1" in result.sanitized_text

        # ИНН сохранён
        assert "7707083893" in result.sanitized_text

    def test_text_without_pii(self, detector, tokenizer):
        """Текст без PII → sanitized == raw."""
        text = "Договор заключён согласно законодательству РФ."

        entities = detector.detect(text)
        policy = PIIPolicy()

        result = tokenizer.tokenize(text, entities, policy)

        # Текст не изменился
        assert result.sanitized_text == text
        assert result.mapping == {}

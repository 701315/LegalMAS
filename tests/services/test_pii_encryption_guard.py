"""
Тесты production-guard для PII-шифрования.

Цель: найти реальные проблемы, не подогнать под зелёный.
Каждый тест проверяет конкретный инвариант через реальный код,
без mock'ирования логики шифрования.
"""

import pytest
from unittest.mock import patch

from services.pii_encryption import (
    PIIEncryptor,
    PIIEncryptionError,
    get_pii_encryptor,
    reset_encryptor,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_singleton():
    """Сбрасывает singleton перед каждым тестом."""
    reset_encryptor()
    yield
    reset_encryptor()


VALID_FERNET_KEY = PIIEncryptor.generate_key()


# ─── PIIEncryptor unit tests ──────────────────────────────────────────────────


class TestPIIEncryptorInit:
    """Тесты инициализации энкриптора."""

    def test_empty_key_sets_fernet_to_none(self):
        """Пустой ключ → _fernet=None, is_encryption_enabled=False."""
        enc = PIIEncryptor("")
        assert enc._fernet is None
        assert enc.is_encryption_enabled is False

    def test_valid_key_initializes_fernet(self):
        """Валидный ключ → _fernet инициализирован."""
        enc = PIIEncryptor(VALID_FERNET_KEY)
        assert enc._fernet is not None
        assert enc.is_encryption_enabled is True

    def test_invalid_base64_raises_error(self):
        """Невалидный base64 → PIIEncryptionError при инициализации."""
        with pytest.raises(PIIEncryptionError, match="неверный формат base64"):
            PIIEncryptor("not-a-valid-fernet-key")

    def test_wrong_length_key_raises_error(self):
        """
        Ключ правильного base64-формата, но неправильной длины
        → PIIEncryptionError.
        """
        import base64
        short_key = base64.urlsafe_b64encode(b"x" * 16).decode()
        with pytest.raises(PIIEncryptionError, match="32 байта"):
            PIIEncryptor(short_key)

    def test_whitespace_only_key_treated_as_empty(self):
        """Ключ из пробелов → strip() → пустая строка → dev-режим."""
        enc = PIIEncryptor("   ")
        assert enc._fernet is None
        assert enc.is_encryption_enabled is False


class TestPIIEncryptorEncryptDecrypt:
    """Тесты round-trip шифрования."""

    def test_encrypt_decrypt_roundtrip_with_valid_key(self):
        """С валидным ключом encrypt→decrypt возвращает исходный маппинг."""
        enc = PIIEncryptor(VALID_FERNET_KEY)
        mapping = {
            "PERSONNAME1": "Иванов Иван Иванович",
            "PASSPORT1": "45 00 123456",
            "PHONE1": "+7 999 123-45-67",
        }
        encrypted = enc.encrypt_mapping(mapping)
        decrypted = enc.decrypt_mapping(encrypted)
        assert decrypted == mapping

    def test_encrypted_result_is_bytes(self):
        """Результат encrypt_mapping — bytes."""
        enc = PIIEncryptor(VALID_FERNET_KEY)
        result = enc.encrypt_mapping({"TOKEN1": "value"})
        assert isinstance(result, bytes)

    def test_encrypted_bytes_are_not_plaintext(self):
        """
        Зашифрованный маппинг НЕ содержит оригинальных значений в plaintext.
        Это ключевой инвариант: данные должны быть нечитаемы без ключа.
        """
        enc = PIIEncryptor(VALID_FERNET_KEY)
        sensitive_value = "Иванов Иван Иванович"
        mapping = {"PERSONNAME1": sensitive_value}
        encrypted = enc.encrypt_mapping(mapping)
        # Зашифрованный blob не должен содержать исходное значение
        assert sensitive_value.encode("utf-8") not in encrypted

    def test_dev_mode_returns_plaintext_bytes(self):
        """
        В dev-режиме (пустой ключ) encrypt_mapping возвращает JSON в plaintext.
        Тест намеренно документирует это поведение как ИЗВЕСТНОЕ и НЕ продакшн.
        """
        enc = PIIEncryptor("")
        mapping = {"TOKEN1": "sensitive_data"}
        result = enc.encrypt_mapping(mapping)
        # В dev-режиме результат — читаемый JSON
        assert b"sensitive_data" in result

    def test_dev_mode_decrypt_roundtrip(self):
        """В dev-режиме decrypt_mapping корректно разбирает plaintext JSON."""
        enc = PIIEncryptor("")
        mapping = {"TOKEN1": "value1", "TOKEN2": "value2"}
        encrypted = enc.encrypt_mapping(mapping)
        decrypted = enc.decrypt_mapping(encrypted)
        assert decrypted == mapping

    def test_decrypt_with_wrong_key_raises_error(self):
        """Дешифровка с другим ключом → PIIEncryptionError."""
        enc1 = PIIEncryptor(VALID_FERNET_KEY)
        enc2 = PIIEncryptor(PIIEncryptor.generate_key())
        encrypted = enc1.encrypt_mapping({"TOKEN1": "value"})
        with pytest.raises(PIIEncryptionError, match="Ошибка при дешифровании"):
            enc2.decrypt_mapping(encrypted)

    def test_decrypt_garbage_raises_error(self):
        """Дешифровка мусорных байт → PIIEncryptionError."""
        enc = PIIEncryptor(VALID_FERNET_KEY)
        with pytest.raises(PIIEncryptionError):
            enc.decrypt_mapping(b"this is not encrypted data")

    def test_empty_mapping_roundtrip(self):
        """Пустой маппинг корректно шифруется и дешифруется."""
        enc = PIIEncryptor(VALID_FERNET_KEY)
        result = enc.decrypt_mapping(enc.encrypt_mapping({}))
        assert result == {}

    def test_unicode_values_roundtrip(self):
        """Unicode-значения (русский текст) корректно переживают round-trip."""
        enc = PIIEncryptor(VALID_FERNET_KEY)
        mapping = {
            "PERSONNAME1": "Фёдоров Михаил Петрович",
            "ADDRESS1": "ул. Ленина, д. 5, кв. 12",
            "INN1": "1234567890",
        }
        assert enc.decrypt_mapping(enc.encrypt_mapping(mapping)) == mapping


# ─── get_pii_encryptor production-guard tests ────────────────────────────────


class TestGetPIIEncryptorProductionGuard:
    """
    Тесты production-guard в get_pii_encryptor().

    ВАЖНО: эти тесты проверяют реальное защитное поведение,
    а не то что мы хотим видеть. Если тест падает — значит guard не работает.
    """

    def test_production_with_empty_key_raises(self):
        """
        ENVIRONMENT=production + PII_ENCRYPTION_KEY="" → PIIEncryptionError.
        Это главный инвариант патча: plaintext в production недопустим.
        """
        with (
            patch("services.pii_encryption.settings") as mock_settings,
        ):
            mock_settings.ENVIRONMENT = "production"
            mock_settings.PII_ENCRYPTION_KEY = ""

            with pytest.raises(PIIEncryptionError, match="required in production"):
                get_pii_encryptor()

    def test_production_with_valid_key_succeeds(self):
        """ENVIRONMENT=production + валидный ключ → нормальная инициализация."""
        with patch("services.pii_encryption.settings") as mock_settings:
            mock_settings.ENVIRONMENT = "production"
            mock_settings.PII_ENCRYPTION_KEY = VALID_FERNET_KEY

            enc = get_pii_encryptor(VALID_FERNET_KEY)
            assert enc.is_encryption_enabled is True

    def test_development_with_empty_key_succeeds(self):
        """
        ENVIRONMENT=development + пустой ключ → dev-режим без ошибки.
        Plaintext допустим только в dev.
        """
        with patch("services.pii_encryption.settings") as mock_settings:
            mock_settings.ENVIRONMENT = "development"
            mock_settings.PII_ENCRYPTION_KEY = ""

            enc = get_pii_encryptor("")
            assert enc.is_encryption_enabled is False

    def test_singleton_returns_same_instance(self):
        """get_pii_encryptor() возвращает один и тот же объект."""
        enc1 = get_pii_encryptor(VALID_FERNET_KEY)
        enc2 = get_pii_encryptor(VALID_FERNET_KEY)
        assert enc1 is enc2

    def test_reset_allows_reinitialize(self):
        """После reset_encryptor() создаётся новый экземпляр."""
        enc1 = get_pii_encryptor(VALID_FERNET_KEY)
        reset_encryptor()
        enc2 = get_pii_encryptor(VALID_FERNET_KEY)
        assert enc1 is not enc2

    def test_explicit_key_overrides_settings(self):
        """Явный ключ в аргументе имеет приоритет над settings."""
        with patch("services.pii_encryption.settings") as mock_settings:
            mock_settings.ENVIRONMENT = "development"
            mock_settings.PII_ENCRYPTION_KEY = ""

            enc = get_pii_encryptor(VALID_FERNET_KEY)
            assert enc.is_encryption_enabled is True


# ─── config.py validator tests ───────────────────────────────────────────────


class TestConfigProductionValidator:
    """
    Тесты model_validator в Settings.

    Проверяем что config.py реально блокирует старт с небезопасными дефолтами.
    Используем прямое создание Settings с переопределёнными полями.
    """

    def test_production_with_empty_pii_key_raises(self):
        """
        Settings(ENVIRONMENT='production', PII_ENCRYPTION_KEY='') → ValueError.
        """
        from core.config import Settings

        with pytest.raises(ValueError, match="PII_ENCRYPTION_KEY"):
            Settings(
                ENVIRONMENT="production",
                PII_ENCRYPTION_KEY="",
                JWT_SECRET_KEY="valid-jwt-secret-that-is-long-enough-32ch",
                MINIO_SECRET_KEY="valid-minio-secret",
            )

    def test_production_with_default_jwt_key_raises(self):
        """
        Settings(ENVIRONMENT='production', JWT дефолт) → ValueError.
        """
        from core.config import Settings

        with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
            Settings(
                ENVIRONMENT="production",
                PII_ENCRYPTION_KEY=VALID_FERNET_KEY,
                JWT_SECRET_KEY="dev-secret-key-change-in-production",
                MINIO_SECRET_KEY="valid-minio-secret",
            )

    def test_production_with_default_minio_key_raises(self):
        """
        Settings(ENVIRONMENT='production', MINIO дефолт) → ValueError.
        """
        from core.config import Settings

        with pytest.raises(ValueError, match="MINIO_SECRET_KEY"):
            Settings(
                ENVIRONMENT="production",
                PII_ENCRYPTION_KEY=VALID_FERNET_KEY,
                JWT_SECRET_KEY="valid-jwt-secret-that-is-long-enough-32ch",
                MINIO_SECRET_KEY="minioadmin123",
            )

    def test_production_multiple_insecure_raises_all(self):
        """
        Несколько небезопасных значений → в сообщении упоминаются все.
        """
        from core.config import Settings

        with pytest.raises(ValueError) as exc_info:
            Settings(
                ENVIRONMENT="production",
                PII_ENCRYPTION_KEY="",
                JWT_SECRET_KEY="dev-secret-key-change-in-production",
                MINIO_SECRET_KEY="minioadmin123",
            )
        error_msg = str(exc_info.value)
        assert "PII_ENCRYPTION_KEY" in error_msg
        assert "JWT_SECRET_KEY" in error_msg
        assert "MINIO_SECRET_KEY" in error_msg

    def test_development_with_all_defaults_succeeds(self):
        """
        Settings(ENVIRONMENT='development') с дефолтами → нет ошибки.
        Dev окружение не блокируется.
        """
        from core.config import Settings

        # Не должно бросить исключение
        s = Settings(
            ENVIRONMENT="development",
            PII_ENCRYPTION_KEY="",
            JWT_SECRET_KEY="dev-secret-key-change-in-production",
            MINIO_SECRET_KEY="minioadmin123",
        )
        assert s.ENVIRONMENT == "development"

    def test_production_all_secure_succeeds(self):
        """
        Settings(ENVIRONMENT='production') со всеми валидными значениями → OK.
        """
        from core.config import Settings

        s = Settings(
            ENVIRONMENT="production",
            PII_ENCRYPTION_KEY=VALID_FERNET_KEY,
            JWT_SECRET_KEY="valid-jwt-secret-that-is-long-enough-32ch",
            MINIO_SECRET_KEY="secure-minio-password-xyz",
        )
        assert s.ENVIRONMENT == "production"
        assert s.PII_ENCRYPTION_KEY == VALID_FERNET_KEY


# ─── Integration: encrypt in dev, try to decrypt in prod ─────────────────────


class TestEncryptionModeTransition:
    """
    Тесты перехода между режимами.
    Моделируют реальный operational риск: данные зашифрованы в одном режиме,
    читаются в другом.
    """

    def test_plaintext_from_dev_fails_decrypt_in_prod_mode(self):
        """
        Данные записанные в dev (plaintext) нельзя расшифровать как Fernet.
        Это ожидаемое и правильное поведение: при смене ключа старые данные
        требуют миграции.
        """
        dev_enc = PIIEncryptor("")
        prod_enc = PIIEncryptor(VALID_FERNET_KEY)

        plaintext_blob = dev_enc.encrypt_mapping({"TOKEN1": "sensitive"})

        # prod encryptor пытается Fernet.decrypt на plaintext JSON → ошибка
        with pytest.raises(PIIEncryptionError):
            prod_enc.decrypt_mapping(plaintext_blob)

    def test_generate_key_produces_valid_fernet_key(self):
        """
        PIIEncryptor.generate_key() генерирует ключ, который принимает Fernet.
        """
        key = PIIEncryptor.generate_key()
        assert isinstance(key, str)
        assert len(key) > 0
        # Должен инициализироваться без ошибок
        enc = PIIEncryptor(key)
        assert enc.is_encryption_enabled is True

    def test_two_different_generated_keys_are_unique(self):
        """Два вызова generate_key() дают разные ключи."""
        key1 = PIIEncryptor.generate_key()
        key2 = PIIEncryptor.generate_key()
        assert key1 != key2


        
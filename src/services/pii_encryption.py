"""
PII Mapping Encryption via Fernet (symmetric).

Production: PII_ENCRYPTION_KEY генерируется через KMS и прокидывается как env-var.
Dev: если PII_ENCRYPTION_KEY пуст — маппинг хранится в открытом виде.
"""

import json
from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)


class PIIEncryptionError(Exception):
    """Ошибка шифрования/дешифрования PII."""

    pass


class PIIEncryptor:
    """
    Шифрование/дешифрование PII-маппинга.

    Production: Fernet (симметричное шифрование).
    Dev: при пустом ключе хранит в plaintext.
    """

    def __init__(self, encryption_key: str = ""):
        """
        Args:
            encryption_key: Fernet-ключ (32 байта в base64).
                           Пустой = dev-режим (plaintext).
        """
        self._key = encryption_key.strip()
        self._fernet = None

        if self._key:
            self._init_fernet()

    def _init_fernet(self) -> None:
        """Инициализировать Fernet."""
        try:
            from cryptography.fernet import Fernet

            key_bytes = self._key.encode() if isinstance(self._key, str) else self._key
            self._fernet = Fernet(key_bytes)
            logger.debug("PII encryption initialized with Fernet")
        except Exception as e:
            raise PIIEncryptionError(f"Failed to init Fernet: {e}") from e

    @property
    def is_encryption_enabled(self) -> bool:
        """Шифрование включено?"""
        return self._fernet is not None

    def encrypt_mapping(self, mapping: dict) -> bytes:
        """Зашифровать маппинг {TOKEN: original_text}."""
        raw = json.dumps(mapping, ensure_ascii=False).encode("utf-8")

        if self._fernet:
            try:
                return self._fernet.encrypt(raw)
            except Exception as e:
                raise PIIEncryptionError(f"Encryption failed: {e}") from e
        else:
            logger.warning("PII_ENCRYPTION_KEY not set — mapping stored unencrypted (dev only)")
            return raw

    def decrypt_mapping(self, encrypted: bytes) -> dict:
        """Расшифровать маппинг."""
        if self._fernet:
            try:
                raw = self._fernet.decrypt(encrypted)
            except Exception as e:
                raise PIIEncryptionError(f"Decryption failed: {e}") from e
        else:
            raw = encrypted

        return json.loads(raw.decode("utf-8"))

    @staticmethod
    def generate_key() -> str:
        """
        Сгенерировать новый Fernet-ключ.

        Использование:
            python3 -c "from services.pii_encryption import PIIEncryptor; print(PIIEncryptor.generate_key())"
        """
        from cryptography.fernet import Fernet

        return Fernet.generate_key().decode("utf-8")


# ═══════════════════════════════════════════════════════════════════════════════
# Singleton и функции-обёртки
# ═══════════════════════════════════════════════════════════════════════════════

_encryptor_instance: PIIEncryptor | None = None


def get_pii_encryptor(encryption_key: str | None = None) -> PIIEncryptor:
    """
    Получить singleton-экземпляр энкриптора.

    Args:
        encryption_key: Ключ шифрования. None = использовать settings.PII_ENCRYPTION_KEY
    """
    global _encryptor_instance

    if _encryptor_instance is None:
        if encryption_key is None:

            encryption_key = settings.PII_ENCRYPTION_KEY

        _encryptor_instance = PIIEncryptor(encryption_key)

    return _encryptor_instance


def encrypt_mapping(mapping: dict) -> bytes:
    """Зашифровать маппинг."""
    return get_pii_encryptor().encrypt_mapping(mapping)


def decrypt_mapping(encrypted: bytes) -> dict:
    """Расшифровать маппинг."""
    return get_pii_encryptor().decrypt_mapping(encrypted)


def reset_encryptor() -> None:
    """Сбросить singleton (для тестов)."""
    global _encryptor_instance
    _encryptor_instance = None

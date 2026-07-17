# src/services/pii_encryption.py

"""
Шифрование PII‑данных (персонально идентифицируемой информации) с помощью Fernet.

Назначение
---------
Модуль отвечает за шифрование и дешифрование маппингов вида:
    {TOKEN: "исходный текст"}

Режимы работы
-------------
1. Production:
   - Ключ шифрования передаётся через переменную окружения
     settings.PII_ENCRYPTION_KEY.
   - Ключ обязан быть валидным Fernet‑ключом:
     * строка в формате URL‑безопасной base64;
     * при декодировании даёт 32 байта.
   - При любом нарушении этих условий выбрасывается PIIEncryptionError.
   - Маппинги всегда хранятся только в зашифрованном виде.

2. Development:
   - Если settings.PII_ENCRYPTION_KEY пустая строка или None,
     шифрование отключено, и маппинги хранятся в открытом виде (plaintext).
   - В лог пишется предупреждение о незащищённом хранении.

Использование
-------------
- Для генерации корректного Fernet‑ключа (однократно, локально):

    python -c "from services.pii_encryption import PIIEncryptor; print(PIIEncryptor.generate_key())"

- Получить singleton‑экземпляр:

    encryptor = get_pii_encryptor()
    ciphertext = encryptor.encrypt_mapping(mapping)
    original = encryptor.decrypt_mapping(ciphertext)
"""

import base64
import json
from typing import Any

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)


class PIIEncryptionError(Exception):
    """Ошибка инициализации, шифрования или дешифрования PII‑данных."""

    pass


class PIIEncryptor:
    """
    Класс для шифрования и дешифрования PII‑маппинга.

    Production:
        Используется Fernet (симметричное шифрование).
    Development:
        При пустом ключе данные хранятся в открытом виде.
    """

    def __init__(self, encryption_key: str = "") -> None:
        """
        Инициализировать энкриптор.

        Аргументы:
            encryption_key: Строка с Fernet‑ключом.
                - Должна быть URL‑безопасной base64‑строкой, которая
                  декодируется в 32 байта.
                - Пустая строка означает dev‑режим без шифрования.
        """
        self._raw_key: str = (encryption_key or "").strip()
        self._fernet = None

        if self._raw_key:
            self._init_fernet()  # в dev‑режиме (пустой ключ) это не вызывается

    def _validate_key_format(self) -> bytes:
        """
        Проверить, что ключ соответствует требованиям Fernet.

        Возвращает:
            bytes: Декодированное значение ключа (32 байта).

        Бросает:
            PIIEncryptionError: Если ключ некорректен по формату или длине.
        """
        try:
            key_bytes = self._raw_key.encode("utf-8")
            decoded = base64.urlsafe_b64decode(key_bytes)
        except Exception as e:
            # Здесь как раз ловим ошибки вида "Incorrect padding"
            raise PIIEncryptionError(f"PII_ENCRYPTION_KEY имеет неверный формат base64: {e}") from e

        if len(decoded) != 32:
            raise PIIEncryptionError(
                f"PII_ENCRYPTION_KEY должен декодироваться в 32 байта, "
                f"получено {len(decoded)} байт."
            )

        return key_bytes

    def _init_fernet(self) -> None:
        """
        Инициализировать Fernet‑объект.

        Если ключ невалиден, поднимаем PIIEncryptionError, чтобы ошибка
        была заметна сразу при старте, а не во время обработки задач.
        """
        try:
            from cryptography.fernet import Fernet
        except Exception as e:
            raise PIIEncryptionError(f"Не удалось импортировать cryptography.fernet: {e}") from e

        # Дополнительная проверка формата ключа перед созданием Fernet
        key_bytes = self._validate_key_format()

        try:
            self._fernet = Fernet(key_bytes)
            logger.info("PII шифрование инициализировано с использованием Fernet")
        except Exception as e:
            raise PIIEncryptionError(f"Не удалось инициализировать Fernet: {e}") from e

    @property
    def is_encryption_enabled(self) -> bool:
        """Возвращает True, если шифрование включено (production‑режим)."""
        return self._fernet is not None

    def encrypt_mapping(self, mapping: dict[str, Any]) -> bytes:
        raw = json.dumps(mapping, ensure_ascii=False).encode("utf-8")

        if self._fernet:
            try:
                return self._fernet.encrypt(raw)
            except Exception as e:
                raise PIIEncryptionError(f"Ошибка при шифровании PII: {e}") from e
        
        # СИСТЕМНЫЙ ФИКС: Запрет plaintext в продакшене
        if settings.ENVIRONMENT == "production":
            raise PIIEncryptionError(
                "CRITICAL: Attempted to encrypt PII data in production without PII_ENCRYPTION_KEY!"
            )
            
        logger.warning(
            "PII_ENCRYPTION_KEY не задан — PII‑данные сохраняются в открытом виде (DEV MODE)."
        )
        return raw

    def decrypt_mapping(self, encrypted: bytes) -> dict[str, Any]:
        """
        Расшифровать маппинг.

        В dev‑режиме (без ключа) ожидается, что на вход пришёл тот же
        JSON, который был сохранён без шифрования.

        Аргументы:
            encrypted: Зашифрованные данные либо JSON в открытом виде.

        Возвращает:
            dict: Восстановленный PII‑маппинг.
        """
        if self._fernet:
            try:
                raw = self._fernet.decrypt(encrypted)
            except Exception as e:
                raise PIIEncryptionError(f"Ошибка при дешифровании PII: {e}") from e
        else:
            raw = encrypted

        try:
            return json.loads(raw.decode("utf-8"))
        except Exception as e:
            raise PIIEncryptionError(f"Не удалось декодировать/распарсить PII‑маппинг: {e}") from e

    @staticmethod
    def generate_key() -> str:
        """
        Сгенерировать новый корректный Fernet‑ключ.

        Пример использования:
            python -c "from services.pii_encryption import PIIEncryptor; "
                      "print(PIIEncryptor.generate_key())"
        """
        from cryptography.fernet import Fernet

        return Fernet.generate_key().decode("utf-8")


# ═══════════════════════════════════════════════════════════════════════════════
# Singleton и функции‑обёртки
# ═══════════════════════════════════════════════════════════════════════════════

_encryptor_instance: PIIEncryptor | None = None


def get_pii_encryptor(encryption_key: str | None = None) -> PIIEncryptor:
    """
    Получить singleton-экземпляр энкриптора.

    Логика:
        - Если экземпляр ещё не создан:
            * берём переданный encryption_key, если он указан явно;
            * иначе берём settings.PII_ENCRYPTION_KEY.
            * создаём PIIEncryptor.
        - Если экземпляр уже есть, всегда возвращаем его же.

    Production-guard:
        - Если ENVIRONMENT=production и ключ пустой —
          поднимаем PIIEncryptionError немедленно, не создавая encryptor.
        - Это дублирует проверку из config.py _validate_production_secrets,
          но добавляет защиту на случай если config validation была обойдена
          (например, при прямом создании PIIEncryptor в тестах или скриптах).

    Raises:
        PIIEncryptionError: Если ключ пустой в production или невалиден.
    """
    global _encryptor_instance

    if _encryptor_instance is None:
        if encryption_key is None:
            encryption_key = settings.PII_ENCRYPTION_KEY

        resolved_key = (encryption_key or "").strip()

        # Defense-in-depth: второй рубеж после config validator.
        # Срабатывает если: production окружение И ключ пустой.
        # config._validate_production_secrets уже должен был поймать это при
        # старте приложения, но прямые вызовы get_pii_encryptor() в скриптах
        # могут обойти config validation.
        if not resolved_key and settings.ENVIRONMENT == "production":
            raise PIIEncryptionError(
                "PII_ENCRYPTION_KEY is required in production environment. "
                "Generate a key with: python -c \"from services.pii_encryption import "
                "PIIEncryptor; print(PIIEncryptor.generate_key())\""
            )

        _encryptor_instance = PIIEncryptor(resolved_key)

    return _encryptor_instance


def encrypt_mapping(mapping: dict[str, Any]) -> bytes:
    """Функция‑обёртка для шифрования PII‑маппинга через singleton."""
    return get_pii_encryptor().encrypt_mapping(mapping)


def decrypt_mapping(encrypted: bytes) -> dict[str, Any]:
    """Функция‑обёртка для дешифрования PII‑маппинга через singleton."""
    return get_pii_encryptor().decrypt_mapping(encrypted)


def reset_encryptor() -> None:
    """
    Сбросить singleton‑экземпляр (полезно для тестов).

    После вызова следующая операция encrypt/decrypt заново создаст
    PIIEncryptor на основе текущего settings.PII_ENCRYPTION_KEY.
    """
    global _encryptor_instance
    _encryptor_instance = None

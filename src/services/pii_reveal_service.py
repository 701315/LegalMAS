"""
PII Reveal Service.

Назначение:
- Восстановить оригинальный текст из sanitized layout, используя
  зашифрованный PII mapping.

Архитектурные принципы:
- Reveal — строго привилегированная операция.
- Сервис не делает ACL-проверки — это ответственность endpoint/caller.
- Сервис только загружает артефакты, дешифрует mapping и делает
  обратную подстановку токенов в sanitized layout.
- Каждый вызов reveal должен логироваться через AuditRepository.

Важно:
- Reveal не изменяет артефакты в MinIO.
- Reveal не изменяет статус документа.
- Результат не кешируется — каждый запрос читает из MinIO.
"""

from __future__ import annotations

import uuid
from typing import Any

from core.exceptions import PermanentError
from core.logging import get_logger
from services.pii_encryption import PIIEncryptor, get_pii_encryptor
from storage.artifact_store import ArtifactStore

logger = get_logger(__name__)


class PIIRevealError(Exception):
    """Ошибка при раскрытии PII-данных."""
    pass


def _substitute_tokens(
    sanitized_layout: dict[str, Any],
    mapping: dict[str, str],
) -> dict[str, Any]:
    """
    Выполнить обратную подстановку PII-токенов в layout.

    Стратегия:
    - Итерируемся по элементам layout.
    - Для каждого элемента с текстом заменяем все токены на оригинальные значения.
    - Возвращаем новый layout (не мутируем входной).

    Args:
        sanitized_layout: JSON-структура sanitized layout.
        mapping: dict TOKEN → original_value из decrypt_mapping().

    Returns:
        Новый dict с восстановленными текстами элементов.
    """
    if not mapping:
        return sanitized_layout

    elements = sanitized_layout.get("elements", [])
    restored_elements = []

    # Важно: заменяем более длинные токены раньше более коротких,
    # чтобы избежать prefix-collision:
    # PERSONNAME10 не должен частично замениться через PERSONNAME1.
    ordered_mapping = sorted(
        mapping.items(),
        key=lambda kv: len(kv[0]),
        reverse=True,
    )

    for elem in elements:
        text = elem.get("text", "")
        if text and ordered_mapping:
            for token, original in ordered_mapping:
                text = text.replace(token, original)
        restored_elements.append({**elem, "text": text})

    return {**sanitized_layout, "elements": restored_elements}


async def reveal_document_pii(
    *,
    store: ArtifactStore,
    encryptor: PIIEncryptor | None = None,
    sanitized_layout_ref: str,
    pii_mapping_ref: str,
    document_id: uuid.UUID,
) -> dict[str, Any]:
    """
    Восстановить оригинальный layout документа из sanitized версии.

    Args:
        store: ArtifactStore для чтения артефактов.
        encryptor: PIIEncryptor для дешифровки. None = singleton.
        sanitized_layout_ref: S3 URI к sanitized layout.
        pii_mapping_ref: S3 URI к зашифрованному PII mapping.
        document_id: UUID документа (для логирования).

    Returns:
        dict: Восстановленный layout с оригинальными текстами.

    Raises:
        PIIRevealError: Если артефакты недоступны или дешифровка не удалась.
    """
    _encryptor = encryptor or get_pii_encryptor()

    # 1. Загрузить sanitized layout
    try:
        sanitized_layout = store.get_json(sanitized_layout_ref)
    except PermanentError as e:
        raise PIIRevealError(
            f"Sanitized layout not found for document {document_id}: {e}"
        ) from e
    except Exception as e:
        raise PIIRevealError(
            f"Failed to load sanitized layout for document {document_id}: {e}"
        ) from e

    # 2. Загрузить зашифрованный mapping
    try:
        encrypted_mapping = store.get_file(pii_mapping_ref)
    except PermanentError as e:
        raise PIIRevealError(
            f"PII mapping not found for document {document_id}: {e}"
        ) from e
    except Exception as e:
        raise PIIRevealError(
            f"Failed to load PII mapping for document {document_id}: {e}"
        ) from e

    # 3. Дешифровать mapping
    try:
        from services.pii_encryption import PIIEncryptionError
        mapping = _encryptor.decrypt_mapping(encrypted_mapping)
    except PIIEncryptionError as e:
        raise PIIRevealError(
            f"Failed to decrypt PII mapping for document {document_id}: {e}"
        ) from e

    logger.info(
        "PII reveal: mapping loaded",
        document_id=str(document_id),
        tokens_count=len(mapping),
        sanitized_layout_ref=sanitized_layout_ref,
    )

    # 4. Восстановить оригинальные тексты
    restored_layout = _substitute_tokens(sanitized_layout, mapping)

    return restored_layout



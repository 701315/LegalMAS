# src/services/playbooks/line_items.py

"""
Доменный сервис для wiring и валидации PlaybookLineItem.

Назначение:
- централизованно проверять, что instruction_code в line items
  ссылается на реально существующие canonical global instructions;
- извлекать instruction_code из line items в стабильном порядке;
- не допускать, чтобы API-слой или репозиторий silently принимали
  случайные/stale raw strings.

Что НЕ делает:
- не ходит в БД;
- не занимается HTTP/FastAPI;
- не компилирует playbook;
- не хранит состояние.

Используется:
- endpoints/playbooks.py при create/update line;
- endpoints/playbooks.py при create version from_line_id.
"""

from __future__ import annotations

from collections.abc import Iterable

from services.playbooks.catalog import get_unknown_global_check_codes


class PlaybookLineItemValidationError(Exception):
    """
    Ошибка доменной валидации состава PlaybookLineItem.
    """

    def __init__(self, unknown_codes: list[str]):
        self.unknown_codes = unknown_codes
        detail = f"Unknown instruction_code values: {', '.join(unknown_codes)}"
        super().__init__(detail)


def extract_unique_instruction_codes_from_items(items: Iterable[object]) -> list[str]:
    """
    Извлечь instruction_code из line items в исходном порядке, убрав дубликаты.

    Пустые значения игнорируются.
    """
    result: list[str] = []
    seen: set[str] = set()

    for item in items:
        code = getattr(item, "instruction_code", None)
        if code is None:
            continue
        normalized = str(code).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)

    return result


def validate_instruction_codes(codes: Iterable[str]) -> list[str]:
    """
    Провалидировать набор instruction_code против canonical global checks catalog.

    Возвращает нормализованный список кодов, если все коды валидны.
    Иначе бросает PlaybookLineItemValidationError.
    """
    normalized: list[str] = []
    seen: set[str] = set()

    for code in codes:
        if code is None:
            continue
        value = str(code).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)

    unknown_codes = get_unknown_global_check_codes(normalized)
    if unknown_codes:
        raise PlaybookLineItemValidationError(unknown_codes)

    return normalized


def validate_line_item_payloads(items: Iterable[object]) -> list[str]:
    """
    Провалидировать instruction_code в payload/model line items.

    Поддерживает как Pydantic payload objects, так и ORM objects.
    """
    codes = [
        getattr(item, "instruction_code", None)
        for item in items
    ]
    return validate_instruction_codes(codes)


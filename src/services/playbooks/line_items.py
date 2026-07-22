# src/services/playbooks/line_items.py

"""
Доменный сервис для wiring и валидации PlaybookLineItem.

Поддерживает:
- sync file-based validation (legacy/fallback)
- async DB-backed validation (target path)
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from db.repositories.global_instruction_version_repo import (
    GlobalInstructionVersionRepository,
)
from services.playbooks.catalog import get_unknown_global_check_codes


class PlaybookLineItemValidationError(Exception):
    """
    Ошибка доменной валидации состава PlaybookLineItem.
    """

    def __init__(self, unknown_codes: list[str]):
        self.unknown_codes = unknown_codes
        detail = f"Unknown instruction_code values: {', '.join(unknown_codes)}"
        super().__init__(detail)


def _normalize_codes(codes: Iterable[str]) -> list[str]:
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

    return normalized


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
    Sync file-based validation against canonical global checks catalog.
    """
    normalized = _normalize_codes(codes)
    unknown_codes = get_unknown_global_check_codes(normalized)
    if unknown_codes:
        raise PlaybookLineItemValidationError(unknown_codes)
    return normalized


def validate_line_item_payloads(items: Iterable[object]) -> list[str]:
    """
    Sync file-based validation for payload/model line items.
    """
    codes = [
        getattr(item, "instruction_code", None)
        for item in items
    ]
    return validate_instruction_codes(codes)


async def get_unknown_global_check_codes_from_db(
    codes: Iterable[str],
    session: AsyncSession,
) -> list[str]:
    """
    Async DB-backed validation source.

    Fallback:
    - если published global instructions в БД нет → sync file-based fallback.
    """
    normalized = _normalize_codes(codes)
    if not normalized:
        return []

    repo = GlobalInstructionVersionRepository(session)
    versions = await repo.list_all_published_platform()

    if not versions:
        return get_unknown_global_check_codes(normalized)

    known_codes = {
        str(version.instruction_code).strip()
        for version in versions
        if version.instruction_code
    }

    return sorted(code for code in normalized if code not in known_codes)


async def validate_instruction_codes_from_db(
    codes: Iterable[str],
    session: AsyncSession,
) -> list[str]:
    """
    Async DB-backed validation against published platform global instructions.
    """
    normalized = _normalize_codes(codes)
    unknown_codes = await get_unknown_global_check_codes_from_db(normalized, session)
    if unknown_codes:
        raise PlaybookLineItemValidationError(unknown_codes)
    return normalized


async def validate_line_item_payloads_from_db(
    items: Iterable[object],
    session: AsyncSession,
) -> list[str]:
    """
    Async DB-backed validation for payload/model line items.
    """
    codes = [
        getattr(item, "instruction_code", None)
        for item in items
    ]
    return await validate_instruction_codes_from_db(codes, session)





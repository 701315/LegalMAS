# src/core/utils/semver.py

"""
Простые утилиты для работы с семантическими версиями (semver).

Формат версии: MAJOR.MINOR.PATCH, например: "1.2.3".
Функция bump_semver позволяет аккуратно увеличивать одну из частей версии.
"""

from __future__ import annotations

from typing import Literal


def bump_semver(
    version: str,
    part: Literal["major", "minor", "patch"] = "minor",
) -> str:
    """
    Увеличивает часть semver-строки.

    Примеры:
    - bump_semver("1.2.3", "patch") -> "1.2.4"
    - bump_semver("1.2.3", "minor") -> "1.3.0"
    - bump_semver("1.2.3", "major") -> "2.0.0"

    Если строка версии в неожиданном формате, просто возвращает её как есть.
    """
    try:
        major_str, minor_str, patch_str = version.split(".")
        major = int(major_str)
        minor = int(minor_str)
        patch = int(patch_str)
    except Exception:
        # Неизвестный формат — не рискуем, возвращаем исходную строку.
        return version

    if part == "major":
        major += 1
        minor = 0
        patch = 0
    elif part == "minor":
        minor += 1
        patch = 0
    else:  # "patch"
        patch += 1

    return f"{major}.{minor}.{patch}"

# src/services/structure/_heading_scoring/_utils.py

"""Утилиты нормализации и проверки предикатов заголовка."""

from __future__ import annotations
import re
from typing import Any
from services.structure.heading_patterns import normalize_spaces

_NUMERIC_UID_RE = re.compile(r"^\d+(?:\.\d+)*$")

def _is_strict_numeric_uid(uid: str | None) -> bool:
    if not uid: return False
    return bool(_NUMERIC_UID_RE.fullmatch(uid.strip()))

def level_from_uid(uid: str) -> int:
    normalized = normalize_spaces(uid)
    if not _is_strict_numeric_uid(normalized):
        return 1
    return normalized.count(".") + 1

def _is_effectively_empty_title(title: str) -> bool:
    if not title: return True
    stripped = normalize_spaces(title).strip()
    if not stripped: return True
    cleaned = re.sub(r"[\s\.,;:!?()\[\]{}\-–—_+/\\|\"'`~№]+", "", stripped)
    return not cleaned

def _looks_too_long_for_heading(title: str, *, level: int) -> bool:
    normalized = normalize_spaces(title)
    word_count = len(normalized.split())
    if level <= 1: return len(normalized) > 220 or word_count > 22
    if level == 2: return len(normalized) > 180 or word_count > 18
    return len(normalized) > 150 or word_count > 16

def _normalize_element_type(element_type: str | None) -> str:
    return normalize_spaces(str(element_type or "")).lower()

def _clamp_score(value: float) -> float:
    return max(0.0, min(1.0, float(value)))

def _is_recoverable_toc_like_element_type(element_type: str | None) -> bool:
    return _normalize_element_type(element_type) == "toc_false_positive"

def _is_strong_heading_element_type(element_type: str | None) -> bool:
    return _normalize_element_type(element_type) in {
        "heading_candidate", "section_heading", "subsection_heading", "appendix_heading"
    }


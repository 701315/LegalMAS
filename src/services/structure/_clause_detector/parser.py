# src/services/structure/_clause_detector/parser.py

"""
Парсер ответа LLM -> список пунктов.

Архитектурные принципы:
- LLM является единственным источником сложной семантической разметки (буквы, римские цифры, списки).
- Парсер валидирует JSON-ответ LLM, устойчив к markdown-обёрткам.
- Fallback строго консервативен: извлекает ТОЛЬКО однозначную цифровую иерархию (1.1, 2.1.3),
  чтобы исключить ложные срабатывания на предлогах и словах любых языков мира.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class DetectedClause:
    """Один пункт, обнаруженный LLM или Fallback."""
    uid: str
    title: str
    quote_start: str
    quote_end: str


def _extract_single_json_object(text: str) -> dict[str, Any]:
    """Извлечь JSON-объект из любого места ответа (устойчиво к markdown)."""
    if not text:
        raise ValueError("Empty LLM response")

    stripped = text.strip()
    start_idx = stripped.find("{")
    end_idx = stripped.rfind("}")

    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        raise ValueError("No JSON object found in LLM response")

    candidate = stripped[start_idx : end_idx + 1].strip()

    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e


def parse_llm_response(
    raw_response: str,
    chapter_number: str,
) -> list[DetectedClause]:
    """
    Разобрать структурированный JSON от LLM.
    Принимает ЛЮБУЮ нумерацию (буквенную, цифровую, римскую), извлеченную моделью.
    """
    clauses: list[DetectedClause] = []
    seen: set[str] = set()

    try:
        obj = _extract_single_json_object(raw_response)
        if not isinstance(obj, dict) or "clauses" not in obj:
            return []

        items = obj.get("clauses")
        if not isinstance(items, list):
            return []

        for item in items:
            if not isinstance(item, dict):
                continue

            uid = str(item.get("uid", "")).strip()
            title = str(item.get("title", "")).strip()
            qs = str(item.get("quote_start", "")).strip()
            qe = str(item.get("quote_end", "")).strip()

            # Валидация контракта
            if not uid or not title or (not qs and not qe):
                continue

            if uid in seen:
                continue

            seen.add(uid)
            clauses.append(DetectedClause(uid=uid, title=title, quote_start=qs, quote_end=qe))

    except Exception as e:
        logger.warning(
            "CLAUSE_DETECTOR parse failed",
            extra={"chapter": chapter_number, "error": str(e)},
        )
        return []

    return clauses


# ---------------------------------------------------------------------------
# Конфигурируемые пороги (читаются из settings, имеют безопасные дефолты).
# Не привязаны к конкретному языку или формату документа.
# ---------------------------------------------------------------------------
_MIN_CLAUSE_TITLE_LEN: int = int(
    getattr(settings, "CLAUSE_DETECTOR_MIN_TITLE_LEN", 2)
)
_MIN_LINE_LEN: int = int(
    getattr(settings, "CLAUSE_DETECTOR_MIN_LINE_LEN", 4)
)

# Композитный паттерн числового маркера: 1.1, 2.1.3, 10.4.1, и т.д.
# Выделен в именованную константу для переиспользования и читаемости.
_NUMERIC_MARKER = r'\d+\.\d+(?:\.\d+)*\.?'

# Основная регулярка: маркер + пробел + заголовок (минимальная длина конфигурируема).
# Флаг re.UNICODE обеспечивает корректную работу с любым языком.
_NUMERIC_CLAUSE_RE = re.compile(
    rf'^\s*({_NUMERIC_MARKER})\s+(.{{{_MIN_CLAUSE_TITLE_LEN},}})',
    re.UNICODE,
)

# Табличная регулярка: | маркер | заголовок |
# Исправлен квантор: было .{5,?} (некорректный ленивый), стало .{N,} (жадный).
_TABLE_ROW_NUMERIC_RE = re.compile(
    rf'^\|\s*({_NUMERIC_MARKER})\s*\|\s*(.{{{_MIN_CLAUSE_TITLE_LEN},}}?)\s*\|',
    re.UNICODE,
)


def _looks_like_valid_clause_title(title: str) -> bool:
    """
    Семантическая проверка заголовка пункта.
    Устойчива к языку: проверяет наличие хотя бы одной буквы/цифры (UNICODE),
    а не абсолютную длину или алфавит.
    """
    stripped = title.strip()
    if len(stripped) < _MIN_CLAUSE_TITLE_LEN:
        return False
    return bool(re.search(r'\w', stripped, re.UNICODE))


def extract_clauses_fallback(chapter_text: str, chapter_number: str) -> list[DetectedClause]:
    """
    Консервативный fallback без LLM.
    Извлекает только строгие числовые маркеры (1.1, 2.1.3 и т.д.).

    Универсален: не привязан к языку, пороги конфигурируемы через settings.
    Валидация заголовка — через семантический предикат, а не через жёсткую длину.
    """
    clauses: list[DetectedClause] = []
    seen: set[str] = set()

    for line in chapter_text.split('\n'):
        line = line.strip()
        if not line or len(line) < _MIN_LINE_LEN:
            continue

        uid: str | None = None
        title: str | None = None
        clean_line = line

        # 1. Проверка строки таблицы с числовым маркером: | 2.8 | Текст |
        table_match = _TABLE_ROW_NUMERIC_RE.match(line)
        if table_match:
            uid = table_match.group(1).strip().rstrip('.')
            title = table_match.group(2).strip()[:100]
            clean_line = f"{uid} {title}"

        # 2. Проверка обычной строки с числовым маркером: 2.8 Текст
        if not uid:
            num_match = _NUMERIC_CLAUSE_RE.match(line)
            if num_match:
                uid = num_match.group(1).strip().rstrip('.')
                title = num_match.group(2).strip()[:100]

        # 3. Семантическая валидация (устойчива к языку и формату)
        if uid and title and uid not in seen and _looks_like_valid_clause_title(title):
            seen.add(uid)
            clauses.append(DetectedClause(
                uid=uid,
                title=title,
                quote_start=clean_line[:50],
                quote_end=clean_line[-50:] if len(clean_line) > 50 else clean_line,
            ))

    return clauses

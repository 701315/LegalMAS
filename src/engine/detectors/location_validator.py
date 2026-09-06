# src/engine/detectors/location_validator.py

"""
Validation and normalization helpers for per-field extraction locations.

This module converts raw LLM location payloads into normalized LocationInfo
objects and produces honest fallback metadata when the location cannot be
trusted against the extraction context.

V1.3b — Numeric-core matching:
LLM возвращает clause_ref в человеческой форме ("п. 22", "Section 12.1",
"п. 7.1.1, п. 7.1.2"), а в тексте договора та же ссылка может выглядеть
как "Пункт 22", "22 ПРИМЕНИМОЕ ПРАВО", "Section 12.1" и т.д.

Наивный substring-match отклоняет корректные ссылки из-за префиксных
и regexp-агностических различий. Решение:
- нормализуем и LLM ссылку, и context к numeric-core форме;
- поддерживаем compound references ("п. 7.1.1, п. 7.1.2");
- защищаем от word-boundary false positives ("п. 7" не должно матчиться в "п. 7.1");
- сохраняем исходную строку clause_ref для UI.

Universal rules:
- clause_ref валиден, если хотя бы один его numeric-core находится в
  context_text как самостоятельный numeric token (word-boundary safe);
- page валиден, если это int и он присутствует в context_pages;
- оба валидны   -> high confidence
- один валиден  -> low confidence
- ни один       -> no location, fallback returned
"""

from __future__ import annotations

import re
from typing import Any

from core.logging import get_logger
from engine.playbook.models import LocationFallback, LocationInfo

logger = get_logger(__name__)


# ─── Prefix lexicon (RU + EN + universal §) ──────────────────────────────────
#
# Порядок важен: сначала более длинные формы, потом короткие,
# чтобы "пункт" не был обрезан до "п" ещё до удаления "пункт".
# Разделены на группы для читаемости, но склеиваются в один regex.
_CLAUSE_PREFIXES: tuple[str, ...] = (
    # RU: длинные словоформы сначала
    "подпункт",
    "подпункта",
    "подпункте",
    "подпунктом",
    "пункта",
    "пункте",
    "пунктом",
    "пункт",
    "статья",
    "статьи",
    "статье",
    "статьей",
    "часть",
    "части",
    "частью",
    "раздел",
    "раздела",
    "разделе",
    "разделом",
    # RU: короткие аббревиатуры
    "подп.",
    "пп.",
    "п.",
    "ст.",
    "ч.",
    "р.",
    # EN: длинные словоформы
    "sections",
    "section",
    "clauses",
    "clause",
    "articles",
    "article",
    "paragraphs",
    "paragraph",
    # EN: короткие аббревиатуры
    "sec.",
    "cl.",
    "art.",
    "para.",
    # Universal
    "§",
    "№",
    "no.",
)

# Regex для удаления одного префикса в начале строки.
# Учитывает возможные пробелы между префиксом и числом.
# re.IGNORECASE + re.UNICODE применяются при компиляции.
_PREFIX_REGEX = re.compile(
    r"^\s*(?:" + "|".join(re.escape(p) for p in _CLAUSE_PREFIXES) + r")\s*",
    flags=re.IGNORECASE | re.UNICODE,
)

# Compound reference разделители.
# Порядок не важен, все — на одном уровне.
# " и ", " and ", " или ", " or " — только с word boundary,
# чтобы не резать слова типа "или" внутри других слов.
_COMPOUND_SPLIT_REGEX = re.compile(
    r"\s*(?:,|;|/|\bи\b|\band\b|\bили\b|\bor\b)\s*",
    flags=re.IGNORECASE | re.UNICODE,
)

# Numeric-core паттерн: "22", "7.1", "7.1.2", "12.1(а)", "5(b)(iii)".
# Требует хотя бы одной цифры, может содержать точки и скобочные суффиксы.
_NUMERIC_CORE_REGEX = re.compile(
    r"^\d+(?:\.\d+)*(?:\([\w\d]+\))*\.?$",
    flags=re.UNICODE,
)


def _normalize_whitespace(value: str) -> str:
    """Нормализовать пробелы: NBSP -> обычный, схлопнуть множественные."""
    return " ".join(value.replace("\u00a0", " ").split())


def _extract_numeric_cores(ref: Any) -> list[str]:
    """
    Извлечь список numeric cores из clause reference строки.

    Правила:
    1. Нормализация whitespace (NBSP, множественные пробелы).
    2. Split по compound-разделителям (запятая, "и", "and" и т.д.).
    3. Для каждого sub-ref удалить leading префикс ("п.", "Пункт", "Section" и т.д.).
    4. Удалить trailing точку.
    5. Проверить, что осталось валидное numeric-core значение.

    Примеры:
        "п. 22"                 -> ["22"]
        "Пункт 22"              -> ["22"]
        "22"                    -> ["22"]
        "п. 7.1.1, п. 7.1.2"    -> ["7.1.1", "7.1.2"]
        "Sections 3 and 5"      -> ["3", "5"]
        "п.\u00a05"             -> ["5"]
        "п. 12.1(а)"            -> ["12.1(а)"]
        "§ 12.1"                -> ["12.1"]
        ""                      -> []
        None                    -> []
        "abc"                   -> []
    """
    if not isinstance(ref, str):
        return []

    normalized = _normalize_whitespace(ref)
    if not normalized:
        return []

    cores: list[str] = []
    seen: set[str] = set()

    for part in _COMPOUND_SPLIT_REGEX.split(normalized):
        candidate = part.strip()
        if not candidate:
            continue

        # Итеративно снимаем префиксы (может быть несколько: "п. п. 5" - edge case)
        prev = None
        while candidate != prev:
            prev = candidate
            candidate = _PREFIX_REGEX.sub("", candidate).strip()

        # Убираем trailing точку
        candidate = candidate.rstrip(".")
        if not candidate:
            continue

        if _NUMERIC_CORE_REGEX.match(candidate):
            if candidate not in seen:
                seen.add(candidate)
                cores.append(candidate)

    return cores


def _find_numeric_core_in_text(core: str, context_text: str) -> bool:
    """
    Проверить, встречается ли numeric core в context_text
    как самостоятельный numeric token.

    Word-boundary protection:

    Что не должно матчиться (false positive защита):
    - "7"  не матчится в "7.1"      (core "7" — префикс более длинного номера)
    - "7"  не матчится в "7.10"     (аналогично)
    - "22" не матчится в "223"      (цифра сразу после)
    - "22" не матчится в "122"      (цифра сразу перед)
    - "7.1" не матчится в "7.1.2"   (точка+цифра после)

    Что должно матчиться (реальные legal citations):
    - "3"  матчится в "3. Payment"   (точка+пробел или конец = конец legal ref)
    - "22" матчится в "Пункт 22"     (пробел вокруг)
    - "22" матчится в "п. 22 текст" (точка перед — от префикса, не от числа)

    Универсальное правило:
    - перед core:  нет цифры и нет точки-цифры  (защита "7.1" от "7", "122" от "22")
    - после core:  нет цифры и нет точки-цифры  (защита "223" от "22", "7.1" от "7")

    Точка+не-цифра после core (например "3.", "3. Payment") — разрешена,
    т.к. это legitimate конец legal citation.

    Точки внутри самого core экранируются через re.escape.
    """
    if not core or not context_text:
        return False

    escaped_core = re.escape(core)
    pattern = re.compile(
        r"(?<![\d.])" + escaped_core + r"(?!\d)(?!\.\d)",
        flags=re.UNICODE,
    )
    return bool(pattern.search(context_text))


def _normalize_clause_ref_display(value: Any) -> str | None:
    """
    Нормализовать LLM clause_ref для сохранения в LocationInfo.clause_ref.

    Сохраняем исходную человеческую форму, только чистим whitespace.
    Юрист увидит "п. 22", как написал LLM, а не голое "22".
    """
    if not isinstance(value, str):
        return None
    cleaned = _normalize_whitespace(value)
    return cleaned or None


def _normalize_page(value: Any) -> int | None:
    """
    Normalize page to int.

    V1 rule:
    - only real int is accepted;
    - string pages like "7" are treated as unreliable and become None.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    return None


def validate_location(
    location: dict | None,
    context_text: str,
    context_pages: list[int],
) -> tuple[LocationInfo | None, LocationFallback | None]:
    """
    Validate raw location payload against extraction context.

    Args:
        location:
            Raw LLM location, expected as:
            {"clause_ref": "...", "page": 7}
            or None.
        context_text:
            Text passed to extraction LLM.
        context_pages:
            Pages covered by the extraction context.

    Returns:
        (LocationInfo | None, LocationFallback | None)

    Rules:
    - clause_ref numeric-core match in context_text + page in context_pages -> high
    - only one of them validated -> low
    - neither validated -> no exact location, fallback
    """
    normalized_pages = sorted(
        {
            int(p)
            for p in (context_pages or [])
            if isinstance(p, int) and not isinstance(p, bool) and p > 0
        }
    )

    if not isinstance(location, dict):
        logger.debug(
            "validate_location: raw location missing or not a dict",
            has_location=location is not None,
            location_type=type(location).__name__ if location is not None else None,
        )
        return (
            None,
            LocationFallback(reason="Exact location in the document is not defined"),
        )

    clause_ref_display = _normalize_clause_ref_display(location.get("clause_ref"))
    page = _normalize_page(location.get("page"))

    if clause_ref_display is None and page is None:
        logger.debug(
            "validate_location: both clause_ref and page are absent after normalization"
        )
        return (
            None,
            LocationFallback(reason="Exact location in the document is not defined"),
        )

    # Numeric-core matching для clause_ref
    clause_ref_ok = False
    matched_core: str | None = None
    if clause_ref_display is not None:
        cores = _extract_numeric_cores(clause_ref_display)
        for core in cores:
            if _find_numeric_core_in_text(core, context_text or ""):
                clause_ref_ok = True
                matched_core = core
                break

        if not clause_ref_ok and not cores:
            logger.debug(
                "validate_location: no numeric cores extracted from clause_ref",
                clause_ref=clause_ref_display,
            )

    page_ok = False
    if page is not None:
        page_ok = page in normalized_pages

    if clause_ref_ok and page_ok:
        logger.debug(
            "validate_location: location validated with high confidence",
            clause_ref=clause_ref_display,
            matched_core=matched_core,
            page=page,
        )
        return (
            LocationInfo(
                clause_ref=clause_ref_display,
                page=page,
                clause_uid=None,
                location_confidence="high",
            ),
            None,
        )

    if clause_ref_ok or page_ok:
        logger.debug(
            "validate_location: location validated with low confidence",
            clause_ref=clause_ref_display,
            matched_core=matched_core,
            page=page,
            clause_ref_ok=clause_ref_ok,
            page_ok=page_ok,
        )
        return (
            LocationInfo(
                clause_ref=clause_ref_display,
                page=page,
                clause_uid=None,
                location_confidence="low",
            ),
            None,
        )

    logger.debug(
        "validate_location: location rejected by context validation",
        clause_ref=clause_ref_display,
        page=page,
        context_pages=normalized_pages,
    )
    return (
        None,
        LocationFallback(reason="Exact location in the document is not defined"),
    )



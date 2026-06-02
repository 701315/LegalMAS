# src/services/structure/_segmenter/patterns.py

"""
Regex-семейства и pattern-based helpers сегментации.

Содержит:
- sub-patterns для построения составных regex;
- скомпилированные regex appendix / amendment / act / invoice / protocol;
- helpers: match, infer type, extract appendix number.
"""

from __future__ import annotations

import re

from services.structure.heading_patterns import normalize_spaces
from services.structure.models import (
    SEGMENT_TYPE_ACT,
    SEGMENT_TYPE_AMENDMENT,
    SEGMENT_TYPE_APPENDIX,
    SEGMENT_TYPE_INVOICE,
    SEGMENT_TYPE_PROTOCOL,
    SEGMENT_TYPE_UNKNOWN,
)

# ── Shared sub-patterns ──────────────────────────────────────────────────────

_SEGMENT_ID_CHARS = r"[A-Za-zА-ЯЁа-яё0-9.\-]+"
"""Символы, допустимые в идентификаторе документа (amendment / addendum)."""

_APPENDIX_DOC_ID_RE = r"(?:\d+(?:\.\d+)*|[A-Za-zА-ЯЁа-яё]|[IVXLCM]{1,12})"
"""Узкий идентификатор приложения: число, буква, римская цифра."""

# Важно: длинная альтернатива «no» идёт ПЕРЕД короткой «n»,
# иначе «No. 5» матчится как marker=n + num=o.
_NUMBER_MARKER_RE = r"(?:№|no\.?|n)\s*"
"""Маркер номера: №, No., No, n."""

_RU_APPENDIX_KEYWORD_RE = r"прилож[еe]ни(?:[еe]|я|й)"
"""Русское ключевое слово «приложение» с OCR-толерантностью к e/е."""

_EN_APPENDIX_KEYWORD_RE = (
    r"(?:appendix|appendices|schedule|exhibit|annex|annexure|attachment)"
)
"""Английские ключевые слова appendix-семейства."""

_TRAILING_TITLE_RE = r"(?:\s*[:\-–—]\s*.+|\s+[A-Za-zА-ЯЁа-яёЁё].*)?"
"""Опциональный trailing title после номера приложения."""

# ── Compiled regexes ─────────────────────────────────────────────────────────

APPENDIX_RE = re.compile(
    rf"""
    ^
    (?:
        {_EN_APPENDIX_KEYWORD_RE}
        (?:
            \s*
            (?:no\.?\s*)?
            \s*
            {_APPENDIX_DOC_ID_RE}
        )?
        {_TRAILING_TITLE_RE}
    |
        disclosure\s+schedule
        (?:
            \s*
            (?:no\.?\s*)?
            \s*
            {_APPENDIX_DOC_ID_RE}
        )?
        {_TRAILING_TITLE_RE}
    |
        {_RU_APPENDIX_KEYWORD_RE}
        \s*
        (?:{_NUMBER_MARKER_RE})?
        \s*
        {_APPENDIX_DOC_ID_RE}
        {_TRAILING_TITLE_RE}
    |
        {_RU_APPENDIX_KEYWORD_RE}
        \s*$
    )
    $
    """,
    re.IGNORECASE | re.VERBOSE,
)

AMENDMENT_RE = re.compile(
    rf"""
    ^
    (?:
        (?:addendum|amendment)
        \s*
        (?:(?:no\.?\s*)?{_SEGMENT_ID_CHARS})?
        {_TRAILING_TITLE_RE}
    |
        supplemental\s+agreement
        {_TRAILING_TITLE_RE}
    |
        дополнительно[еe]\s+соглашени[еe]
        \s*
        (?:{_NUMBER_MARKER_RE})?
        \s*
        (?:{_SEGMENT_ID_CHARS})?
        {_TRAILING_TITLE_RE}
    |
        дополн[еe]ни[еe]
        \s*
        (?:{_NUMBER_MARKER_RE})?
        \s*
        (?:{_SEGMENT_ID_CHARS})?
        {_TRAILING_TITLE_RE}
    )
    $
    """,
    re.IGNORECASE | re.VERBOSE,
)

ACT_RE = re.compile(
    r"^(?:передаточный\s+акт|акт\s+(?:приема|приёма|сдачи|выполненных\s+работ|оказанных\s+услуг)|acceptance\s+act|delivery\s+act)(?:\s*[:\-–—]\s*.*)?$",
    re.IGNORECASE,
)

INVOICE_RE = re.compile(
    r"^(?:(?:сч[еёe]т|сч[еёe]т)\s*(?:на\s+оплату)?|invoice\b)(?:\s*[:\-–—]\s*.*)?$",
    re.IGNORECASE,
)

PROTOCOL_RE = re.compile(
    r"^(?:protocol|протокол)\b(?:\s*[:\-–—]\s*.*)?$",
    re.IGNORECASE,
)

HORIZONTAL_RULE_RE = re.compile(r"^\s*-{3,}\s*$")

SIGNATURE_LINE_RE = re.compile(
    r"^(?:подпись|signature|м\.п\.|место\s+печати|генеральный\s+директор|директор|по[дд]писи\s+сторон)\b",
    re.IGNORECASE,
)

REQUISITES_LINE_RE = re.compile(
    r"^(?:реквизиты|адреса\s+и\s+реквизиты|юридический\s+адрес|инн|кпп|огрн|расчетный\s+счет|р/с|к/с|банк|бик)\b",
    re.IGNORECASE,
)

APPENDIX_NUMBER_RE = re.compile(
    rf"""
    (?:
        appendix|appendices|schedule|exhibit|annex|annexure|attachment
        |disclosure\s+schedule
        |{_RU_APPENDIX_KEYWORD_RE}
    )
    \s*
    (?:
        {_NUMBER_MARKER_RE}
    )?
    \s*
    (?P<num>{_APPENDIX_DOC_ID_RE})
    """,
    re.IGNORECASE | re.VERBOSE,
)


# ── Pattern helpers ──────────────────────────────────────────────────────────

def match_boundary_marker(text: str) -> str | None:
    """Возвращает тип маркера границы или None."""
    if APPENDIX_RE.match(text):
        return "appendix"
    if AMENDMENT_RE.match(text):
        return "amendment"
    if ACT_RE.match(text):
        return "act"
    if INVOICE_RE.match(text):
        return "invoice"
    if PROTOCOL_RE.match(text):
        return "protocol"
    return None


def infer_segment_type_from_text(text: str) -> str:
    """Определяет тип сегмента по тексту маркера."""
    if APPENDIX_RE.match(text):
        return SEGMENT_TYPE_APPENDIX
    if AMENDMENT_RE.match(text):
        return SEGMENT_TYPE_AMENDMENT
    if ACT_RE.match(text):
        return SEGMENT_TYPE_ACT
    if INVOICE_RE.match(text):
        return SEGMENT_TYPE_INVOICE
    if PROTOCOL_RE.match(text):
        return SEGMENT_TYPE_PROTOCOL
    return SEGMENT_TYPE_UNKNOWN


def infer_segment_title(text: str) -> str | None:
    """Извлекает заголовок сегмента из текста маркера."""
    title = normalize_spaces(text)
    return title or None


def extract_appendix_number(text: str) -> str | None:
    """Извлекает номер приложения из текста.

    Возвращает нормализованную строку номера или None.
    """
    normalized = normalize_spaces(text)
    if not normalized:
        return None
    m = APPENDIX_NUMBER_RE.search(normalized)
    if not m:
        return None
    value = normalize_spaces(str(m.group("num") or ""))
    return value or None


def looks_like_appendix_boundary_marker(text: str) -> bool:
    """Предикат для suppression layer: текст похож на appendix boundary.

    Переиспользует ту же appendix-grammar, что и основной boundary detector,
    чтобы избежать расхождений между «что подавляем» и «что принимаем».
    """
    return infer_segment_type_from_text(text) == SEGMENT_TYPE_APPENDIX


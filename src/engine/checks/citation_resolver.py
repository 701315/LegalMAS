"""
B2 Citation Resolver — deterministic quote-to-span resolution.

Назначение:
- Получить от детектора цитату (`quote`) и текст клаузы (`source_text`).
- Найти точное место цитаты в тексте (span_start/span_end в ОРИГИНАЛЕ).
- Привязать span к layout elements (element_ids).
- Вернуть `CheckAnchor` из B1a.

Не путать с `src/engine/content/citation_resolver.py`:
- тот резолвер — topic-to-clause (знает клаузу, не знает цитату);
- этот — quote-to-span (знает цитату, не знает точной позиции).
- Оба нужны, не дублируют друг друга (см. B3 wiring).

Ступени (по плану):
1. exact_span  — цитата найдена дословно после нормализации   (confidence=1.0)
2. fuzzy_span  — token-level LCS ratio >= 0.75                (confidence = ratio)
3. clause_only — цитата не найдена, но есть fallback_clause_uid (confidence=0.5)
4. page_only   — только fallback_page                         (confidence=0.3)
5. none        — нет ни цитаты, ни fallback                   (confidence=0.0)

Контракт:
- Pure function, без I/O, без БД, без LLM.
- Никогда не бросает исключение на «плохих» входных данных — возвращает NONE.
- Никогда не мутирует входные dicts.
- Span всегда в координатах ОРИГИНАЛЬНОГО source_text (не нормализованного).
"""

from __future__ import annotations

import hashlib
from typing import Any

from core.anchors.models import CheckAnchor, CheckAnchorMethod
from core.logging import get_logger
from engine.checks.citation_normalization import (
    normalize_text,
    normalize_with_index_map,
)

logger = get_logger(__name__)


# Минимальная длина цитаты, ниже которой поиск превращается в шум.
# План задаёт порог 20; на практике 8 даёт стабильный fuzzy ratio
# на коротких клаузах, при этом отсекает однословные выбросы.
_MIN_QUOTE_LEN = 8

# Порог fuzzy token-level LCS ratio (см. план B2).
_FUZZY_MIN_RATIO = 0.75

# При каком ratio fuzzy-совпадение считается "валидированным" (round-trip).
# Exact всегда проходит; fuzzy с 0.85+ тоже считаем достаточно близким.
_FUZZY_VALIDATED_RATIO = 0.85

# Разделитель между элементами при materialize_text_from_element_ids
# (см. clause_tree_builder.ClauseTreeBuilder.materialize_text_from_element_ids).
_ELEMENT_SEPARATOR = "\n\n"


# ---------------------------------------------------------------------------
# Внутренние helpers
# ---------------------------------------------------------------------------


def _compute_content_hash(source_text: str) -> str:
    """SHA-256 hex от source_text (UTF-8). 64 lowercase hex."""
    return hashlib.sha256(source_text.encode("utf-8")).hexdigest()


def _normalized_span_to_original(
    norm_start: int,
    norm_end: int,
    idx_map: list[int],
) -> tuple[int, int] | None:
    """
    Перевести span из нормализованного текста в координаты оригинала.

    idx_map[i] — индекс начала i-го символа нормализованного текста
    в оригинале. Гарантия: len(idx_map) == len(normalized) (B2a).

    Возвращает (orig_start, orig_end) или None при выходе за границы.
    """
    if norm_start < 0 or norm_end <= norm_start or norm_end > len(idx_map):
        return None
    orig_start = idx_map[norm_start]
    orig_end = idx_map[norm_end - 1] + 1
    return orig_start, orig_end


def _exact_span(
    quote: str,
    source_text: str,
) -> tuple[int, int] | None:
    """
    Дословный поиск после нормализации.

    Возвращает span в ОРИГИНАЛЕ или None.
    """
    norm_quote = normalize_text(quote)
    if len(norm_quote) < _MIN_QUOTE_LEN:
        return None

    norm_source, idx_map = normalize_with_index_map(source_text)
    if not norm_source:
        return None

    pos = norm_source.find(norm_quote)
    if pos < 0:
        return None

    return _normalized_span_to_original(
        pos, pos + len(norm_quote), idx_map
    )


def _token_lcs_ratio(a: list[str], b: list[str]) -> float:
    """
    Доля LCS между двумя токен-списками: len(LCS) / max(len(a), len(b)).

    Классический DP LCS. O(len(a) * len(b)).
    """
    if not a or not b:
        return 0.0

    n, m = len(a), len(b)
    # Плоский DP: dp[i][j] = LCS(a[:i], b[:j])
    prev = [0] * (m + 1)
    curr = [0] * (m + 1)

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if a[i - 1] == b[j - 1]:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = prev[j] if prev[j] >= curr[j - 1] else curr[j - 1]
        prev, curr = curr, [0] * (m + 1)

    lcs_len = prev[m]
    return lcs_len / max(n, m)


def _tokenize_with_offsets(
    normalized: str,
) -> list[tuple[str, int, int]]:
    """
    Разбить нормализованный текст на токены с char-офсетами.

    Токен = непрерывная последовательность не-whitespace символов.
    Возвращает [(token, char_start, char_end), ...] в координатах normalized.
    """
    tokens: list[tuple[str, int, int]] = []
    i = 0
    n = len(normalized)
    while i < n:
        while i < n and normalized[i].isspace():
            i += 1
        if i >= n:
            break
        start = i
        while i < n and not normalized[i].isspace():
            i += 1
        tokens.append((normalized[start:i], start, i))
    return tokens


def _fuzzy_span(
    quote: str,
    source_text: str,
) -> tuple[int, int, float] | None:
    """
    Fuzzy поиск через token-level LCS.

    Ищем окно в source-токенах ровно длины len(quote_tokens),
    максимизируя LCS ratio. Возвращаем (orig_start, orig_end, ratio).

    Возвращает None, если лучший ratio < _FUZZY_MIN_RATIO.
    """
    norm_quote = normalize_text(quote)
    quote_tokens = norm_quote.split()
    if len(quote_tokens) < 3:
        return None

    norm_source, idx_map = normalize_with_index_map(source_text)
    if not norm_source:
        return None

    source_tokens = _tokenize_with_offsets(norm_source)
    m = len(quote_tokens)
    n = len(source_tokens)
    if n < m:
        return None

    best_ratio = 0.0
    best_window: int | None = None

    for i in range(n - m + 1):
        window = [t[0] for t in source_tokens[i : i + m]]
        ratio = _token_lcs_ratio(quote_tokens, window)
        if ratio > best_ratio:
            best_ratio = ratio
            best_window = i

    if best_ratio < _FUZZY_MIN_RATIO or best_window is None:
        return None

    first = source_tokens[best_window]
    last = source_tokens[best_window + m - 1]

    span = _normalized_span_to_original(first[1], last[2], idx_map)
    if span is None:
        return None

    orig_start, orig_end = span
    return orig_start, orig_end, best_ratio


def _compute_element_offsets(
    layout_elements: list[dict[str, Any]],
    source_text: str,
) -> tuple[list[tuple[str, int, int]], bool]:
    """
    Воспроизвести логику materialize_text_from_element_ids и вернуть
    offsets каждого элемента в source_text.

    Возвращает:
    - [(element_id, start, end), ...] для непустых элементов;
    - bool: True если суммарный offset совпал с len(source_text)
      (layout_elements согласованы с source_text).

    Расхождение offset — не ошибка, а сигнал, что caller передал
    layout_elements не из этой клаузы. Тогда element_ids лучше не
    возвращать (см. resolve_quote_in_source).
    """
    sorted_els = sorted(
        [el for el in layout_elements if el.get("element_id")],
        key=lambda el: int(el.get("_seq", 0)),
    )

    pieces: list[tuple[str, str | None]] = []
    last_page: int | None = None

    for el in sorted_els:
        text = (el.get("text") or "").strip()
        page = el.get("page")

        if not text:
            if isinstance(page, int):
                last_page = page
            continue

        if (
            last_page is not None
            and isinstance(page, int)
            and page != last_page
        ):
            pieces.append(("", None))

        pieces.append((text, str(el["element_id"])))
        last_page = page if isinstance(page, int) else last_page

    if not pieces:
        return [], len(source_text) == 0

    offsets: list[tuple[str, int, int]] = []
    offset = 0
    for i, (text, el_id) in enumerate(pieces):
        if i > 0:
            offset += len(_ELEMENT_SEPARATOR)
        start = offset
        offset += len(text)
        end = offset
        if el_id is not None:
            offsets.append((el_id, start, end))

    return offsets, offset == len(source_text)


def _span_to_element_ids(
    span_start: int,
    span_end: int,
    element_offsets: list[tuple[str, int, int]],
) -> list[str]:
    """
    Найти element_ids, чьи [start, end) пересекаются со span.

    Span в координатах source_text; offsets тоже в source_text.
    """
    result: list[str] = []
    for el_id, el_start, el_end in element_offsets:
        if el_end > span_start and el_start < span_end:
            result.append(el_id)
    return result


def _round_trip_matches(
    source_text: str,
    span_start: int,
    span_end: int,
    quote: str,
) -> bool:
    """
    Проверка: нормализованный фрагмент source[span] == нормализованный quote.

    Для exact — должно быть True.
    Для fuzzy — зависит от ratio (см. resolve_quote_in_source).
    """
    fragment = source_text[span_start:span_end]
    return normalize_text(fragment) == normalize_text(quote)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_quote_in_source(
    *,
    quote: str | None,
    source_text: str,
    layout_elements: list[dict[str, Any]],
    fallback_clause_uid: str | None = None,
    fallback_page: int | None = None,
    source_content_hash: str | None = None,
) -> CheckAnchor:
    """
    Найти точное место цитаты в тексте и вернуть CheckAnchor.

    Ступени (в порядке приоритета):
    - exact_span  → confidence=1.0, anchor_validation_passed=True
    - fuzzy_span  → confidence=ratio, anchor_validation_passed=ratio>=0.85
    - clause_only → confidence=0.5 (если fallback_clause_uid задан)
    - page_only   → confidence=0.3 (если fallback_page задан)
    - none        → confidence=0.0

    Параметры:
    - quote:               цитата от детектора (может быть None / пустой);
    - source_text:         текст клаузы (own_text), в котором ищем;
    - layout_elements:     элементы этой клаузы в формате
                           {"element_id", "text", "page", "_seq"};
                           caller фильтрует их по unit.element_ids.
    - fallback_clause_uid: effective_uid клаузы — для clause_only;
    - fallback_page:       страница — для page_only;
    - source_content_hash: 64-hex SHA-256 source_text;
                           если None — вычисляется автоматически.

    Возвращает CheckAnchor. Никогда не None и не бросает исключение.
    """
    # Нормализуем входные данные
    source_text = source_text or ""
    quote_clean = (quote or "").strip()
    fallback_clause_uid_clean = (fallback_clause_uid or "").strip() or None

    # Если caller не передал хеш и есть source_text — считаем сами.
    # Если source_text пуст — хеш не нужен, оставляем None.
    content_hash = source_content_hash
    if content_hash is None and source_text:
        content_hash = _compute_content_hash(source_text)

    # ── Ступень 1–2: span-based (exact / fuzzy) ──────────────────────────
    span: tuple[int, int] | None = None
    method: CheckAnchorMethod = CheckAnchorMethod.NONE
    confidence: float = 0.0
    diagnostics: dict[str, Any] = {}

    if quote_clean and source_text and len(quote_clean) >= _MIN_QUOTE_LEN:
        exact = _exact_span(quote_clean, source_text)
        if exact is not None:
            span = exact
            method = CheckAnchorMethod.EXACT_SPAN
            confidence = 1.0
            diagnostics["match"] = "exact"
        else:
            fuzzy = _fuzzy_span(quote_clean, source_text)
            if fuzzy is not None:
                f_start, f_end, ratio = fuzzy
                span = (f_start, f_end)
                method = CheckAnchorMethod.FUZZY_SPAN
                confidence = round(ratio, 4)
                diagnostics["match"] = "fuzzy"
                diagnostics["ratio"] = round(ratio, 4)
                diagnostics["min_ratio"] = _FUZZY_MIN_RATIO

    # ── Fallback chain: span найден? ─────────────────────────────────────
    if span is not None:
        span_start, span_end = span

        # element_ids — только если layout согласован с source_text
        element_ids: list[str] = []
        if layout_elements:
            offsets, offsets_match = _compute_element_offsets(
                layout_elements, source_text
            )
            if offsets_match:
                element_ids = _span_to_element_ids(
                    span_start, span_end, offsets
                )
            else:
                diagnostics["layout_offset_mismatch"] = True
                logger.debug(
                    "resolve_quote_in_source: layout offset mismatch",
                    extra={
                        "source_text_len": len(source_text),
                        "layout_elements_n": len(layout_elements),
                    },
                )

        # Round-trip validation
        rt_exact = _round_trip_matches(
            source_text, span_start, span_end, quote_clean
        )
        diagnostics["round_trip_exact"] = rt_exact

        if method == CheckAnchorMethod.EXACT_SPAN:
            validation_passed = rt_exact
        else:
            # fuzzy: считаем валидным, если ratio >= _FUZZY_VALIDATED_RATIO
            # (exact-совпадение уже отфильтровано выше — здесь только fuzzy)
            ratio = float(diagnostics.get("ratio", 0.0))
            validation_passed = ratio >= _FUZZY_VALIDATED_RATIO or rt_exact

        # quoted_text — берём реальный фрагмент source (не нормализованный)
        quoted_fragment = source_text[span_start:span_end]

        return CheckAnchor(
            clause_uid=fallback_clause_uid_clean,
            quoted_text=quoted_fragment or None,
            span_start=span_start,
            span_end=span_end,
            source_content_hash=content_hash,
            layout_element_ids=element_ids,
            anchor_method=method,
            anchor_confidence=confidence,
            anchor_validation_passed=validation_passed,
            anchor_diagnostics=diagnostics,
        )

    # ── Ступень 3: clause_only ───────────────────────────────────────────
    if fallback_clause_uid_clean:
        diagnostics["reason"] = "quote_not_found"
        return CheckAnchor(
            clause_uid=fallback_clause_uid_clean,
            source_content_hash=content_hash,
            anchor_method=CheckAnchorMethod.CLAUSE_ONLY,
            anchor_confidence=0.5,
            anchor_validation_passed=False,
            anchor_diagnostics=diagnostics,
        )

    # ── Ступень 4: page_only ─────────────────────────────────────────────
    if isinstance(fallback_page, int) and fallback_page >= 1:
        diagnostics["reason"] = "no_clause_uid"
        return CheckAnchor(
            page=fallback_page,
            source_content_hash=content_hash,
            anchor_method=CheckAnchorMethod.PAGE_ONLY,
            anchor_confidence=0.3,
            anchor_validation_passed=False,
            anchor_diagnostics=diagnostics,
        )

    # ── Ступень 5: none ──────────────────────────────────────────────────
    diagnostics["reason"] = "no_inputs"
    return CheckAnchor(
        anchor_method=CheckAnchorMethod.NONE,
        anchor_confidence=0.0,
        anchor_validation_passed=False,
        anchor_diagnostics=diagnostics,
    )

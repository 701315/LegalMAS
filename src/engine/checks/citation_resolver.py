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
2. fuzzy_span  — минимальное окно, содержащее quote как
                 подпоследовательность токенов; compactness
                 = len(quote_tokens)/span_len_tokens       (confidence = compactness)
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

# Минимальное число токенов в цитате для fuzzy-поиска.
# Ниже — риск ложных срабатываний на служебных словах.
_MIN_FUZZY_QUOTE_TOKENS = 3

# Максимальное отношение span_len_tokens / quote_len_tokens для accept.
# LLM может выбросить токены из середины цитаты — тогда span source
# длиннее quote; ограничение отсекает "разбросанные" совпадения.
_FUZZY_MAX_WINDOW_MULTIPLIER = 2.5

# То же отношение для validation_passed (строже, чем accept).
_FUZZY_VALIDATED_WINDOW_MULTIPLIER = 2.0

# Пунктуация, срезаемая с краёв токена при fuzzy-сравнении. После
# normalize_text юникод-кавычки → " или ', тире → '-'; поэтому здесь
# достаточно ASCII-набора + многоточие + backtick.
# Симметрично с location_validator._TOKEN_EDGE_PUNCT (R21): единая
# нормализационная граница для quote ↔ source во всём pipeline.
_TOKEN_EDGE_PUNCT: str = ".,;:!?()[]{}\"'-…`"

# Разделитель между элементами при materialize_text_from_element_ids
# (см. clause_tree_builder.ClauseTreeBuilder.materialize_text_from_element_ids).


# ---------------------------------------------------------------------------
# Внутренние helpers
# ---------------------------------------------------------------------------


from engine.content.element_offsets import (
    compute_element_offsets as _compute_element_offsets,
    span_to_element_ids as _span_to_element_ids,
)


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


# Sentinel для токенов, у которых после среза краевой пунктуации
# не осталось значащих символов (например, одиночные "-", "...", "!!").
# Такой объект уникален и не совпадёт ни с одним настоящим токеном.
_EDGE_STRIPPED_SENTINEL = object()


def _normalize_tokens_for_match(tokens: list[str]) -> list:
    """
    Нормализовать токены для fuzzy-сравнения.

    Срезаем краевую пунктуацию с каждого токена (симметрично R21).
    Токены, состоящие только из пунктуации, заменяются на уникальный
    sentinel — они не участвуют в матчинге, но сохраняют позицию в
    массиве, что позволяет брать offsets из параллельного массива
    source_offsets без переиндексации.

    Возвращает list, элементы которого — str (значимые токены) или
    _EDGE_STRIPPED_SENTINEL (не значимые).
    """
    out: list = []
    for t in tokens:
        s = t.strip(_TOKEN_EDGE_PUNCT)
        if s:
            out.append(s)
        else:
            out.append(_EDGE_STRIPPED_SENTINEL)
    return out


def _find_min_subsequence_window(
    source_tokens: list[str],
    quote_tokens: list[str],
) -> tuple[int, int, int] | None:
    """
    Минимальное окно в source_tokens, содержащее quote_tokens как
    подпоследовательность (порядок сохранён, пропуски допустимы).

    Возвращает (span_len_tokens, start_idx, end_idx) или None, если
    хотя бы один токен quote не найден в source.

    Алгоритм: forward-greedy + backward-shrink со скользящим s.
    Сложность O(n*m) worst-case, O(n) типично.
    """
    m = len(quote_tokens)
    n = len(source_tokens)
    if m == 0 or n < m:
        return None

    best: tuple[int, int, int] | None = None
    s = 0
    while s <= n - m:
        k = 0
        e = -1
        for i in range(s, n):
            if source_tokens[i] == quote_tokens[k]:
                k += 1
                if k == m:
                    e = i
                    break
        if e < 0:
            break

        k = m - 1
        st = e
        for j in range(e, s - 1, -1):
            if source_tokens[j] == quote_tokens[k]:
                k -= 1
                if k < 0:
                    st = j
                    break

        span_len = e - st + 1
        if best is None or span_len < best[0]:
            best = (span_len, st, e)

        s = st + 1

    return best


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
    Fuzzy-поиск цитаты в source_text через минимальное окно,
    содержащее quote как подпоследовательность токенов.

    Устойчив к типичному поведению LLM: выбрасыванию токенов из
    середины цитаты (порядок сохраняется, добавлять токены LLM не может).

    Возвращает (orig_start, orig_end, compactness):
    - orig_start/orig_end — span в ОРИГИНАЛЕ source_text;
    - compactness = len(quote_tokens) / span_len_tokens in (0, 1].

    Устойчив также к краевой пунктуации (запятые/точки/кавычки на границе
    слова): сравнение токенов идёт после среза краевой пунктуации
    (_normalize_tokens_for_match, симметрично R21).

    None — если:
    - токенов в quote меньше _MIN_FUZZY_QUOTE_TOKENS,
    - хотя бы один значимый токен quote отсутствует в source (галлюцинация),
    - минимальное окно превышает _FUZZY_MAX_WINDOW_MULTIPLIER * len(quote).
    """
    norm_quote = normalize_text(quote)
    quote_tokens = norm_quote.split()
    if len(quote_tokens) < _MIN_FUZZY_QUOTE_TOKENS:
        return None

    norm_source, idx_map = normalize_with_index_map(source_text)
    if not norm_source:
        return None

    source_offsets = _tokenize_with_offsets(norm_source)
    source_tokens = _normalize_tokens_for_match(
        [t[0] for t in source_offsets]
    )
    quote_tokens = _normalize_tokens_for_match(quote_tokens)
    m = len(quote_tokens)
    n = len(source_tokens)
    if n < m:
        return None

    best = _find_min_subsequence_window(source_tokens, quote_tokens)
    if best is None:
        return None

    span_len, start_idx, end_idx = best
    if span_len > _FUZZY_MAX_WINDOW_MULTIPLIER * m:
        return None

    first = source_offsets[start_idx]
    last = source_offsets[end_idx]
    span = _normalized_span_to_original(first[1], last[2], idx_map)
    if span is None:
        return None

    compactness = m / span_len
    return span[0], span[1], compactness


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
    - fuzzy_span  → confidence=compactness,
                    anchor_validation_passed=window_multiplier<=2.0
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
    fallback_page_clean = (
        fallback_page
        if isinstance(fallback_page, int)
        and not isinstance(fallback_page, bool)
        and fallback_page >= 1
        else None
    )

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
                f_start, f_end, compactness = fuzzy
                span = (f_start, f_end)
                method = CheckAnchorMethod.FUZZY_SPAN
                confidence = round(compactness, 4)
                window_multiplier = (
                    (1.0 / compactness) if compactness > 0 else float("inf")
                )
                diagnostics["match"] = "fuzzy"
                diagnostics["compactness"] = round(compactness, 4)
                diagnostics["window_multiplier"] = round(window_multiplier, 4)
                diagnostics["max_window_multiplier"] = _FUZZY_MAX_WINDOW_MULTIPLIER

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
            # fuzzy: считаем валидным, если окно достаточно плотное
            wm = float(diagnostics.get("window_multiplier", float("inf")))
            validation_passed = (
                wm <= _FUZZY_VALIDATED_WINDOW_MULTIPLIER or rt_exact
            )

        # quoted_text — берём реальный фрагмент source (не нормализованный)
        quoted_fragment = source_text[span_start:span_end]

        return CheckAnchor(
            clause_uid=fallback_clause_uid_clean,
            quoted_text=quoted_fragment or None,
            span_start=span_start,
            span_end=span_end,
            source_content_hash=content_hash,
            page=fallback_page_clean,
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

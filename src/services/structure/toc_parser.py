# src/services/structure/toc_parser.py

"""
TOC parser и TOC reliability слой для structural pipeline.

Роль модуля:
- детектировать TOC block в ранних страницах документа;
- разбирать TOC в структурированные ParsedTOCEntry;
- поддерживать dot leaders и OCR-friendly separators;
- поддерживать multi-line TOC entries с adjacency rules;
- считать alignment summary и partial reliability;
- предоставлять reusable TOC model для pipeline / heading scoring / diagnostics.

Главный принцип:
TOC здесь не принимает policy-решений и не вырезает body.
Этот модуль знает только:
- detect,
- parse,
- alignment summary,
- reliability summary.

Важно:
- detect_toc_block() отвечает только за границы TOC блока;
- parse_toc_entries() отвечает только за извлечение uid/title/page_hint;
- evaluate_toc_alignment() и compute_partial_reliability() работают
  по уже размеченному ParsedTOC;
- сам fuzzy/exact matching вынесен в toc_matcher.py;
- policy decision (reliable/partial/reject) должен жить в toc_guard.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from services.structure.heading_patterns import normalize_spaces, parse_raw_heading

_TOC_MAX_PAGES = 5

_TOC_MARKERS = frozenset(
    {
        "table of contents",
        "contents",
        "содержание",
        "оглавление",
    }
)

_DOT_LEADER_RE = re.compile(r"(?:\.{3,}|·{3,}|•{3,}|…{2,})")
_PAGE_HINT_RE = re.compile(
    r"""
    (?:
        ^|[\s\t]
    )
    (?P<page>\d{1,4})
    \s*$
    """,
    re.VERBOSE,
)
_TRAILING_PAGE_TOKEN_RE = re.compile(
    r"""
    (?:
        \s*(?:\.{3,}|·{3,}|•{3,}|…{2,})\s*
        |
        \s+
    )
    (?P<page>\d{1,4})
    \s*$
    """,
    re.VERBOSE,
)
_WHITESPACE_RE = re.compile(r"\s+")
_SEPARATOR_NOISE_RE = re.compile(r"[\t\u00a0]+")


@dataclass(slots=True)
class TOCBlock:
    """
    Сырые границы TOC блока внутри списка elements.

    Attributes:
        detected: Найден ли TOC block.
        start_index: Индекс первого элемента TOC в исходном списке.
        end_index: Exclusive-end индекс TOC блока.
        reason: Причина срабатывания detector-а.
        elements: Срез elements, относящийся к TOC.
    """

    detected: bool
    start_index: int | None
    end_index: int
    reason: str
    elements: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class ParsedTOCEntry:
    """
    Одна структурированная запись TOC.

    Attributes:
        entry_index: Порядковый индекс entry внутри ParsedTOC.
        source_element_indexes: Индексы исходных elements, из которых собрана запись.
        raw_text: Сырой объединённый текст entry.
        normalized_text: Нормализованная форма raw_text.
        uid: Распарсенный heading uid, если удалось извлечь.
        title: Заголовок без page_hint.
        normalized_title: Нормализованный title для matching.
        page_hint: Номер страницы из TOC, если найден.
        match_status: matched / unmatched.
        match_type: exact / fuzzy / no_match.
        matched_heading_uid: UID body heading, если найден match.
        matched_heading_title: Title body heading, если найден match.
        matched_heading_page: Page body heading, если найден match.
        match_score: Similarity score для fuzzy/exact matching.
        toc_missing_in_body: Entry присутствует в TOC, но не найден в body.
        diagnostics: Дополнительные parser/matcher признаки.
    """

    entry_index: int
    source_element_indexes: list[int]
    raw_text: str
    normalized_text: str
    uid: str | None
    title: str
    normalized_title: str
    page_hint: int | None
    match_status: str = "unmatched"
    match_type: str = "no_match"
    matched_heading_uid: str | None = None
    matched_heading_title: str | None = None
    matched_heading_page: int | None = None
    match_score: float | None = None
    toc_missing_in_body: bool = False
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ParsedTOC:
    """
    Полная структурированная модель TOC блока.

    Attributes:
        detected: Был ли TOC обнаружен.
        entries: Список структурированных TOC entries.
        start_index: Индекс начала TOC блока в исходных elements.
        end_index: Exclusive-end индекс TOC блока.
        reason: Причина, по которой TOC block был выделен.
        parser_diagnostics: Сводные диагностические поля parser-а.
    """

    detected: bool
    entries: list[ParsedTOCEntry] = field(default_factory=list)
    start_index: int | None = None
    end_index: int = 0
    reason: str = "not_detected"
    parser_diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TOCAlignmentResult:
    """
    Сводка по alignment ParsedTOC entries с body headings.

    Attributes:
        entries_total: Общее число TOC entries.
        exact_matches: Количество exact matches.
        fuzzy_matches: Количество fuzzy matches.
        no_matches: Количество unmatched entries.
        stale_entries: Количество TOC entries, отсутствующих в body.
        toc_alignment_score: Интегральный alignment score 0.0..1.0.
        mismatch_details: Детали несовпадений для diagnostics.
    """

    entries_total: int
    exact_matches: int
    fuzzy_matches: int
    no_matches: int
    stale_entries: int
    toc_alignment_score: float
    mismatch_details: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class TOCReliabilityResult:
    """
    Partial reliability оценка для TOC.

    Attributes:
        is_reliable: Достаточно ли надёжен TOC как structural signal.
        partial_reliability: Непрерывная оценка надёжности 0.0..1.0.
        confidence_band: Нормализованный уровень надёжности (none/low/partial/high).
        reasons: Explainability reasons для diagnostics и логов.
    """

    is_reliable: bool
    partial_reliability: float
    confidence_band: str
    reasons: list[str] = field(default_factory=list)


def _safe_page(value: Any, default: int = 1) -> int:
    """
    Безопасно приводит page к положительному int.
    """
    try:
        page = int(value)
    except Exception:
        return default
    return page if page >= 1 else default


def _normalize_toc_text(text: str) -> str:
    """
    Нормализует TOC-подобную строку для parser-level работы.

    Делает только безопасную нормализацию:
    - trim + collapse spaces;
    - замена separator noise;
    - выравнивание dot leaders в стабильную форму.

    Функция не удаляет семантически значимые части строки.
    """
    t = normalize_spaces(text)
    if not t:
        return ""
    t = _SEPARATOR_NOISE_RE.sub(" ", t)
    t = _DOT_LEADER_RE.sub(" .... ", t)
    t = _WHITESPACE_RE.sub(" ", t).strip()
    return t


def _extract_page_hint(text: str) -> tuple[str, int | None]:
    """
    Извлекает page_hint из правого хвоста строки.

    Возвращает:
    - text_without_page_hint
    - page_hint | None
    """
    t = _normalize_toc_text(text)
    if not t:
        return "", None

    m = _TRAILING_PAGE_TOKEN_RE.search(t)
    if m:
        page_hint = int(m.group("page"))
        left = t[: m.start()].strip()
        return left, page_hint

    m = _PAGE_HINT_RE.search(t)
    if m:
        page_hint = int(m.group("page"))
        left = t[: m.start()].strip()
        return left, page_hint

    return t, None


def _normalize_toc_title(title: str) -> str:
    """
    Нормализует title TOC entry для downstream matching.

    Убирает:
    - dot leaders;
    - лишние separator traces;
    - висячую punctuation noise.
    """
    t = _normalize_toc_text(title)
    t = _DOT_LEADER_RE.sub(" ", t)
    t = _WHITESPACE_RE.sub(" ", t).strip(" .:-–—\t")
    return normalize_spaces(t)


def _is_likely_toc_marker(text: str) -> bool:
    """
    Проверяет, выглядит ли строка как явный TOC marker.

    Примеры:
    - "Contents"
    - "Table of Contents"
    - "Содержание"
    - "Оглавление"
    """
    return _normalize_toc_text(text).lower() in _TOC_MARKERS


def _looks_substantive_toc_false_positive_text(text: str) -> bool:
    """
    Parser-level negative filter против ложноположительных TOC-строк.

    Это не юридическая классификация "на 100%", а ранний защитный фильтр,
    чтобы detect_toc_block() не захватывал очевидные body/definition-like линии.
    """
    t = _normalize_toc_text(text)
    if not t:
        return False

    words = t.split()
    word_count = len(words)
    has_dot_leader = bool(_DOT_LEADER_RE.search(t))

    if word_count >= 18:
        return True

    if len(t) >= 160:
        return True

    if ":" in t and not has_dot_leader:
        return True

    if t.endswith((".", ";")) and word_count >= 8 and not has_dot_leader:
        return True

    return False


def _is_likely_toc_entry_line(text: str) -> bool:
    """
    Проверяет, похожа ли строка на самостоятельную TOC entry line.

    Строгие сигналы:
    - строка должна иметь page_hint в конце;
    - строка должна быть короткой;
    - либо есть dot leaders,
      либо строка heading-like после извлечения page_hint.

    Negative-фильтры применяются до positive logic.
    """
    t = _normalize_toc_text(text)
    if not t:
        return False

    if _looks_substantive_toc_false_positive_text(t):
        return False

    text_wo_page, page_hint = _extract_page_hint(t)
    if page_hint is None:
        return False

    has_dot_leader = bool(_DOT_LEADER_RE.search(t))

    if not text_wo_page:
        return False

    if len(text_wo_page.split()) > 20:
        return False

    if len(text_wo_page) > 140:
        return False

    if has_dot_leader:
        return True

    parsed = parse_raw_heading(text_wo_page)
    if parsed is not None:
        _, title = parsed
        if len(title.split()) <= 16 and len(title) <= 140:
            return True

    return False


def _is_toc_continuation_line(text: str) -> bool:
    """
    Проверяет, выглядит ли строка как continuation line для multi-line TOC entry.

    Правило строгое:
    - continuation line допустима только после уже начатой TOC entry;
    - строка не должна быть TOC marker;
    - строка не должна выглядеть как новая самостоятельная TOC entry;
    - строка не должна быть слишком длинной;
    - строка не должна быть явным substantive false positive.
    """
    t = _normalize_toc_text(text)
    if not t:
        return False

    if _is_likely_toc_marker(t):
        return False

    if _is_likely_toc_entry_line(t):
        return False

    if _looks_substantive_toc_false_positive_text(t):
        return False

    if len(t.split()) > 18:
        return False

    if len(t) > 140:
        return False

    return True


def _is_toc_tail_line(text: str) -> bool:
    """
    Строка выглядит как хвост multiline TOC entry:
    - есть page_hint;
    - нет собственного heading uid;
    - короткая;
    - не выглядит как substantive/body line.
    """
    t = _normalize_toc_text(text)
    if not t:
        return False

    text_wo_page, page_hint = _extract_page_hint(t)
    if page_hint is None:
        return False

    if _looks_substantive_toc_false_positive_text(text_wo_page):
        return False

    parsed = parse_raw_heading(text_wo_page)
    if parsed is not None:
        return False

    if len(text_wo_page.split()) > 12:
        return False

    if len(text_wo_page) > 100:
        return False

    return True


def detect_toc_block(elements: list[dict[str, Any]]) -> TOCBlock:
    """
    Выделяет границы TOC блока на ранних страницах документа.

    Стратегия:
    1. Пытается найти явный TOC marker.
    2. Если marker не найден — использует fallback по cluster-у TOC-like entries.
    3. Возвращает TOCBlock с start/end индексами и исходным element slice.

    Важно:
    - функция не парсит отдельные entries;
    - функция не решает вопрос reliability;
    - функция не выполняет fuzzy matching.
    """
    if not elements:
        return TOCBlock(
            detected=False,
            start_index=None,
            end_index=0,
            reason="empty_elements",
            elements=[],
        )

    first_page = _safe_page(elements[0].get("page", 1), default=1)
    page_threshold = first_page + max(_TOC_MAX_PAGES - 1, 0)

    start_index: int | None = None
    for i, el in enumerate(elements):
        if _safe_page(el.get("page", 1), default=1) > page_threshold:
            break
        text = _normalize_toc_text(str(el.get("text") or ""))
        if _is_likely_toc_marker(text):
            start_index = i
            break

    if start_index is None:
        cluster_start: int | None = None
        cluster_count = 0
        cluster_last = 0

        for i, el in enumerate(elements):
            if _safe_page(el.get("page", 1), default=1) > page_threshold:
                break

            text = _normalize_toc_text(str(el.get("text") or ""))
            if _is_likely_toc_entry_line(text):
                if cluster_start is None:
                    cluster_start = i
                cluster_count += 1
                cluster_last = i
                continue

            if cluster_count >= 3 and cluster_start is not None:
                return TOCBlock(
                    detected=True,
                    start_index=cluster_start,
                    end_index=cluster_last + 1,
                    reason="toc_entry_cluster",
                    elements=elements[cluster_start:cluster_last + 1],
                )

            cluster_start = None
            cluster_count = 0

        if cluster_count >= 3 and cluster_start is not None:
            return TOCBlock(
                detected=True,
                start_index=cluster_start,
                end_index=cluster_last + 1,
                reason="toc_entry_cluster_end",
                elements=elements[cluster_start:cluster_last + 1],
            )

        return TOCBlock(
            detected=False,
            start_index=None,
            end_index=0,
            reason="not_detected",
            elements=[],
        )

    end_index = start_index + 1
    seen_toc_entry = False

    for i in range(start_index + 1, len(elements)):
        el = elements[i]
        if _safe_page(el.get("page", 1), default=1) > page_threshold:
            break

        text = _normalize_toc_text(str(el.get("text") or ""))
        if not text:
            end_index = i + 1
            continue

        if _is_likely_toc_entry_line(text) or _is_toc_continuation_line(text):
            seen_toc_entry = True
            end_index = i + 1
            continue

        if seen_toc_entry:
            break

    return TOCBlock(
        detected=True,
        start_index=start_index,
        end_index=end_index,
        reason="marker_detected",
        elements=elements[start_index:end_index],
    )


def parse_toc_entries(toc_block: TOCBlock) -> ParsedTOC:
    """
    Разбирает TOC block в список ParsedTOCEntry.

    Поведение:
    - пропускает marker line;
    - собирает multi-line entries по adjacency rules;
    - выделяет uid, title, page_hint;
    - нормализует title для downstream matching.

    Важно:
    - функция не выполняет exact/fuzzy matching;
    - функция не меняет исходные body elements;
    - parser сохраняет source_element_indexes для explainability.
    """
    if not toc_block.detected or not toc_block.elements:
        return ParsedTOC(
            detected=False,
            entries=[],
            start_index=toc_block.start_index,
            end_index=toc_block.end_index,
            reason=toc_block.reason,
            parser_diagnostics={"entries_total": 0},
        )

    entries: list[ParsedTOCEntry] = []
    buffer_texts: list[str] = []
    buffer_indexes: list[int] = []

    def flush_buffer() -> None:
        nonlocal buffer_texts, buffer_indexes

        if not buffer_texts:
            return

        raw_text = normalize_spaces(" ".join(buffer_texts))
        text_wo_page, page_hint = _extract_page_hint(raw_text)
        parsed = parse_raw_heading(text_wo_page)

        uid: str | None = None
        title = text_wo_page
        if parsed is not None:
            uid, parsed_title = parsed
            title = parsed_title or text_wo_page

        normalized_title = _normalize_toc_title(title)
        if normalized_title:
            entries.append(
                ParsedTOCEntry(
                    entry_index=len(entries),
                    source_element_indexes=list(buffer_indexes),
                    raw_text=raw_text,
                    normalized_text=_normalize_toc_text(raw_text),
                    uid=uid,
                    title=title,
                    normalized_title=normalized_title,
                    page_hint=page_hint,
                    diagnostics={
                        "multiline": len(buffer_indexes) > 1,
                    },
                )
            )

        buffer_texts = []
        buffer_indexes = []

    for local_idx, el in enumerate(toc_block.elements):
        global_idx = (toc_block.start_index or 0) + local_idx
        text = _normalize_toc_text(str(el.get("text") or ""))
        if not text:
            flush_buffer()
            continue

        if _is_likely_toc_marker(text):
            continue

        # Приоритет 1: tail line для уже начатой multiline entry
        if buffer_texts and _is_toc_tail_line(text):
            buffer_texts.append(text)
            buffer_indexes.append(global_idx)
            if _extract_page_hint(" ".join(buffer_texts))[1] is not None:
                flush_buffer()
            continue

        # Приоритет 2: самостоятельная TOC entry с page_hint
        if _is_likely_toc_entry_line(text):
            flush_buffer()
            buffer_texts = [text]
            buffer_indexes = [global_idx]
            if _extract_page_hint(text)[1] is not None:
                flush_buffer()
            continue

        # Приоритет 3: строка с heading uid, но без page_hint — начинаем multiline
        parsed = parse_raw_heading(text)
        if parsed is not None:
            flush_buffer()
            buffer_texts = [text]
            buffer_indexes = [global_idx]
            continue

        # Приоритет 4: continuation line для уже открытой entry
        if _is_toc_continuation_line(text) and buffer_texts:
            buffer_texts.append(text)
            buffer_indexes.append(global_idx)
            if _extract_page_hint(" ".join(buffer_texts))[1] is not None:
                flush_buffer()
            continue

        # Fallback: строка не подошла ни под один паттерн
        flush_buffer()

    flush_buffer()

    return ParsedTOC(
        detected=True,
        entries=entries,
        start_index=toc_block.start_index,
        end_index=toc_block.end_index,
        reason=toc_block.reason,
        parser_diagnostics={
            "entries_total": len(entries),
            "multiline_entries": sum(1 for e in entries if e.diagnostics.get("multiline")),
            "entries_with_page_hint": sum(1 for e in entries if e.page_hint is not None),
        },
    )


def evaluate_toc_alignment(parsed_toc: ParsedTOC) -> TOCAlignmentResult:
    """
    Считает alignment summary по уже сматченному ParsedTOC.

    Инвариант:
    - exact/fuzzy/no_match должны быть уже проставлены matcher-ом;
    - функция не делает matching самостоятельно;
    - функция агрегирует quality signal для diagnostics и reliability.

    Score logic:
    - exact даёт полный вклад;
    - fuzzy даёт ослабленный вклад;
    - stale entries дают штраф;
    - итоговое значение clamp-ится в диапазон 0.0..1.0.
    """
    if not parsed_toc.detected or not parsed_toc.entries:
        return TOCAlignmentResult(
            entries_total=0,
            exact_matches=0,
            fuzzy_matches=0,
            no_matches=0,
            stale_entries=0,
            toc_alignment_score=0.0,
            mismatch_details=[],
        )

    exact = sum(1 for e in parsed_toc.entries if e.match_type == "exact")
    fuzzy = sum(1 for e in parsed_toc.entries if e.match_type == "fuzzy")
    no_match = sum(1 for e in parsed_toc.entries if e.match_type == "no_match")
    stale = sum(1 for e in parsed_toc.entries if e.toc_missing_in_body)

    total = len(parsed_toc.entries)
    score = ((exact * 1.0) + (fuzzy * 0.75) - (stale * 0.35)) / total
    score = max(0.0, min(1.0, round(score, 4)))

    mismatch_details = [
        {
            "entry_index": e.entry_index,
            "uid": e.uid,
            "title": e.title,
            "page_hint": e.page_hint,
            "match_type": e.match_type,
            "match_score": e.match_score,
            "toc_missing_in_body": e.toc_missing_in_body,
        }
        for e in parsed_toc.entries
        if e.match_type == "no_match" or e.toc_missing_in_body
    ]

    return TOCAlignmentResult(
        entries_total=total,
        exact_matches=exact,
        fuzzy_matches=fuzzy,
        no_matches=no_match,
        stale_entries=stale,
        toc_alignment_score=score,
        mismatch_details=mismatch_details[:50],
    )


def compute_partial_reliability(
    parsed_toc: ParsedTOC,
    alignment: TOCAlignmentResult,
) -> TOCReliabilityResult:
    """
    Вычисляет partial reliability для TOC как structural signal.

    Идея:
    TOC может быть полезным даже при частичном несовпадении с body.
    Поэтому результат не бинарный, а непрерывный.

    В расчёт входят:
    - alignment score;
    - доля entries с page_hint;
    - penalty за большое число multi-line entries,
      так как они повышают parser ambiguity.

    Возвращает:
    - is_reliable для сильного TOC сигнала;
    - partial_reliability для weak/partial evidence;
    - confidence_band для diagnostics.
    """
    if not parsed_toc.detected:
        return TOCReliabilityResult(
            is_reliable=False,
            partial_reliability=0.0,
            confidence_band="none",
            reasons=["toc_not_detected"],
        )

    entries_total = alignment.entries_total
    if entries_total == 0:
        return TOCReliabilityResult(
            is_reliable=False,
            partial_reliability=0.0,
            confidence_band="none",
            reasons=["toc_detected_but_no_entries_parsed"],
        )

    page_hint_ratio = (
        sum(1 for e in parsed_toc.entries if e.page_hint is not None) / entries_total
    )
    multiline_penalty = (
        sum(1 for e in parsed_toc.entries if e.diagnostics.get("multiline")) / entries_total
    )

    reliability = (
        alignment.toc_alignment_score * 0.65
        + page_hint_ratio * 0.25
        + (1.0 - multiline_penalty) * 0.10
    )
    reliability = max(0.0, min(1.0, round(reliability, 4)))

    reasons: list[str] = []
    if alignment.exact_matches:
        reasons.append("has_exact_matches")
    if alignment.fuzzy_matches:
        reasons.append("has_fuzzy_matches")
    if alignment.stale_entries:
        reasons.append("has_stale_entries")
    if page_hint_ratio < 0.5:
        reasons.append("low_page_hint_coverage")
    if multiline_penalty > 0.3:
        reasons.append("many_multiline_entries")

    if reliability >= 0.75:
        band = "high"
        is_reliable = True
    elif reliability >= 0.45:
        band = "partial"
        is_reliable = False
    else:
        band = "low"
        is_reliable = False

    return TOCReliabilityResult(
        is_reliable=is_reliable,
        partial_reliability=reliability,
        confidence_band=band,
        reasons=reasons,
    )



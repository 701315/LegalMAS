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
_TOC_MIN_CLUSTER_ENTRIES = 3
_TOC_MAX_CONSECUTIVE_NOISE = 2

_TOC_MARKERS = frozenset(
    {
        # EN
        "table of contents",
        "contents",
        "index",
        # RU
        "содержание",
        "оглавление",
        # DE
        "inhaltsverzeichnis",
        # FR
        "sommaire",
        "table des matières",
        # ES
        "índice",
        "contenido",
        "tabla de contenido",
        # PT
        "sumário",
        "índice geral",
    }
)

_TOC_MARKER_STRIP_RE = re.compile(
    r"^(?:[\d]+(?:\.[\d]+)*|[IVXLCDMivxlcdm]+|[Гг]лава\s*\d+|[Ss]ection\s*\d+|[Aa]rticle\s*\d+)[\s.)\]\-]*"
)
_TOC_MARKER_TRAIL_RE = re.compile(r"[.:;\s]+$")

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
    Поддерживает мультиязычные маркеры и префиксы: "1. Содержание", "Глава 1. Contents".
    """
    t = _normalize_toc_text(text).lower().strip()
    if t in _TOC_MARKERS:
        return True
    stripped = _TOC_MARKER_STRIP_RE.sub("", t)
    stripped = _TOC_MARKER_TRAIL_RE.sub("", stripped).strip()
    return stripped in _TOC_MARKERS


def _looks_like_appendix_uid(uid: str | None) -> bool:
    if not uid:
        return False
    u = normalize_spaces(uid).lower()
    return u.startswith("appendix-") or u.startswith("приложение-")


def _looks_like_root_numeric_uid(uid: str | None) -> bool:
    if not uid:
        return False
    return bool(re.fullmatch(r"\d+", uid.strip()))


def _extract_root_numeric_value(uid: str | None) -> int | None:
    if not _looks_like_root_numeric_uid(uid):
        return None
    try:
        return int(uid.strip())
    except Exception:
        return None


def _longest_consecutive_chain(values: list[int]) -> int:
    if not values:
        return 0
    uniq = sorted(set(v for v in values if v >= 1))
    if not uniq:
        return 0
    best = 1
    cur = 1
    for i in range(1, len(uniq)):
        if uniq[i] == uniq[i - 1] + 1:
            cur += 1
            best = max(best, cur)
        else:
            cur = 1
    return best


def _looks_substantive_toc_false_positive_text(text: str) -> bool:
    """
    Parser-level negative filter против ложноположительных TOC-строк.
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
        parsed = parse_raw_heading(t)
        if parsed is None:
            return True
        _, title = parsed
        if len(title.split()) > 12 or len(title) > 90:
            return True

    if t.endswith((".", ";")) and word_count >= 8 and not has_dot_leader:
        return True

    return False


def _is_likely_toc_entry_line(text: str) -> bool:
    """
    Проверяет, похожа ли строка на самостоятельную TOC entry line.
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

    if len(text_wo_page) > 160:
        return False

    if has_dot_leader:
        return True

    parsed = parse_raw_heading(text_wo_page)
    if parsed is not None:
        _, title = parsed
        if len(title.split()) <= 18 and len(title) <= 160:
            return True

    return False


def _is_toc_continuation_line(text: str) -> bool:
    """
    Проверяет, выглядит ли строка как continuation line для multi-line TOC entry.
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


def _is_toc_weak_start_line(text: str) -> bool:
    """
    Строка может быть началом multiline TOC entry даже без page_hint,
    но только если она достаточно похожа на TOC-строку и не похожа на body.
    """
    t = _normalize_toc_text(text)
    if not t:
        return False

    if _looks_substantive_toc_false_positive_text(t):
        return False

    if _DOT_LEADER_RE.search(t):
        return True

    parsed = parse_raw_heading(t)
    if parsed is None:
        return False

    uid, title = parsed
    title = normalize_spaces(title or "")
    if not uid or not title:
        return False

    if len(title.split()) > 14:
        return False

    if len(title) > 110:
        return False

    if title.endswith((".", ";", ":")):
        return False

    return True


def _score_toc_like_line(text: str) -> int:
    """
    Лёгкий parser-level scoring для detect_toc_block().
    Нужен только для детекта кластера и мягкого расширения блока.
    """
    t = _normalize_toc_text(text)
    if not t:
        return 0

    score = 0
    if _is_likely_toc_marker(t):
        score += 5
    if _is_likely_toc_entry_line(t):
        score += 4
    elif _is_toc_tail_line(t):
        score += 3
    elif _is_toc_weak_start_line(t):
        score += 2

    text_wo_page, page_hint = _extract_page_hint(t)
    if page_hint is not None:
        score += 1

    parsed = parse_raw_heading(text_wo_page)
    if parsed is not None:
        uid, _ = parsed
        if uid:
            score += 1
        if _looks_like_appendix_uid(uid):
            score += 1

    return score


def _looks_like_page_artifact(text: str) -> bool:
    """
    Проверяет, похож ли текст на page artifact типа '2 (16)', '(15)', '3 12'.
    Универсально: любые комбинации цифр, скобок, пробелов, точек — без букв.
    """
    t = _normalize_toc_text(text).strip()
    if len(t) > 20:
        return False
    if re.match(r'^[\d\s().,\-]+$', t):
        return True
    return False


def _is_toc_entry_v2(
    text: str,
    *,
    has_page_hint_entries: bool,
    has_marker: bool,
    is_same_page: bool,
) -> bool:
    """
    Универсальный критерий ToC-entry.

    is_same_page: находится ли элемент на той же странице, где началось оглавление.
    Если мы перешли на следующую страницу (is_same_page=False), мы запрещаем
    слабым строкам без номеров страниц продолжать ToC, защищая тело документа.
    """
    # Строгие ToC-строки (с номерами страниц справа) принимаются всегда
    if _is_likely_toc_entry_line(text):
        return True
    if _is_toc_tail_line(text):
        return True

    # Расширенные критерии (активны только если у ToC есть явный маркер)
    if has_marker:
        if _looks_like_page_artifact(text):
            return False

        # Если мы ушли на другую страницу — запрещаем слабые ToC-линии
        if not is_same_page:
            return False

        # На той же странице ToC-маркера разрешаем мягкие ToC-линии (например, приложения)
        if not has_page_hint_entries:
            if _is_toc_weak_start_line(text):
                return True
            # Строка с dot-leader: "1 ОПРЕДЕЛЕНИЯ.........."
            if _DOT_LEADER_RE.search(text):
                t = _normalize_toc_text(text)
                if not _looks_substantive_toc_false_positive_text(t):
                    parsed = parse_raw_heading(t)
                    if parsed is not None:
                        uid, title = parsed
                        if uid and len(title) <= 150:
                            return True
    return False


def detect_toc_block(elements: list[dict[str, Any]]) -> TOCBlock:
    """
    Выделяет границы TOC блока на ранних страницах документа через State Machine.
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

    early_indexes: list[int] = []
    for i, el in enumerate(elements):
        if _safe_page(el.get("page", 1), default=1) > page_threshold:
            break
        early_indexes.append(i)

    if not early_indexes:
        return TOCBlock(
            detected=False,
            start_index=None,
            end_index=0,
            reason="no_early_pages",
            elements=[],
        )

    # Ищем явный маркер ToC
    marker_index: int | None = None
    for i in early_indexes:
        text = _normalize_toc_text(str(elements[i].get("text") or ""))
        if _is_likely_toc_marker(text):
            marker_index = i
            break

    # ── State Machine ──────────────────────────────────────────────
    state = "NOT_IN_TOC"
    start_idx: int | None = marker_index
    last_entry_idx: int | None = None
    consecutive_noise = 0
    has_page_hint_entries = False
    entry_count = 0
    cluster_score = 0
    max_noise = _TOC_MAX_CONSECUTIVE_NOISE

    # Определяем страницу, на которой начался ToC (для правила страниц)
    start_page = first_page
    if marker_index is not None:
        start_page = _safe_page(elements[marker_index].get("page", 1), default=1)
        state = "TOC_CORE"
        last_entry_idx = marker_index
        scan_range = range(marker_index + 1, len(elements))
    else:
        scan_range = range(0, len(elements))

    for i in scan_range:
        el = elements[i]
        el_page = _safe_page(el.get("page", 1), default=1)
        if el_page > page_threshold:
            break

        text = _normalize_toc_text(str(el.get("text") or ""))
        score = _score_toc_like_line(text)
        
        # Проверяем, находимся ли мы на той же странице, где начался ToC
        is_same_page = (el_page == start_page)

        is_entry = _is_toc_entry_v2(
            text,
            has_page_hint_entries=has_page_hint_entries,
            has_marker=marker_index is not None,
            is_same_page=is_same_page,
        )

        if is_entry and _extract_page_hint(text)[1] is not None:
            has_page_hint_entries = True

        if state == "NOT_IN_TOC":
            if score >= 3 or is_entry:
                state = "TOC_CORE"
                start_idx = i
                start_page = el_page  # Фиксируем страницу старта кластера ToC
                last_entry_idx = i
                entry_count = 1 if is_entry else 0
                cluster_score = score
                consecutive_noise = 0

        elif state in {"TOC_CORE", "TOC_SUSPENDED"}:
            if is_entry:
                state = "TOC_CORE"
                last_entry_idx = i
                entry_count += 1
                cluster_score += score
                consecutive_noise = 0
            else:
                consecutive_noise += 1
                cluster_score += score
                if consecutive_noise > max_noise:
                    state = "CLOSED"
                    break
                state = "TOC_SUSPENDED"

    # ── Финализация ────────────────────────────────────────────────
    if start_idx is not None and last_entry_idx is not None:
        is_valid = False
        reason = ""

        if marker_index is not None:
            if entry_count > 0 or last_entry_idx > start_idx:
                is_valid = True
                reason = "marker_detected"
            else:
                reason = "marker_without_entries"
        else:
            if entry_count >= _TOC_MIN_CLUSTER_ENTRIES and cluster_score >= 10:
                is_valid = True
                reason = "toc_entry_cluster"
            else:
                reason = "not_detected"

        if is_valid:
            end_idx = last_entry_idx + 1
            return TOCBlock(
                detected=True,
                start_index=start_idx,
                end_index=end_idx,
                reason=reason,
                elements=elements[start_idx:end_idx],
            )
        return TOCBlock(
            detected=False,
            start_index=None,
            end_index=0,
            reason=reason if reason else "not_detected",
            elements=[],
        )

    return TOCBlock(
        detected=False,
        start_index=None,
        end_index=0,
        reason="not_detected",
        elements=[],
    )

    cluster_start: int | None = None
    cluster_last: int | None = None
    cluster_score = 0
    cluster_entry_like_count = 0
    noise_run = 0

    for i in early_indexes:
        text = _normalize_toc_text(str(elements[i].get("text") or ""))
        score = _score_toc_like_line(text)

        if score >= 3:
            if cluster_start is None:
                cluster_start = i
            cluster_last = i
            cluster_score += score
            if _is_likely_toc_entry_line(text) or _is_toc_tail_line(text):
                cluster_entry_like_count += 1
            noise_run = 0
            continue

        if cluster_start is not None and score >= 2 and noise_run < _TOC_MAX_CONSECUTIVE_NOISE:
            cluster_last = i
            cluster_score += score
            noise_run += 1
            continue

        if (
            cluster_start is not None
            and cluster_last is not None
            and cluster_entry_like_count >= _TOC_MIN_CLUSTER_ENTRIES
            and cluster_score >= 10
        ):
            return TOCBlock(
                detected=True,
                start_index=cluster_start,
                end_index=cluster_last + 1,
                reason="toc_entry_cluster",
                elements=elements[cluster_start : cluster_last + 1],
            )

        cluster_start = None
        cluster_last = None
        cluster_score = 0
        cluster_entry_like_count = 0
        noise_run = 0

    if (
        cluster_start is not None
        and cluster_last is not None
        and cluster_entry_like_count >= _TOC_MIN_CLUSTER_ENTRIES
        and cluster_score >= 10
    ):
        return TOCBlock(
            detected=True,
            start_index=cluster_start,
            end_index=cluster_last + 1,
            reason="toc_entry_cluster_end",
            elements=elements[cluster_start : cluster_last + 1],
        )

    return TOCBlock(
        detected=False,
        start_index=None,
        end_index=0,
        reason="not_detected",
        elements=[],
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

    skipped_marker_lines = 0
    skipped_noise_lines = 0
    weak_start_entries = 0

    def flush_buffer() -> None:
        nonlocal buffer_texts, buffer_indexes, weak_start_entries

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

        weak_start = bool(buffer_texts) and _is_toc_weak_start_line(buffer_texts[0])
        body_like_false_positive = _looks_substantive_toc_false_positive_text(title)

        if (
            normalized_title
            and not body_like_false_positive
            and (
                page_hint is not None
                or weak_start
            )
        ):
            has_page_hint = page_hint is not None
            diagnostics = {
                "multiline": len(buffer_indexes) > 1,
                "has_uid": uid is not None,
                "is_appendix_uid": _looks_like_appendix_uid(uid),
                "is_root_numeric_uid": _looks_like_root_numeric_uid(uid),
                "source_line_count": len(buffer_indexes),
                "weak_entry_no_page_hint": uid is not None and not has_page_hint,
                "weak_start_line": weak_start,
            }

            if diagnostics["weak_start_line"]:
                weak_start_entries += 1

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
                    diagnostics=diagnostics,
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
            skipped_marker_lines += 1
            continue

        if buffer_texts and _is_toc_tail_line(text):
            if _extract_page_hint(" ".join(buffer_texts))[1] is not None:
                flush_buffer()
                if _is_likely_toc_entry_line(text):
                    buffer_texts = [text]
                    buffer_indexes = [global_idx]
                    if _extract_page_hint(text)[1] is not None:
                        flush_buffer()
                continue

            buffer_texts.append(text)
            buffer_indexes.append(global_idx)
            if _extract_page_hint(" ".join(buffer_texts))[1] is not None:
                flush_buffer()
            continue

        if _is_likely_toc_entry_line(text):
            flush_buffer()
            buffer_texts = [text]
            buffer_indexes = [global_idx]
            if _extract_page_hint(text)[1] is not None:
                flush_buffer()
            continue

        parsed = parse_raw_heading(text)
        if parsed is not None and _is_toc_weak_start_line(text):
            flush_buffer()
            buffer_texts = [text]
            buffer_indexes = [global_idx]
            continue

        if _is_toc_continuation_line(text) and buffer_texts:
            buffer_texts.append(text)
            buffer_indexes.append(global_idx)
            if _extract_page_hint(" ".join(buffer_texts))[1] is not None:
                flush_buffer()
            continue

        skipped_noise_lines += 1
        flush_buffer()

    flush_buffer()

    entries_total = len(entries)
    entries_with_page_hint = sum(1 for e in entries if e.page_hint is not None)
    multiline_entries = sum(1 for e in entries if e.diagnostics.get("multiline"))
    entries_with_uid = sum(1 for e in entries if e.uid is not None)
    numeric_uid_entries = sum(
        1 for e in entries if e.uid is not None and re.fullmatch(r"\d+(?:\.\d+)*", e.uid)
    )
    appendix_uid_entries = sum(1 for e in entries if e.diagnostics.get("is_appendix_uid"))
    entries_without_uid_with_page_hint = sum(
        1 for e in entries if e.uid is None and e.page_hint is not None
    )

    root_numeric_values = [
        v
        for v in (_extract_root_numeric_value(e.uid) for e in entries)
        if v is not None
    ]
    root_numeric_chain_len = _longest_consecutive_chain(root_numeric_values)

    return ParsedTOC(
        detected=True,
        entries=entries,
        start_index=toc_block.start_index,
        end_index=toc_block.end_index,
        reason=toc_block.reason,
        parser_diagnostics={
            "entries_total": entries_total,
            "multiline_entries": multiline_entries,
            "entries_with_page_hint": entries_with_page_hint,
            "entries_with_uid": entries_with_uid,
            "numeric_uid_entries": numeric_uid_entries,
            "appendix_uid_entries": appendix_uid_entries,
            "entries_without_uid_with_page_hint": entries_without_uid_with_page_hint,
            "root_numeric_uids": sorted(set(root_numeric_values)),
            "root_numeric_chain_len": root_numeric_chain_len,
            "skipped_marker_lines": skipped_marker_lines,
            "skipped_noise_lines": skipped_noise_lines,
            "weak_start_entries": weak_start_entries,
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
      так как они повышают parser ambiguity;
    - bonus за наличие в TOC root numeric chain,
      так как это сильный structural signal для main agreement.
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

    page_hint_ratio = sum(1 for e in parsed_toc.entries if e.page_hint is not None) / entries_total
    multiline_penalty = (
        sum(1 for e in parsed_toc.entries if e.diagnostics.get("multiline")) / entries_total
    )
    root_numeric_chain_len = int(parsed_toc.parser_diagnostics.get("root_numeric_chain_len", 0) or 0)
    root_chain_bonus = min(root_numeric_chain_len / 8.0, 1.0)

    reliability = (
        alignment.toc_alignment_score * 0.55
        + page_hint_ratio * 0.20
        + (1.0 - multiline_penalty) * 0.10
        + root_chain_bonus * 0.15
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
    if root_numeric_chain_len >= 4:
        reasons.append("has_root_numeric_chain")
    if int(parsed_toc.parser_diagnostics.get("appendix_uid_entries", 0) or 0) > 0:
        reasons.append("has_appendix_entries")

    if reliability >= 0.75:
        band = "high"
        is_reliable = True
    elif reliability >= 0.45:
        band = "partial"
        is_reliable = False
    else:
        band = "low"
        is_reliable = False

    if band == "partial":
        reasons.append("usable_as_weak_hint")

    return TOCReliabilityResult(
        is_reliable=is_reliable,
        partial_reliability=reliability,
        confidence_band=band,
        reasons=reasons,
    )


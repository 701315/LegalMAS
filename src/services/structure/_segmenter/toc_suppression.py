# src/services/structure/_segmenter/toc_suppression.py

"""
Deterministic TOC / catalog boundary suppression for segmenter.

This module computes page-level suppression context that prevents false
boundary-family markers from being created inside:
- table-of-contents pages;
- appendix catalog / appendices list pages;
- amendment catalog / amendments list pages.

The logic is intentionally deterministic and page-local because raw layout
elements that reach the segmenter are not guaranteed to be pre-classified.

P5: introduced appendix-family suppression on TOC / catalog pages.
A3: generalized to boundary-family suppression (amendment-family added).
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

from core.logging import get_logger
from services.structure._element_classifier._detectors import (
    _is_toc_header,
    _toc_line_score,
)
from services.structure.heading_patterns import normalize_spaces

logger = get_logger(__name__)

# ── Константы ────────────────────────────────────────────────────────────────

_TOC_LINE_WEAK_THRESHOLD = 0.45

_CLASSIFIED_TOC_TYPES = frozenset(
    {
        "toc_header",
        "toc_line",
        "possible_toc",
        "toc_content",
    }
)

# ── Catalog header regexes ────────────────────────────────────────────────────

_APPENDIX_CATALOG_HEADER_RE = re.compile(
    r"""
    ^
    (?:
        (?:
            appendices
            |schedules
            |annexes
            |annexures
            |attachments
            |exhibits
        )
        (?:\s*/\s*приложения)?
      |
        приложения
        (?:\s*/\s*
            (?:
                appendices
                |schedules
                |annexes
                |annexures
                |attachments
                |exhibits
            )
        )?
    )
    $
    """,
    re.IGNORECASE | re.VERBOSE,
)

_AMENDMENT_CATALOG_HEADER_RE = re.compile(
    r"""
    ^
    (?:
        (?:
            amendments
            |addenda
            |supplemental\s+agreements
        )
        (?:\s*/\s*
            (?:
                дополнения
                |дополнительные\s+соглашения
            )
        )?
      |
        (?:
            дополнения
            |дополнительные\s+соглашения
        )
        (?:\s*/\s*
            (?:
                amendments
                |addenda
                |supplemental\s+agreements
            )
        )?
    )
    $
    """,
    re.IGNORECASE | re.VERBOSE,
)

_TOC_HEADER_FALLBACK_TOKEN_RE = re.compile(
    r"(?:table\s+of\s+contents|contents|содержание|оглавление)",
    re.IGNORECASE,
)

# Строка оглавления / списка, в которой есть текстовая метка и в конце стоит
# короткий номер страницы. Разрешаем как dotted leaders, так и просто пробел
# перед номером страницы, чтобы быть устойчивыми к OCR и табличной/TOC-верстке.
_TERMINAL_PAGE_NUMBER_RE = re.compile(
    r"""
    ^
    (?=.*[A-Za-zА-ЯЁа-яё])      # есть буквенный текст
    .{6,}?                      # строка не слишком короткая
    (?:
        [\.\-_~·•…]{2,}\s*      # dotted / noisy leader
      |
        \s+                     # или хотя бы пробельный разделитель
    )
    \d{1,4}                     # номер страницы
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _is_terminal_page_number_line(text: str) -> bool:
    """Строка похожа на TOC entry по terminal page number в конце."""
    normalized = normalize_spaces(text)
    if not normalized:
        return False
    return bool(_TERMINAL_PAGE_NUMBER_RE.match(normalized))



# ── Substantive body markers ──────────────────────────────────────────────────

_SUBSTANTIVE_BODY_MARKERS = (
    " означает ",
    " понимается ",
    " обязан",
    " обяз",
    " вправе",
    " должен",
    " shall ",
    " must ",
    " means ",
    " liability",
    " price",
    " payment",
    " transfer",
    " purchase",
    " seller",
    " buyer",
    " ответственность",
    " цена",
    " оплата",
    " переда",
    " продав",
    " покупат",
    " стороны договорились",
    " настоящий договор",
)

# ── Dataclass ────────────────────────────────────────────────────────────────

@dataclass(slots=True)
class BoundarySuppressionContext:
    """
    Page-level suppression context for segment boundary collection.

    P5 introduced appendix-family suppression on TOC / catalog pages.
    A3 generalizes this to boundary-family suppression while preserving
    appendix convenience accessor for backward compatibility.

    Attributes:
        suppressed_boundary_families_by_page:
            Canonical mapping page → set of suppressed boundary families.
            Primary source of truth for suppression decisions.
        suppressed_appendix_pages:
            Convenience set of pages where appendix-family is suppressed.
            Derived from suppressed_boundary_families_by_page.
            Kept for backward compatibility with existing callers.
        page_reasons:
            Diagnostic reasons per suppressed page.
        page_diagnostics:
            Raw counters and signals per suppressed page.
    """

    suppressed_boundary_families_by_page: dict[int, frozenset[str]] = field(
        default_factory=dict
    )
    suppressed_appendix_pages: frozenset[int] = field(default_factory=frozenset)
    page_reasons: dict[int, tuple[str, ...]] = field(default_factory=dict)
    page_diagnostics: dict[int, dict[str, Any]] = field(default_factory=dict)

    def suppresses_boundary_family(self, page: int, family: str | None) -> bool:
        """Возвращает True если данная boundary family подавлена на данной странице."""
        if not family:
            return False
        try:
            page_num = int(page)
        except Exception:
            return False
        return family in self.suppressed_boundary_families_by_page.get(
            page_num, frozenset()
        )

    def suppresses_appendix_page(self, page: int) -> bool:
        """Convenience accessor: appendix-family подавлена на данной странице.

        Сохранён для backward compatibility. Новый код должен использовать
        suppresses_boundary_family(page, BOUNDARY_FAMILY_APPENDIX).
        """
        try:
            page_num = int(page)
        except Exception:
            return False
        return page_num in self.suppressed_appendix_pages

    def to_dict(self) -> dict[str, Any]:
        return {
            "suppressed_appendix_pages": sorted(self.suppressed_appendix_pages),
            "suppressed_boundary_families_by_page": {
                int(page): sorted(families)
                for page, families in sorted(
                    self.suppressed_boundary_families_by_page.items()
                )
            },
            "page_reasons": {
                int(page): list(reasons)
                for page, reasons in sorted(self.page_reasons.items())
            },
            "page_diagnostics": {
                int(page): dict(payload)
                for page, payload in sorted(self.page_diagnostics.items())
            },
        }


# ── Внутренние helpers ────────────────────────────────────────────────────────

def _safe_page(element: dict[str, Any]) -> int:
    try:
        return int(element.get("page") or 1)
    except Exception:
        return 1


def _element_type(element: dict[str, Any]) -> str:
    return str(element.get("element_type") or "").strip().lower()


def _normalized_text(element: dict[str, Any]) -> str:
    return normalize_spaces(str(element.get("text") or ""))


def _detect_catalog_header_family(text: str) -> str | None:
    """Определяет семейство каталог-заголовка (ПРИЛОЖЕНИЯ / ДОПОЛНЕНИЯ / etc).

    Возвращает canonical family string или None если текст не является
    заголовком каталога.
    """
    normalized = normalize_spaces(text)
    if not normalized:
        return None

    if _APPENDIX_CATALOG_HEADER_RE.match(normalized):
        # Импорт здесь чтобы избежать circular import на уровне модуля.
        # patterns.py не импортирует toc_suppression.py, поэтому это безопасно.
        from services.structure._segmenter.patterns import BOUNDARY_FAMILY_APPENDIX
        return BOUNDARY_FAMILY_APPENDIX

    if _AMENDMENT_CATALOG_HEADER_RE.match(normalized):
        from services.structure._segmenter.patterns import BOUNDARY_FAMILY_AMENDMENT
        return BOUNDARY_FAMILY_AMENDMENT

    return None


def _looks_like_toc_header(*, text: str, element_type: str) -> bool:
    """
    More tolerant TOC header detector for raw segmenter input.

    Reuses classifier-level `_is_toc_header()` first, then falls back to a
    lightweight token-based check that tolerates bilingual combined headers
    and OCR-fused forms like:
    - TABLE OF CONTENTS / СОДЕРЖАНИЕ
    - TABLE OF CONTENTS / СОДЕРЖАНИЕTABLE OF CONTENTS
    """
    normalized = normalize_spaces(text)
    if not normalized:
        return False

    if element_type == "toc_header":
        return True

    if _is_toc_header(normalized):
        return True

    if not _TOC_HEADER_FALLBACK_TOKEN_RE.search(normalized):
        return False

    words = normalized.split()
    if len(words) <= 10:
        return True

    if len(normalized) <= 80:
        return True

    return False


def _is_toc_line_like(*, text: str, element_type: str) -> bool:
    if not text:
        return False
    if element_type in _CLASSIFIED_TOC_TYPES:
        return True
    score, _ = _toc_line_score(text)
    return score >= _TOC_LINE_WEAK_THRESHOLD


def _looks_like_substantive_body_line(text: str) -> bool:
    normalized = normalize_spaces(text)
    if not normalized:
        return False

    lower = f" {normalized.lower()} "
    words = normalized.split()

    if any(marker in lower for marker in _SUBSTANTIVE_BODY_MARKERS):
        return True

    if len(words) >= 12:
        return True

    if len(words) >= 8 and normalized.endswith((".", ";", ":")):
        return True

    if ("«" in normalized and "»" in normalized) or (
        '"' in normalized and len(words) >= 6
    ):
        return True

    return False


def _count_compact_catalog_entry_pairs(
    page_texts: list[str],
    entry_positions: list[int],
) -> int:
    """Считает пары соседних catalog-entries, разделённых только короткими
    нессодержательными строками.

    Это надёжный сигнал для каталогов:
    - Приложение 2 ...
    - Условия аккредитивов ...   ← короткое продолжение названия
    - Приложение 3 ...
    - Кредиторская задолженность ...
    """
    if len(entry_positions) < 2:
        return 0

    compact_pairs = 0

    for left_pos, right_pos in zip(entry_positions, entry_positions[1:]):
        between = [
            normalize_spaces(page_texts[pos])
            for pos in range(left_pos + 1, right_pos)
            if normalize_spaces(page_texts[pos])
        ]

        if not between:
            compact_pairs += 1
            continue

        if all(
            len(text.split()) <= 10
            and not _looks_like_substantive_body_line(text)
            for text in between
        ):
            compact_pairs += 1

    return compact_pairs


# ── Публичный API ─────────────────────────────────────────────────────────────

def build_boundary_suppression_context(
    elements: list[dict[str, Any]],
    *,
    resolve_boundary_family: Callable[[str], str | None],
) -> BoundarySuppressionContext:
    """Строит детерминированный page-level suppression context для сегментации.

    Подавляет boundary markers конкретного семейства (appendix, amendment)
    только когда страница уверенно идентифицирована как TOC-подобная
    или catalog-подобная.

    Args:
        elements:               список layout-элементов документа.
        resolve_boundary_family: callback, возвращающий canonical family string
                                 ("appendix" / "amendment" / None) по тексту элемента.
                                 Должен переиспользовать ту же grammar, что и основной
                                 boundary detector, чтобы suppression и detection
                                 не расходились.
    """
    if not elements:
        return BoundarySuppressionContext()

    page_to_indexes: dict[int, list[int]] = defaultdict(list)
    for idx, element in enumerate(elements):
        page_to_indexes[_safe_page(element)].append(idx)

    suppressed_boundary_families_by_page: dict[int, frozenset[str]] = {}
    appendix_suppressed_pages: set[int] = set()
    page_reasons: dict[int, tuple[str, ...]] = {}
    page_diagnostics: dict[int, dict[str, Any]] = {}

    for page, indexes in sorted(page_to_indexes.items()):
        page_texts: list[str] = []

        toc_header_count = 0
        toc_line_like_count = 0
        terminal_page_number_count = 0
        substantive_body_count = 0

        # Family-aware counters.
        family_entry_counts: dict[str, int] = defaultdict(int)
        family_catalog_header_counts: dict[str, int] = defaultdict(int)
        family_positions: dict[str, list[int]] = defaultdict(list)

        for element_index in indexes:
            element = elements[element_index]
            element_type = _element_type(element)
            text = _normalized_text(element)

            if not text:
                continue
            if element_type == "page_artifact":
                continue

            local_pos = len(page_texts)
            page_texts.append(text)

            is_toc_hdr = _looks_like_toc_header(text=text, element_type=element_type)
            is_toc_line = _is_toc_line_like(text=text, element_type=element_type)
            is_terminal_page_number = _is_terminal_page_number_line(text)
            catalog_header_family = _detect_catalog_header_family(text)
            boundary_family = resolve_boundary_family(text)

            if is_toc_hdr:
                toc_header_count += 1
            if is_toc_line:
                toc_line_like_count += 1
            if is_terminal_page_number:
                terminal_page_number_count += 1
            if catalog_header_family:
                family_catalog_header_counts[catalog_header_family] += 1
            if boundary_family:
                family_entry_counts[boundary_family] += 1
                family_positions[boundary_family].append(local_pos)

            # Substantive body: элемент не является TOC / catalog-маркером
            # и выглядит как содержательный текст.
            if (
                not is_toc_hdr
                and not is_toc_line
                and not is_terminal_page_number
                and catalog_header_family is None
                and boundary_family is None
                and _looks_like_substantive_body_line(text)
            ):
                substantive_body_count += 1

        # ── Per-family suppression decision ──────────────────────────────────

        page_level_reasons: list[str] = []
        suppressed_families: set[str] = set()
        family_diagnostics: dict[str, dict[str, Any]] = {}

        families_to_evaluate = sorted(
            set(family_entry_counts.keys()) | set(family_catalog_header_counts.keys())
        )

        for family in families_to_evaluate:
            entry_count = family_entry_counts.get(family, 0)
            header_count = family_catalog_header_counts.get(family, 0)
            compact_pairs = _count_compact_catalog_entry_pairs(
                page_texts=page_texts,
                entry_positions=family_positions.get(family, []),
            )

            family_reasons: list[str] = []

            # Сильнейший сигнал: явный TOC + явный catalog header + entries.
            if toc_header_count >= 1 and header_count >= 1 and entry_count >= 1:
                family_reasons.append("toc_header_with_catalog_block")

            # TOC страница с плотными TOC-строками и несколькими entries.
            if (
                toc_header_count >= 1
                and toc_line_like_count >= 3
                and entry_count >= 2
            ):
                family_reasons.append("toc_page_with_multiple_catalog_entries")

            # OCR-resilient TOC fallback:
            # Даже если explicit TOC/catalog header потерян OCR-ом,
            # страница всё ещё может выглядеть как contents page:
            # - часть строк распознана как toc_line_like;
            # - часть строк узнаётся по terminal page number в конце;
            # - есть appendix/amendment entries;
            # - substantive body почти отсутствует.
            #
            # Важно: одного appendix entry недостаточно, иначе мы начнём
            # ложно подавлять реальные appendix pages с табличным/числовым
            # содержимым. Поэтому без явного header suppress-им только если:
            # - есть минимум 2 entries, ИЛИ
            # - toc_line_like_count сам по себе уже очень высокий.
            if (
                (toc_line_like_count + terminal_page_number_count) >= 4
                and substantive_body_count <= 5
                and entry_count >= 2
            ):
                family_reasons.append("dense_toc_lines_without_explicit_header")

            # Standalone catalog page без TOC header.
            if (
                header_count >= 1
                and entry_count >= 3
                and compact_pairs >= min(2, entry_count - 1)
                and substantive_body_count <= 2
            ):
                family_reasons.append("catalog_header_with_dense_compact_entries")

            # Плотный кластер entries без содержательного текста.
            if (
                entry_count >= 5
                and compact_pairs >= 3
                and substantive_body_count <= 1
                and (
                    toc_header_count >= 1
                    or toc_line_like_count >= 4
                    or header_count >= 1
                )
            ):
                family_reasons.append("dense_catalog_entry_cluster_without_body_text")

            # Чистый структурный инвариант (топология списка):
            # Если на странице есть плотный contiguous cluster из 3+ entries
            # без substantive body между ними, это физически не может быть серией
            # самостоятельных документов. Это roster/list, даже если:
            # - OCR уничтожил заголовок "СОДЕРЖАНИЕ" / "ПРИЛОЖЕНИЯ";
            # - страница находится в конце документа;
            # - нет явных TOC-сигналов.
            if (
                entry_count >= 3
                and compact_pairs >= entry_count - 1
                and substantive_body_count <= 5
            ):
                family_reasons.append("contiguous_entry_cluster_violates_document_physics")

            family_diagnostics[family] = {
                "catalog_header_count": header_count,
                "entry_count": entry_count,
                "compact_entry_pairs": compact_pairs,
            }

            if family_reasons:
                suppressed_families.add(family)
                page_level_reasons.extend(
                    f"{family}:{reason}" for reason in family_reasons
                )

        # ── Commit suppression for this page ─────────────────────────────────

        if suppressed_families:
            suppressed_boundary_families_by_page[page] = frozenset(
                sorted(suppressed_families)
            )
            page_reasons[page] = tuple(page_level_reasons)
            page_diagnostics[page] = {
                "toc_header_count": toc_header_count,
                "toc_line_like_count": toc_line_like_count,
                "terminal_page_number_count": terminal_page_number_count,
                "substantive_body_count": substantive_body_count,
                "page_nonempty_lines": len(page_texts),
                "suppressed_families": sorted(suppressed_families),
                "families": family_diagnostics,
            }

            # Convenience set для backward compatibility.
            from services.structure._segmenter.patterns import BOUNDARY_FAMILY_APPENDIX
            if BOUNDARY_FAMILY_APPENDIX in suppressed_families:
                appendix_suppressed_pages.add(page)

            logger.debug(
                "STRUCTURE segmenter_toc_catalog_suppression_page_detected",
                extra={
                    "page": page,
                    "suppressed_families": sorted(suppressed_families),
                    "reasons": list(page_level_reasons),
                    "toc_header_count": toc_header_count,
                    "toc_line_like_count": toc_line_like_count,
                    "terminal_page_number_count": terminal_page_number_count,
                    "substantive_body_count": substantive_body_count,
                    "page_nonempty_lines": len(page_texts),
                },
            )

    return BoundarySuppressionContext(
        suppressed_boundary_families_by_page=suppressed_boundary_families_by_page,
        suppressed_appendix_pages=frozenset(sorted(appendix_suppressed_pages)),
        page_reasons=page_reasons,
        page_diagnostics=page_diagnostics,
    )


# src/services/structure/_segmenter/toc_suppression.py

"""
Deterministic TOC / appendix-catalog boundary suppression for segmenter.

This module computes page-level suppression context that prevents false
appendix-family boundaries from being created inside:
- table-of-contents pages;
- appendix catalog / appendices list pages.

The logic is intentionally deterministic and page-local because raw layout
elements that reach the segmenter are not guaranteed to be pre-classified.
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

_TOC_LINE_WEAK_THRESHOLD = 0.45

_CLASSIFIED_TOC_TYPES = frozenset(
    {
        "toc_header",
        "toc_line",
        "possible_toc",
        "toc_content",
    }
)

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

_TOC_HEADER_FALLBACK_TOKEN_RE = re.compile(
    r"(?:table\s+of\s+contents|contents|содержание|оглавление)",
    re.IGNORECASE,
)



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


@dataclass(slots=True)
class BoundarySuppressionContext:
    """
    Page-level suppression context for segment boundary collection.

    The current P5 use case suppresses only appendix-family boundaries on pages
    confidently identified as TOC-like or appendix-catalog-like.
    """

    suppressed_appendix_pages: frozenset[int] = field(default_factory=frozenset)
    page_reasons: dict[int, tuple[str, ...]] = field(default_factory=dict)
    page_diagnostics: dict[int, dict[str, Any]] = field(default_factory=dict)

    def suppresses_appendix_page(self, page: int) -> bool:
        try:
            page_num = int(page)
        except Exception:
            return False
        return page_num in self.suppressed_appendix_pages

    def to_dict(self) -> dict[str, Any]:
        return {
            "suppressed_appendix_pages": sorted(self.suppressed_appendix_pages),
            "page_reasons": {
                int(page): list(reasons)
                for page, reasons in sorted(self.page_reasons.items())
            },
            "page_diagnostics": {
                int(page): dict(payload)
                for page, payload in sorted(self.page_diagnostics.items())
            },
        }


def _safe_page(element: dict[str, Any]) -> int:
    try:
        return int(element.get("page") or 1)
    except Exception:
        return 1


def _element_type(element: dict[str, Any]) -> str:
    return str(element.get("element_type") or "").strip().lower()


def _normalized_text(element: dict[str, Any]) -> str:
    return normalize_spaces(str(element.get("text") or ""))


def _looks_like_appendix_catalog_header(text: str) -> bool:
    normalized = normalize_spaces(text)
    if not normalized:
        return False
    return bool(_APPENDIX_CATALOG_HEADER_RE.match(normalized))

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

    if ("«" in normalized and "»" in normalized) or ('"' in normalized and len(words) >= 6):
        return True

    return False


def _count_compact_appendix_pairs(
    page_texts: list[str],
    appendix_positions: list[int],
) -> int:
    """
    Counts adjacent appendix-entry pairs separated only by empty/short,
    non-substantive continuation lines.

    This is a robust signal for appendix catalogs:
    - Appendix 2 ...
    - Terms and Conditions ...
    - Appendix 3 ...
    - Creditor Indebtedness ...
    """

    if len(appendix_positions) < 2:
        return 0

    compact_pairs = 0

    for left_pos, right_pos in zip(appendix_positions, appendix_positions[1:]):
        between = [
            normalize_spaces(page_texts[pos])
            for pos in range(left_pos + 1, right_pos)
            if normalize_spaces(page_texts[pos])
        ]

        if not between:
            compact_pairs += 1
            continue

        if all(
            len(text.split()) <= 10 and not _looks_like_substantive_body_line(text)
            for text in between
        ):
            compact_pairs += 1

    return compact_pairs


def build_boundary_suppression_context(
    elements: list[dict[str, Any]],
    *,
    is_appendix_entry: Callable[[str], bool],
) -> BoundarySuppressionContext:
    """
    Builds deterministic page-level suppression context for segmentation.

    Suppresses appendix-family boundaries only when page evidence strongly
    indicates TOC-like or appendix-catalog-like behavior.
    """
    if not elements:
        return BoundarySuppressionContext()

    page_to_indexes: dict[int, list[int]] = defaultdict(list)
    for idx, element in enumerate(elements):
        page_to_indexes[_safe_page(element)].append(idx)

    suppressed_pages: set[int] = set()
    page_reasons: dict[int, tuple[str, ...]] = {}
    page_diagnostics: dict[int, dict[str, Any]] = {}

    for page, indexes in sorted(page_to_indexes.items()):
        page_texts: list[str] = []
        appendix_positions: list[int] = []

        toc_header_count = 0
        toc_line_like_count = 0
        appendix_catalog_header_count = 0
        appendix_entry_count = 0
        substantive_body_count = 0

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

            is_toc_header = _looks_like_toc_header(
                text=text,
                element_type=element_type,
            )
            is_toc_line_like = _is_toc_line_like(text=text, element_type=element_type)
            is_appendix_catalog_header = _looks_like_appendix_catalog_header(text)
            is_appendix_catalog_entry = bool(is_appendix_entry(text))

            if is_toc_header:
                toc_header_count += 1
            if is_toc_line_like:
                toc_line_like_count += 1
            if is_appendix_catalog_header:
                appendix_catalog_header_count += 1
            if is_appendix_catalog_entry:
                appendix_entry_count += 1
                appendix_positions.append(local_pos)

            if (
                not is_toc_header
                and not is_toc_line_like
                and not is_appendix_catalog_header
                and not is_appendix_catalog_entry
                and _looks_like_substantive_body_line(text)
            ):
                substantive_body_count += 1

        compact_appendix_pairs = _count_compact_appendix_pairs(
            page_texts=page_texts,
            appendix_positions=appendix_positions,
        )

        reasons: list[str] = []

        # Strongest deterministic signal:
        # explicit TOC + explicit appendix catalog header + appendix entries.
        if (
            toc_header_count >= 1
            and appendix_catalog_header_count >= 1
            and appendix_entry_count >= 1
        ):
            reasons.append("toc_header_with_appendix_catalog_block")

        # TOC page with dense TOC lines and multiple appendix entries.
        if (
            toc_header_count >= 1
            and toc_line_like_count >= 3
            and appendix_entry_count >= 2
        ):
            reasons.append("toc_page_with_multiple_appendix_entries")


        # TOC-like line cluster + appendix catalog block, even if explicit TOC
        # header was missed by OCR or upstream heuristics.
        if (
            toc_line_like_count >= 2
            and appendix_catalog_header_count >= 1
            and appendix_entry_count >= 2
            and compact_appendix_pairs >= 1
            and substantive_body_count <= 2
        ):
            reasons.append("toc_line_cluster_with_appendix_catalog_entries")

        # Standalone appendix catalog page.
        if (
            appendix_catalog_header_count >= 1
            and appendix_entry_count >= 3
            and compact_appendix_pairs >= min(2, appendix_entry_count - 1)
            and substantive_body_count <= 2
        ):
            reasons.append("appendix_catalog_header_with_dense_compact_entries")

        # Dense appendix-entry cluster without substantive body text.
        if (
            appendix_entry_count >= 5
            and compact_appendix_pairs >= 3
            and substantive_body_count <= 1
            and (
                toc_header_count >= 1
                or toc_line_like_count >= 4
                or appendix_catalog_header_count >= 1
            )
        ):
            reasons.append("dense_appendix_entry_cluster_without_body_text")

        diagnostics = {
            "toc_header_count": toc_header_count,
            "toc_line_like_count": toc_line_like_count,
            "appendix_catalog_header_count": appendix_catalog_header_count,
            "appendix_entry_count": appendix_entry_count,
            "compact_appendix_pairs": compact_appendix_pairs,
            "substantive_body_count": substantive_body_count,
            "page_nonempty_lines": len(page_texts),
        }

        if reasons:
            suppressed_pages.add(page)
            page_reasons[page] = tuple(reasons)
            page_diagnostics[page] = diagnostics

            logger.debug(
                "STRUCTURE segmenter_toc_appendix_suppression_page_detected",
                extra={
                    "page": page,
                    "reasons": list(reasons),
                    **diagnostics,
                },
            )

    return BoundarySuppressionContext(
        suppressed_appendix_pages=frozenset(sorted(suppressed_pages)),
        page_reasons=page_reasons,
        page_diagnostics=page_diagnostics,
    )


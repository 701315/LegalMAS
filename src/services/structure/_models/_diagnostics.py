# src/services/structure/models/_diagnostics.py

"""
Typed diagnostics models для структуры документа.

Содержит dataclass-модели для TOC, parse quality и функции embedding
diagnostics в structure_diagnostics dict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ._constants import (
    PARSE_QUALITY_OK,
    TOC_CONFIDENCE_NONE,
)
from ._normalization import (
    _ensure_dict,
    _norm_bool,
    _norm_opt_str,
    _normalize_non_negative_int,
    _normalize_parse_quality_status,
    _normalize_probability,
    _normalize_toc_confidence_band,
    _normalize_unique_string_list,
)


@dataclass
class TOCDiagnostics:
    """
    Канонический typed-контракт для TOC diagnostics.

    Описывает результаты обнаружения, парсинга и alignment оглавления (TOC).
    Используется в ClauseTree.structure_diagnostics под ключом "toc_diagnostics".
    """

    detected: bool = False
    block_start_index: int | None = None
    block_end_index: int | None = None
    detection_reason: str | None = None

    header_count: int = 0
    toc_line_count: int = 0
    possible_toc_count: int = 0
    toc_false_positive_count: int = 0

    parsed_entries_total: int = 0
    parsed_entries_with_page_hint: int = 0
    parsed_multiline_entries: int = 0

    exact_matches: int = 0
    fuzzy_matches: int = 0
    no_matches: int = 0
    stale_entries: int = 0

    toc_alignment_score: float = 0.0
    toc_partial_reliability: float = 0.0
    toc_confidence_band: str = TOC_CONFIDENCE_NONE

    toc_guard_applied: bool = False
    toc_body_suppression_allowed: bool = False
    body_recovered_from_toc: int = 0
    toc_skipped_elements: int = 0

    parser_status: str = PARSE_QUALITY_OK
    parser_reasons: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.detected = _norm_bool(self.detected)
        self.block_start_index = (
            None
            if self.block_start_index is None
            else _normalize_non_negative_int(
                self.block_start_index, "TOCDiagnostics.block_start_index"
            )
        )
        self.block_end_index = (
            None
            if self.block_end_index is None
            else _normalize_non_negative_int(self.block_end_index, "TOCDiagnostics.block_end_index")
        )
        self.detection_reason = _norm_opt_str(self.detection_reason)

        self.header_count = _normalize_non_negative_int(
            self.header_count, "TOCDiagnostics.header_count"
        )
        self.toc_line_count = _normalize_non_negative_int(
            self.toc_line_count, "TOCDiagnostics.toc_line_count"
        )
        self.possible_toc_count = _normalize_non_negative_int(
            self.possible_toc_count,
            "TOCDiagnostics.possible_toc_count",
        )
        self.toc_false_positive_count = _normalize_non_negative_int(
            self.toc_false_positive_count,
            "TOCDiagnostics.toc_false_positive_count",
        )

        self.parsed_entries_total = _normalize_non_negative_int(
            self.parsed_entries_total,
            "TOCDiagnostics.parsed_entries_total",
        )
        self.parsed_entries_with_page_hint = _normalize_non_negative_int(
            self.parsed_entries_with_page_hint,
            "TOCDiagnostics.parsed_entries_with_page_hint",
        )
        self.parsed_multiline_entries = _normalize_non_negative_int(
            self.parsed_multiline_entries,
            "TOCDiagnostics.parsed_multiline_entries",
        )

        self.exact_matches = _normalize_non_negative_int(
            self.exact_matches, "TOCDiagnostics.exact_matches"
        )
        self.fuzzy_matches = _normalize_non_negative_int(
            self.fuzzy_matches, "TOCDiagnostics.fuzzy_matches"
        )
        self.no_matches = _normalize_non_negative_int(self.no_matches, "TOCDiagnostics.no_matches")
        self.stale_entries = _normalize_non_negative_int(
            self.stale_entries, "TOCDiagnostics.stale_entries"
        )

        self.toc_alignment_score = _normalize_probability(
            self.toc_alignment_score,
            "TOCDiagnostics.toc_alignment_score",
        )
        self.toc_partial_reliability = _normalize_probability(
            self.toc_partial_reliability,
            "TOCDiagnostics.toc_partial_reliability",
        )
        self.toc_confidence_band = _normalize_toc_confidence_band(self.toc_confidence_band)

        self.toc_guard_applied = _norm_bool(self.toc_guard_applied)
        self.toc_body_suppression_allowed = _norm_bool(self.toc_body_suppression_allowed)
        self.body_recovered_from_toc = _normalize_non_negative_int(
            self.body_recovered_from_toc,
            "TOCDiagnostics.body_recovered_from_toc",
        )

        self.toc_skipped_elements = _normalize_non_negative_int(
            self.toc_skipped_elements,
            "TOCDiagnostics.toc_skipped_elements",
        )

        self.parser_status = _normalize_parse_quality_status(self.parser_status)
        self.parser_reasons = _normalize_unique_string_list(
            self.parser_reasons,
            "TOCDiagnostics.parser_reasons",
        )
        self.extra = _ensure_dict(self.extra, "TOCDiagnostics.extra")

        if self.block_start_index is not None and self.block_end_index is not None:
            if self.block_end_index < self.block_start_index:
                raise ValueError(
                    "TOCDiagnostics block range must satisfy block_end_index >= block_start_index"
                )

        if self.parsed_entries_with_page_hint > self.parsed_entries_total:
            raise ValueError(
                "TOCDiagnostics.parsed_entries_with_page_hint cannot exceed parsed_entries_total"
            )

        if self.parsed_multiline_entries > self.parsed_entries_total:
            raise ValueError(
                "TOCDiagnostics.parsed_multiline_entries cannot exceed parsed_entries_total"
            )

    def to_dict(self) -> dict[str, Any]:
        """Сериализовать в dict для JSON/diagnostics."""
        return {
            "detected": self.detected,
            "block_start_index": self.block_start_index,
            "block_end_index": self.block_end_index,
            "detection_reason": self.detection_reason,
            "header_count": self.header_count,
            "toc_line_count": self.toc_line_count,
            "possible_toc_count": self.possible_toc_count,
            "toc_false_positive_count": self.toc_false_positive_count,
            "parsed_entries_total": self.parsed_entries_total,
            "parsed_entries_with_page_hint": self.parsed_entries_with_page_hint,
            "parsed_multiline_entries": self.parsed_multiline_entries,
            "exact_matches": self.exact_matches,
            "fuzzy_matches": self.fuzzy_matches,
            "no_matches": self.no_matches,
            "stale_entries": self.stale_entries,
            "toc_alignment_score": self.toc_alignment_score,
            "toc_partial_reliability": self.toc_partial_reliability,
            "toc_confidence_band": self.toc_confidence_band,
            "toc_guard_applied": self.toc_guard_applied,
            "toc_body_suppression_allowed": self.toc_body_suppression_allowed,
            "body_recovered_from_toc": self.body_recovered_from_toc,
            "toc_skipped_elements": self.toc_skipped_elements,
            "parser_status": self.parser_status,
            "parser_reasons": list(self.parser_reasons),
            "extra": dict(self.extra),
        }


@dataclass
class ParseQualityDiagnostics:
    """
    Typed-контракт для верхнеуровневого качества разбора segment/file structure.

    Агрегирует статусы TOC, heading, hierarchy parsing и общий статус качества.
    """

    overall_status: str = PARSE_QUALITY_OK
    toc_status: str = PARSE_QUALITY_OK
    heading_status: str = PARSE_QUALITY_OK
    hierarchy_status: str = PARSE_QUALITY_OK

    reasons: list[str] = field(default_factory=list)
    toc_diagnostics: TOCDiagnostics | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.overall_status = _normalize_parse_quality_status(self.overall_status)
        self.toc_status = _normalize_parse_quality_status(self.toc_status)
        self.heading_status = _normalize_parse_quality_status(self.heading_status)
        self.hierarchy_status = _normalize_parse_quality_status(self.hierarchy_status)
        self.reasons = _normalize_unique_string_list(
            self.reasons, "ParseQualityDiagnostics.reasons"
        )
        self.extra = _ensure_dict(self.extra, "ParseQualityDiagnostics.extra")

        if self.toc_diagnostics is not None and not isinstance(
            self.toc_diagnostics, TOCDiagnostics
        ):
            raise ValueError(
                "ParseQualityDiagnostics.toc_diagnostics must be TOCDiagnostics | None"
            )

    def to_dict(self) -> dict[str, Any]:
        """Сериализовать в dict для JSON/diagnostics."""
        return {
            "overall_status": self.overall_status,
            "toc_status": self.toc_status,
            "heading_status": self.heading_status,
            "hierarchy_status": self.hierarchy_status,
            "reasons": list(self.reasons),
            "toc_diagnostics": (
                self.toc_diagnostics.to_dict() if self.toc_diagnostics is not None else None
            ),
            "extra": dict(self.extra),
        }


def embed_toc_diagnostics(
    structure_diagnostics: dict[str, Any] | None,
    toc_diagnostics: TOCDiagnostics | None,
) -> dict[str, Any]:
    """
    Встроить TOCDiagnostics в structure_diagnostics dict.

    Args:
        structure_diagnostics: Существующий diagnostics dict или None
        toc_diagnostics: TOC diagnostics для embedding

    Returns:
        Новый dict с нормализованным ключом "toc_diagnostics"
    """
    base = _ensure_dict(structure_diagnostics, "structure_diagnostics")
    out = dict(base)
    out["toc_diagnostics"] = toc_diagnostics.to_dict() if toc_diagnostics is not None else None
    return out


def embed_parse_quality_diagnostics(
    structure_diagnostics: dict[str, Any] | None,
    parse_quality: ParseQualityDiagnostics | None,
) -> dict[str, Any]:
    """
    Встроить ParseQualityDiagnostics в structure_diagnostics dict.

    Args:
        structure_diagnostics: Существующий diagnostics dict или None
        parse_quality: Parse quality diagnostics для embedding

    Returns:
        Новый dict с нормализованным ключом "parse_quality"
    """
    base = _ensure_dict(structure_diagnostics, "structure_diagnostics")
    out = dict(base)
    out["parse_quality"] = parse_quality.to_dict() if parse_quality is not None else None
    return out

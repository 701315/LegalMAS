# src/services/structure/toc_analysis.py

"""
TOC Analysis orchestration layer.

Роль модуля:
- объединять detect/parse/match/align/reliability/guard в один вызов;
- быть единственной точкой, где TOC policy verdict строится авторитетно;
- предоставлять TOCAnalysisBundle для pipeline и diagnostics.

Вызывается из pipeline ПОСЛЕ первого прохода build_heading_candidates(),
когда headings уже доступны для attach_toc_matches().

Контракт индексов:
- все indexes в TOCGuardVerdict относятся к тому списку elements,
  который передан в analyze_toc_with_guard();
- если вызов идёт на segment slice — indexes segment-local;
- если на весь документ — document-local.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.logging import get_logger
from services.structure.hierarchy_builder import HeadingCandidate
from services.structure.toc_guard import TOCGuardVerdict, evaluate_toc_guard
from services.structure.toc_matcher import attach_toc_matches, build_toc_match_index
from services.structure.toc_parser import (
    ParsedTOC,
    TOCAlignmentResult,
    TOCBlock,
    TOCReliabilityResult,
    compute_partial_reliability,
    detect_toc_block,
    evaluate_toc_alignment,
    parse_toc_entries,
)

logger = get_logger(__name__)


@dataclass(slots=True)
class TOCAnalysisBundle:
    """
    Полный результат TOC analysis для одного segment/document slice.

    Содержит все промежуточные результаты для:
    - pipeline suppression decisions;
    - element annotation через annotate_elements_with_guard();
    - diagnostics заполнения.

    Все integer indexes в guard относятся к тому списку elements,
    на котором был вызван analyze_toc_with_guard().
    """

    toc_block: TOCBlock
    parsed_toc: ParsedTOC
    alignment: TOCAlignmentResult
    reliability: TOCReliabilityResult
    guard: TOCGuardVerdict
    toc_match_index: dict[tuple[str, str], dict[str, Any]]

    @property
    def detected(self) -> bool:
        return self.toc_block.detected

    @property
    def suppress_body_elements(self) -> bool:
        return self.guard.suppress_body_elements

    def to_diagnostics_dict(self) -> dict[str, Any]:
        """
        Возвращает плоский dict для записи в diagnostics["toc"].

        Используется в _build_single_segment_tree() для обновления
        diagnostics после authoritative guard.
        """
        return {
            "detected": self.toc_block.detected,
            "start_index": self.toc_block.start_index,
            "end_index": self.toc_block.end_index,
            "reason": self.toc_block.reason,
            "entries_total": self.alignment.entries_total,
            "entries_with_page_hint": int(
                self.parsed_toc.parser_diagnostics.get("entries_with_page_hint", 0)
            ),
            "multiline_entries": int(
                self.parsed_toc.parser_diagnostics.get("multiline_entries", 0)
            ),
            "toc_alignment_score": round(self.alignment.toc_alignment_score, 4),
            "partial_reliability": round(self.reliability.partial_reliability, 4),
            "is_reliable": self.reliability.is_reliable,
            "confidence_band": self.reliability.confidence_band,
            "exact_matches": self.alignment.exact_matches,
            "fuzzy_matches": self.alignment.fuzzy_matches,
            "no_matches": self.alignment.no_matches,
            "stale_entries": self.alignment.stale_entries,
            "mismatch_details": list(self.alignment.mismatch_details[:20]),
            "reasons": list(self.reliability.reasons),
            "match_index_size": len(self.toc_match_index),
            "guard_decision": self.guard.decision,
            "guard_quality": self.guard.toc_quality,
            "guard_reliability": self.guard.toc_reliability,
            "toc_guard_applied": True,
            "toc_body_suppression_allowed": self.guard.suppress_body_elements,
            "false_positive_element_count": len(self.guard.false_positive_indexes),
            "recoverable_element_count": len(self.guard.recoverable_indexes),
        }


def analyze_toc_with_guard(
    elements: list[dict[str, Any]],
    headings: list[HeadingCandidate],
    *,
    document_id: str | None = None,
) -> TOCAnalysisBundle:
    """
    Полный authoritative TOC analysis для одного segment slice.

    Порядок:
    1. detect_toc_block() — находим границы TOC.
    2. parse_toc_entries() — парсим entries.
    3. attach_toc_matches() — матчим с body headings (требует headings).
    4. evaluate_toc_alignment() — считаем alignment score.
    5. compute_partial_reliability() — считаем reliability.
    6. evaluate_toc_guard() — policy verdict.
    7. build_toc_match_index() — индекс для heading scoring.

    Параметры:
        elements: список элементов сегмента (segment-local slice).
        headings: список headings из первого прохода build_heading_candidates().
        document_id: для логирования.

    Возвращает:
        TOCAnalysisBundle с полным результатом.

    Важно:
        Все indexes в guard.false_positive_indexes и guard.recoverable_indexes
        относятся к переданному списку elements (segment-local).
    """
    toc_block = detect_toc_block(elements)
    parsed_toc = parse_toc_entries(toc_block)

    if headings:
        parsed_toc = attach_toc_matches(parsed_toc, headings)

    alignment = evaluate_toc_alignment(parsed_toc)
    reliability = compute_partial_reliability(parsed_toc, alignment)
    guard = evaluate_toc_guard(parsed_toc, reliability, document_id=document_id)
    toc_match_index = build_toc_match_index(parsed_toc)

    logger.info(
        "STRUCTURE toc_analysis_complete",
        extra={
            "document_id": document_id,
            "toc_detected": toc_block.detected,
            "entries_total": alignment.entries_total,
            "exact_matches": alignment.exact_matches,
            "fuzzy_matches": alignment.fuzzy_matches,
            "no_matches": alignment.no_matches,
            "alignment_score": round(alignment.toc_alignment_score, 4),
            "partial_reliability": round(reliability.partial_reliability, 4),
            "confidence_band": reliability.confidence_band,
            "guard_decision": guard.decision,
            "suppress_body": guard.suppress_body_elements,
            "false_positive_count": len(guard.false_positive_indexes),
            "recoverable_count": len(guard.recoverable_indexes),
        },
    )

    return TOCAnalysisBundle(
        toc_block=toc_block,
        parsed_toc=parsed_toc,
        alignment=alignment,
        reliability=reliability,
        guard=guard,
        toc_match_index=toc_match_index,
    )

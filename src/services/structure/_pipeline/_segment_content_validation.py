# src/services/structure/_pipeline/_segment_content_validation.py

"""
Deterministic content validation for segmentation output.

B1: Segment Content Validation.

Purpose:
- detect segments with no meaningful text content;
- detect anomalously short segments;
- detect duplicate segment_ids;
- detect overlapping element ranges.

Architecture:
- deterministic only, no LLM;
- non-blocking: anomalies produce warnings, not pipeline failures;
- single fallback exception: if ALL segments are empty/anomalous,
  caller may decide to fall back to single segment.

Logging contract:
- each anomaly is logged as STRUCTURE warning with diagnostics;
- a summary is logged after full validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.logging import get_logger
from services.structure.heading_patterns import normalize_spaces
from services.structure.models import SegmentDocument

logger = get_logger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────

# Минимальное суммарное количество символов текста в сегменте,
# чтобы он не считался аномально коротким.
# Выбрано консервативно: инвойс или акт на 1 страницу обычно > 50 символов.
_MIN_MEANINGFUL_CHARS = 30

# Типы элементов, которые считаются содержательными для подсчёта текста.
# Page artifacts, подписи и реквизиты не считаются.
_NON_CONTENT_ELEMENT_TYPES = frozenset({
    "page_artifact",
    "signature_block",
    "requisites_block",
    "toc_header",
    "toc_line",
    "toc_content",
    "possible_toc",
    "unknown_layout",
})


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass(slots=True)
class SegmentContentValidationResult:
    """
    Result of segment content validation.

    Attributes:
        all_valid:       True если ни один сегмент не является полностью пустым.
        has_warnings:    True если есть хотя бы одно предупреждение.
        empty_segments:  segment_ids сегментов без содержательного текста.
        short_segments:  segment_ids аномально коротких сегментов.
        duplicate_ids:   повторяющиеся segment_id.
        overlapping_ranges: пары (segment_id_a, segment_id_b) с перекрытием элементов.
        diagnostics:     детальные диагностики по каждому нарушению.
    """

    all_valid: bool = True
    has_warnings: bool = False
    empty_segments: list[str] = field(default_factory=list)
    short_segments: list[str] = field(default_factory=list)
    duplicate_ids: list[str] = field(default_factory=list)
    overlapping_ranges: list[tuple[str, str]] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "all_valid": self.all_valid,
            "has_warnings": self.has_warnings,
            "empty_segments": self.empty_segments,
            "short_segments": self.short_segments,
            "duplicate_ids": self.duplicate_ids,
            "overlapping_ranges": [
                {"a": a, "b": b} for a, b in self.overlapping_ranges
            ],
            "diagnostics_count": len(self.diagnostics),
        }


# ── Core validation ───────────────────────────────────────────────────────────

def _count_meaningful_chars(
    segment: SegmentDocument,
    elements: list[dict[str, Any]],
) -> int:
    """
    Считает суммарное количество символов содержательного текста в сегменте.

    Исключает page artifacts, подписи, toc-элементы.
    """
    total = 0
    for idx in range(segment.element_start, min(segment.element_end, len(elements))):
        el = elements[idx]
        element_type = str(el.get("element_type") or "").strip().lower()
        if element_type in _NON_CONTENT_ELEMENT_TYPES:
            continue
        text = normalize_spaces(str(el.get("text") or ""))
        total += len(text)
    return total


def _check_duplicate_ids(
    segments: list[SegmentDocument],
) -> list[str]:
    """
    Возвращает список дублирующихся segment_id.
    """
    seen: set[str] = set()
    duplicates: list[str] = []
    for seg in segments:
        sid = str(seg.segment_id or "")
        if sid in seen:
            if sid not in duplicates:
                duplicates.append(sid)
        else:
            seen.add(sid)
    return duplicates


def _check_overlapping_ranges(
    segments: list[SegmentDocument],
) -> list[tuple[str, str]]:
    """
    Возвращает пары сегментов с перекрывающимися element ranges.

    Два сегмента перекрываются если их [element_start, element_end)
    имеют общие индексы.
    """
    overlaps: list[tuple[str, str]] = []
    for i, seg_a in enumerate(segments):
        for seg_b in segments[i + 1:]:
            # [a_start, a_end) ∩ [b_start, b_end) непусто если:
            # a_start < b_end AND b_start < a_end
            if seg_a.element_start < seg_b.element_end and seg_b.element_start < seg_a.element_end:
                overlaps.append((str(seg_a.segment_id), str(seg_b.segment_id)))
    return overlaps


def validate_segment_content(
    segments: list[SegmentDocument],
    elements: list[dict[str, Any]],
    *,
    document_id: str,
) -> SegmentContentValidationResult:
    """
    Deterministic content validation for segmentation output.

    Checks:
    1. Empty segments — no meaningful text content at all.
    2. Anomalously short segments — total content below threshold.
    3. Duplicate segment_ids — deterministic IDs should never collide.
    4. Overlapping element ranges — structural integrity check.

    Returns SegmentContentValidationResult with full diagnostics.
    Does NOT raise exceptions. Caller decides how to handle warnings.
    """
    result = SegmentContentValidationResult()

    if not segments:
        return result

    # ── 1 + 2: Content checks per segment ────────────────────────────────────
    for seg in segments:
        char_count = _count_meaningful_chars(seg, elements)
        sid = str(seg.segment_id or "")

        if char_count == 0:
            result.empty_segments.append(sid)
            result.has_warnings = True
            result.diagnostics.append({
                "check": "empty_segment",
                "segment_id": sid,
                "segment_order": seg.segment_order,
                "segment_type": seg.segment_type,
                "element_start": seg.element_start,
                "element_end": seg.element_end,
                "char_count": 0,
            })
        elif char_count < _MIN_MEANINGFUL_CHARS:
            result.short_segments.append(sid)
            result.has_warnings = True
            result.diagnostics.append({
                "check": "short_segment",
                "segment_id": sid,
                "segment_order": seg.segment_order,
                "segment_type": seg.segment_type,
                "element_start": seg.element_start,
                "element_end": seg.element_end,
                "char_count": char_count,
                "threshold": _MIN_MEANINGFUL_CHARS,
            })

    # ── 3: Duplicate IDs ──────────────────────────────────────────────────────
    duplicate_ids = _check_duplicate_ids(segments)
    if duplicate_ids:
        result.duplicate_ids = duplicate_ids
        result.has_warnings = True
        for did in duplicate_ids:
            result.diagnostics.append({
                "check": "duplicate_segment_id",
                "segment_id": did,
            })

    # ── 4: Overlapping ranges ─────────────────────────────────────────────────
    overlapping = _check_overlapping_ranges(segments)
    if overlapping:
        result.overlapping_ranges = overlapping
        result.has_warnings = True
        for sid_a, sid_b in overlapping:
            result.diagnostics.append({
                "check": "overlapping_element_ranges",
                "segment_id_a": sid_a,
                "segment_id_b": sid_b,
            })

    # ── all_valid: False только если ВСЕ сегменты пустые ─────────────────────
    # Одиночный пустой сегмент — warning, не failure.
    # Все пустые — это уже structural problem.
    if result.empty_segments and len(result.empty_segments) == len(segments):
        result.all_valid = False

    # ── Logging ───────────────────────────────────────────────────────────────
    if result.has_warnings:
        logger.warning(
            "STRUCTURE segment_content_validation_warnings",
            extra={
                "document_id": document_id,
                "total_segments": len(segments),
                "empty_segments_count": len(result.empty_segments),
                "short_segments_count": len(result.short_segments),
                "duplicate_ids_count": len(result.duplicate_ids),
                "overlapping_ranges_count": len(result.overlapping_ranges),
                "all_valid": result.all_valid,
            },
        )
    else:
        logger.debug(
            "STRUCTURE segment_content_validation_ok",
            extra={
                "document_id": document_id,
                "total_segments": len(segments),
            },
        )

    return result


    
# src/services/structure/pipeline/_segment_utils.py

"""
Segmentation helpers.

Содержит:
- single segment fallback
- основной wrapper над segment_elements
"""

from __future__ import annotations

from core.logging import get_logger
from services.structure.models import (
    SEGMENT_CONFIDENCE_HIGH,
    SEGMENT_TYPE_CONTRACT,
    SegmentDocument,
    make_segment_id,
)
from services.structure.segmenter import segment_elements

from ._element_validation import segment_slice_is_valid
from ._segment_content_validation import validate_segment_content
from ._utils import pages_for_elements

logger = get_logger(__name__)


def make_single_segment_list(
    *,
    document_id: str,
    document_version_id: str | None,
    elements: list[dict],
) -> list[SegmentDocument]:
    """
    Возвращает один сегмент, покрывающий весь документ.
    """
    page_start, page_end = pages_for_elements(elements)

    return [
        SegmentDocument(
            segment_id=make_segment_id(document_id, segment_order=0),
            document_id=document_id,
            document_version_id=document_version_id,
            segment_order=0,
            segment_type=SEGMENT_TYPE_CONTRACT,
            segment_title=None,
            page_start=page_start,
            page_end=page_end,
            element_start=0,
            element_end=len(elements),
            confidence=SEGMENT_CONFIDENCE_HIGH,
            is_primary=True,
            segmentation_confidence_score=1.0,
            segmentation_reasons=["single_segment_pipeline_fallback"],
        )
    ]


def segment_document(
    *,
    document_id: str,
    document_version_id: str | None,
    elements: list[dict],
) -> list[SegmentDocument]:
    """
    Выполняет сегментацию с защитой от ошибок.
    """
    try:
        segments = segment_elements(document_id=document_id, elements=elements)
    except Exception as e:
        logger.exception(
            "STRUCTURE segmentation_failed_fallback_to_single_segment",
            extra={
                "document_id": document_id,
                "elements_count": len(elements),
                "error": str(e),
            },
        )
        return make_single_segment_list(
            document_id=document_id,
            document_version_id=document_version_id,
            elements=elements,
        )

    if not segments:
        logger.warning(
            "STRUCTURE segmentation_returned_empty_fallback_to_single_segment",
            extra={"document_id": document_id},
        )
        return make_single_segment_list(
            document_id=document_id,
            document_version_id=document_version_id,
            elements=elements,
        )

    valid_segments = [seg for seg in segments if segment_slice_is_valid(seg, len(elements))]

    if len(valid_segments) != len(segments):
        logger.warning(
            "STRUCTURE segmentation_invalid_ranges_fallback_to_single_segment",
            extra={"document_id": document_id},
        )
        return make_single_segment_list(
            document_id=document_id,
            document_version_id=document_version_id,
            elements=elements,
        )

    # B1: Content validation — non-blocking.
    # Anomalies (empty, short, duplicates, overlaps) are logged as warnings.
    # Pipeline falls back to single segment only if ALL segments are empty.
    content_validation = validate_segment_content(
        valid_segments,
        elements,
        document_id=document_id,
    )

    if not content_validation.all_valid:
        logger.warning(
            "STRUCTURE segmentation_all_segments_empty_fallback_to_single_segment",
            extra={
                "document_id": document_id,
                "segments_count": len(valid_segments),
                **content_validation.to_dict(),
            },
        )
        return make_single_segment_list(
            document_id=document_id,
            document_version_id=document_version_id,
            elements=elements,
        )

    for seg in valid_segments:
        seg.document_version_id = document_version_id

    return valid_segments

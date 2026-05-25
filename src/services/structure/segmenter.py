# src/services/structure/segmenter.py

"""
Deterministic segmentation of a physical file into logical document segments.

Для непрофессионального программиста:
Этот модуль анализирует весь файл и решает:
- это один логический документ;
- или несколько сегментов: основной договор, приложения, акты, доп. соглашения и т.д.

Главная идея v3:
сегментация теперь не "опция", а обязательный этап structural pipeline.
Но это НЕ значит, что файл обязательно режется на много частей.
Это значит только одно: мы всегда пытаемся определить сегменты,
а результат может быть:
- single-segment
- multi-segment

Принципы:
- детерминированность;
- консервативность;
- объяснимость: каждая найденная граница имеет reasons;
- безопасный fallback: при любой ошибке возвращается один сегмент.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from core.config import settings
from core.logging import get_logger
from services.structure.heading_patterns import normalize_spaces
from services.structure.heading_scoring import score_heading_candidate, CandidateStatus
from services.structure.models import (
    SegmentDocument,
    SEGMENT_CONFIDENCE_HIGH,
    SEGMENT_CONFIDENCE_LOW,
    SEGMENT_CONFIDENCE_MEDIUM,
    SEGMENT_TYPE_ACT,
    SEGMENT_TYPE_AMENDMENT,
    SEGMENT_TYPE_APPENDIX,
    SEGMENT_TYPE_CONTRACT,
    SEGMENT_TYPE_INVOICE,
    SEGMENT_TYPE_PROTOCOL,
    SEGMENT_TYPE_UNKNOWN,
    make_segment_id,
)

logger = get_logger(__name__)

_MIN_ELEMENTS_BETWEEN_BOUNDARIES = 3
_MAX_REASONABLE_SEGMENTS = 15
_NEW_PAGE_HEADING_WINDOW = 3

_MIN_PAGES_FOR_ARTIFACT = 3
_MAX_HEADER_LINES_TO_CHECK = 5

_DEFAULT_SEGMENT_CONFIDENCE_THRESHOLD = 0.70
_WEAK_BOUNDARY_THRESHOLD = 0.45

_NUMBER_MARKER_RE = r"(?:№|n|no\.?)\s*"
_CYRILLIC_WORD_RE = r"[\u0401\u0451\u0410-\u044f]+"

_APPENDIX_RE = re.compile(
    rf"^(?:appendix|schedule|exhibit|annex)\s+\w+|^приложение(?:\s+{_NUMBER_MARKER_RE})?\s*[\w\dа-яёa-z-]+(?::)?$",
    re.IGNORECASE,
)

_AMENDMENT_RE = re.compile(
    rf"^(?:addendum\s+\w+|amendment\s+(?:no\.?\s*)?\w+|supplemental agreement|дополнительное\s+соглашение(?:\s+{_NUMBER_MARKER_RE})?\s*[\w\dа-яёa-z-]*)[:.]?$",
    re.IGNORECASE,
)

_ACT_RE = re.compile(
    r"^(?:передаточный\s+акт|акт\s+(?:приема|приёма|сдачи|выполненных\s+работ|оказанных\s+услуг)|acceptance act|delivery act)[:.]?$",
    re.IGNORECASE,
)

_INVOICE_RE = re.compile(
    r"^(?:счет|счёт)\s*(?:на\s+оплату)?[:.]?$|^invoice\b[:.]?$",
    re.IGNORECASE,
)

_PROTOCOL_RE = re.compile(
    r"^(?:protocol|протокол)\b[:.]?$",
    re.IGNORECASE,
)

_HORIZONTAL_RULE_RE = re.compile(r"^\s*-{3,}\s*$")

_SIGNATURE_LINE_RE = re.compile(
    r"^(?:подпись|signature|м\.п\.|место\s+печати|генеральный\s+директор|директор|по[дд]писи\s+сторон)\b",
    re.IGNORECASE,
)

_REQUISITES_LINE_RE = re.compile(
    r"^(?:реквизиты|адреса\s+и\s+реквизиты|юридический\s+адрес|инн|кпп|огрн|расчетный\s+счет|р/с|к/с|банк|бик)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _BoundarySignal:
    """
    Один сигнал в пользу границы сегмента.
    """
    name: str
    weight: float
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class _BoundaryCandidate:
    """
    Кандидат на начало нового сегмента.
    """
    element_index: int
    page: int
    text: str
    segment_type: str
    title: str | None
    confidence_score: float
    confidence_label: str
    signals: tuple[_BoundarySignal, ...]
    reasons: tuple[str, ...]
    is_mid_page: bool


def segment_elements(
    document_id: str,
    elements: list[dict[str, Any]],
) -> list[SegmentDocument]:
    """
    Splits elements[] into logical SegmentDocuments.

    Гарантии:
    - никогда не бросает исключение наружу;
    - всегда возвращает >= 1 сегмент;
    - если надёжных границ нет — возвращает один сегмент на весь файл.
    """
    try:
        return _segment_elements_impl(document_id=document_id, elements=elements)
    except Exception as e:
        logger.exception(
            "STRUCTURE segmenter failed, falling back to single segment",
            extra={
                "document_id": document_id,
                "elements_count": len(elements or []),
                "error": str(e),
            },
        )
        return [_make_single_segment(document_id=document_id, elements=elements or [])]


def _segment_elements_impl(
    *,
    document_id: str,
    elements: list[dict[str, Any]],
) -> list[SegmentDocument]:
    if not document_id:
        document_id = "<unknown>"

    if not isinstance(elements, list) or not elements:
        return [_make_single_segment(document_id=document_id, elements=[])]

    clean_elements = [el for el in elements if isinstance(el, dict)]
    if not clean_elements:
        return [_make_single_segment(document_id=document_id, elements=[])]

    artifacts = _detect_repeated_page_artifacts(clean_elements)
    candidates = _collect_boundary_candidates(clean_elements, artifacts=artifacts)
    validated_candidates = _validate_boundary_candidates(clean_elements, candidates)

    threshold = float(
        getattr(
            settings,
            "SEGMENT_CONFIDENCE_THRESHOLD",
            _DEFAULT_SEGMENT_CONFIDENCE_THRESHOLD,
        )
    )

    accepted_candidates = [
        c for c in validated_candidates
        if c.confidence_score >= threshold
    ]

    if not accepted_candidates:
        single = _make_single_segment(document_id=document_id, elements=clean_elements)
        _propagate_segment_metadata(elements=clean_elements, segments=[single])

        logger.info(
            "STRUCTURE segmenter_single_segment_mode",
            extra={
                "document_id": document_id,
                "elements_count": len(clean_elements),
                "candidates_found": len(candidates),
                "validated_candidates": len(validated_candidates),
                "accepted_candidates": 0,
                "threshold": threshold,
                "rejected_reasons_preview": [
                    {
                        "element_index": c.element_index,
                        "page": c.page,
                        "segment_type": c.segment_type,
                        "confidence_score": round(c.confidence_score, 3),
                        "reasons": list(c.reasons),
                    }
                    for c in validated_candidates[:10]
                ],
            },
        )
        return [single]

    segments = _build_segments_from_candidates(
        document_id=document_id,
        elements=clean_elements,
        candidates=accepted_candidates,
    )

    if not segments:
        single = _make_single_segment(document_id=document_id, elements=clean_elements)
        _propagate_segment_metadata(elements=clean_elements, segments=[single])
        return [single]

    if len(segments) > _MAX_REASONABLE_SEGMENTS:
        logger.warning(
            "STRUCTURE segmenter_too_many_segments_fallback_to_single",
            extra={
                "document_id": document_id,
                "segments_count": len(segments),
                "max_reasonable_segments": _MAX_REASONABLE_SEGMENTS,
            },
        )
        single = _make_single_segment(document_id=document_id, elements=clean_elements)
        _propagate_segment_metadata(elements=clean_elements, segments=[single])
        return [single]

    _assign_primary_segment(segments)
    _attach_scope_names(segments)
    _propagate_segment_metadata(elements=clean_elements, segments=segments)

    logger.info(
        "STRUCTURE segmenter_completed",
        extra={
            "document_id": document_id,
            "elements_count": len(clean_elements),
            "segments_count": len(segments),
            "segment_types": [s.segment_type for s in segments],
            "scope_names": [getattr(s, "scope_name", None) for s in segments],
            "accepted_boundaries": [
                {
                    "element_index": c.element_index,
                    "page": c.page,
                    "segment_type": c.segment_type,
                    "confidence_score": round(c.confidence_score, 3),
                    "reasons": list(c.reasons),
                }
                for c in accepted_candidates
            ],
        },
    )

    return segments


def _detect_repeated_page_artifacts(
    elements: list[dict[str, Any]],
) -> set[int]:
    page_first_indices: dict[int, list[int]] = defaultdict(list)
    repeated_indices: set[int] = set()

    for idx, el in enumerate(elements):
        page = _safe_page(el)
        if len(page_first_indices[page]) < _MAX_HEADER_LINES_TO_CHECK:
            page_first_indices[page].append(idx)

        if _element_type(el) == "page_artifact":
            repeated_indices.add(idx)

    signature_hits: dict[str, list[int]] = defaultdict(list)
    for _, idx_list in page_first_indices.items():
        for idx in idx_list:
            if idx in repeated_indices:
                continue

            raw_text = elements[idx].get("text", "")
            text = normalize_spaces(str(raw_text or ""))
            if not text:
                continue

            signature_hits[text].append(idx)

    for _, idx_list in signature_hits.items():
        if len(idx_list) >= _MIN_PAGES_FOR_ARTIFACT:
            repeated_indices.update(idx_list)

    return repeated_indices


def _collect_boundary_candidates(
    elements: list[dict[str, Any]],
    artifacts: set[int] | None = None,
) -> list[_BoundaryCandidate]:
    artifacts = artifacts or set()
    candidates: list[_BoundaryCandidate] = []

    for idx, element in enumerate(elements):
        if idx == 0:
            continue
        if idx in artifacts:
            continue

        raw_text = element.get("text", "")
        text = normalize_spaces(str(raw_text or ""))
        if not text:
            continue
        if _HORIZONTAL_RULE_RE.match(text):
            continue
        if _is_non_boundary_element_type(element):
            continue
        if _looks_like_non_boundary_block(text):
            continue

        marker = _match_boundary_marker(text)
        if not marker:
            continue

        page = _safe_page(element)
        page_offset = _page_offset(elements, idx)

        if not _is_boundary_position(elements, idx, text):
            continue

        signals: list[_BoundarySignal] = []
        reasons: list[str] = []

        seg_type = _infer_segment_type_from_text(text)
        title = _infer_segment_title(text)

        signals.append(
            _BoundarySignal(
                name="boundary_keyword",
                weight=0.45,
                details={"marker": marker},
            )
        )
        reasons.append("boundary_keyword")

        if page_offset == 0:
            signals.append(
                _BoundarySignal(
                    name="page_break",
                    weight=0.20,
                    details={"page_offset": page_offset},
                )
            )
            reasons.append("page_break")

        numbering_reset = _detect_local_numbering_reset(elements, idx)
        if numbering_reset:
            signals.append(
                _BoundarySignal(
                    name="numbering_reset",
                    weight=0.20,
                    details=numbering_reset,
                )
            )
            reasons.append("numbering_reset")

        formatting_shift = _detect_formatting_shift(elements, idx)
        if formatting_shift:
            signals.append(
                _BoundarySignal(
                    name="formatting_shift",
                    weight=0.10,
                    details=formatting_shift,
                )
            )
            reasons.append("formatting_shift")

        heading_density_shift = _detect_heading_density_shift(elements, idx)
        if heading_density_shift:
            signals.append(
                _BoundarySignal(
                    name="heading_density_shift",
                    weight=0.10,
                    details=heading_density_shift,
                )
            )
            reasons.append("heading_density_shift")

        if _is_heading_like(text):
            signals.append(
                _BoundarySignal(
                    name="heading_like_marker",
                    weight=0.05,
                    details={},
                )
            )
            reasons.append("heading_like_marker")

        if _is_heading_candidate_element(element):
            signals.append(
                _BoundarySignal(
                    name="element_type_heading_candidate",
                    weight=0.10,
                    details={"element_type": _element_type(element)},
                )
            )
            reasons.append("element_type_heading_candidate")

        if _is_list_item_element(element):
            signals.append(
                _BoundarySignal(
                    name="element_type_list_item_penalty",
                    weight=-0.20,
                    details={"element_type": _element_type(element)},
                )
            )
            reasons.append("element_type_list_item_penalty")

        if _looks_like_segment_start_context(elements, idx):
            signals.append(
                _BoundarySignal(
                    name="segment_start_context",
                    weight=0.10,
                    details={},
                )
            )
            reasons.append("segment_start_context")

        confidence_score = max(0.0, min(sum(signal.weight for signal in signals), 1.0))
        confidence_label = _confidence_label(confidence_score)

        candidates.append(
            _BoundaryCandidate(
                element_index=idx,
                page=page,
                text=text,
                segment_type=seg_type,
                title=title,
                confidence_score=confidence_score,
                confidence_label=confidence_label,
                signals=tuple(signals),
                reasons=tuple(reasons),
                is_mid_page=(page_offset > 0),
            )
        )

    return candidates


def _validate_boundary_candidates(
    elements: list[dict[str, Any]],
    candidates: list[_BoundaryCandidate],
) -> list[_BoundaryCandidate]:
    if not candidates:
        return []

    validated: list[_BoundaryCandidate] = []

    for candidate in sorted(candidates, key=lambda c: (c.element_index, -c.confidence_score)):
        if candidate.element_index <= 0:
            continue

        if _looks_like_mid_paragraph_reference(elements, candidate):
            continue

        if candidate.confidence_score < _WEAK_BOUNDARY_THRESHOLD:
            continue

        if validated:
            prev = validated[-1]
            if candidate.element_index - prev.element_index < _MIN_ELEMENTS_BETWEEN_BOUNDARIES:
                winner = _pick_stronger_boundary(prev, candidate)
                validated[-1] = winner
                continue

        validated.append(candidate)

    return validated


def _pick_stronger_boundary(
    left: _BoundaryCandidate,
    right: _BoundaryCandidate,
) -> _BoundaryCandidate:
    if right.confidence_score > left.confidence_score:
        return right
    if right.confidence_score < left.confidence_score:
        return left

    left_has_page_break = any(s.name == "page_break" for s in left.signals)
    right_has_page_break = any(s.name == "page_break" for s in right.signals)
    if right_has_page_break and not left_has_page_break:
        return right
    if left_has_page_break and not right_has_page_break:
        return left

    left_has_reset = any(s.name == "numbering_reset" for s in left.signals)
    right_has_reset = any(s.name == "numbering_reset" for s in right.signals)
    if right_has_reset and not left_has_reset:
        return right
    if left_has_reset and not right_has_reset:
        return left

    if left.segment_type == SEGMENT_TYPE_UNKNOWN and right.segment_type != SEGMENT_TYPE_UNKNOWN:
        return right
    if right.segment_type == SEGMENT_TYPE_UNKNOWN and left.segment_type != SEGMENT_TYPE_UNKNOWN:
        return left

    return left


def _build_segments_from_candidates(
    *,
    document_id: str,
    elements: list[dict[str, Any]],
    candidates: list[_BoundaryCandidate],
) -> list[SegmentDocument]:
    boundaries = [0] + [c.element_index for c in candidates]
    boundaries = sorted(set(boundaries))

    segments: list[SegmentDocument] = []

    for order, start_idx in enumerate(boundaries):
        end_idx = boundaries[order + 1] if order + 1 < len(boundaries) else len(elements)
        if start_idx >= end_idx:
            continue

        segment_slice = elements[start_idx:end_idx]
        page_start = _safe_page(segment_slice[0]) if segment_slice else 1
        page_end = _safe_page(segment_slice[-1]) if segment_slice else page_start

        if order == 0:
            boundary_candidate = None
            segment_type = _infer_first_segment_type(elements, candidates)
            segment_title = _infer_first_segment_title(elements)
            confidence_score = 1.0 if segment_type == SEGMENT_TYPE_CONTRACT else 0.75
        else:
            boundary_candidate = next(
                (c for c in candidates if c.element_index == start_idx),
                None,
            )
            segment_type = boundary_candidate.segment_type if boundary_candidate else SEGMENT_TYPE_UNKNOWN
            segment_title = boundary_candidate.title if boundary_candidate else None
            confidence_score = boundary_candidate.confidence_score if boundary_candidate else 0.60

        segment = SegmentDocument(
            segment_id=make_segment_id(document_id=document_id, segment_order=order),
            document_id=document_id,
            document_version_id=None,
            segment_order=order,
            segment_type=segment_type,
            segment_title=segment_title,
            page_start=page_start,
            page_end=page_end,
            element_start=start_idx,
            element_end=end_idx,
            confidence=_confidence_label(confidence_score),
            is_primary=False,
        )

        segment.segmentation_confidence_score = round(confidence_score, 3)
        segment.segmentation_reasons = (
            list(boundary_candidate.reasons)
            if boundary_candidate
            else ["file_start"]
        )

        segments.append(segment)

    return segments


def _assign_primary_segment(segments: list[SegmentDocument]) -> None:
    if not segments:
        return

    for s in segments:
        s.is_primary = False

    contracts_high = [
        s for s in segments
        if s.segment_type == SEGMENT_TYPE_CONTRACT and s.confidence == SEGMENT_CONFIDENCE_HIGH
    ]
    if contracts_high:
        contracts_high[0].is_primary = True
        return

    contracts_any = [s for s in segments if s.segment_type == SEGMENT_TYPE_CONTRACT]
    if contracts_any:
        contracts_any[0].is_primary = True
        return

    segments[0].is_primary = True


def _attach_scope_names(segments: list[SegmentDocument]) -> None:
    """
    Формирует scope_name по типу и порядку в пределах типа.
    """
    type_counters: dict[str, int] = defaultdict(int)

    for seg in segments:
        seg_type = seg.segment_type or SEGMENT_TYPE_UNKNOWN

        if seg_type == SEGMENT_TYPE_CONTRACT and seg.segment_order == 0:
            seg.scope_name = "main_contract"
            continue

        type_counters[seg_type] += 1
        seg.scope_name = _generate_scope_name(
            segment_type=seg_type,
            index_within_type=type_counters[seg_type],
        )


def _propagate_segment_metadata(
    *,
    elements: list[dict[str, Any]],
    segments: list[SegmentDocument],
) -> None:
    """
    Проставляет segment metadata в каждый element.
    """
    for seg in segments:
        for idx in range(seg.element_start, seg.element_end):
            if idx >= len(elements):
                continue

            el = elements[idx]
            el["segment_id"] = seg.segment_id
            el["segment_type"] = seg.segment_type
            el["segment_order"] = seg.segment_order
            el["scope"] = getattr(seg, "scope_name", None) or "unknown_scope"


def _make_single_segment(
    *,
    document_id: str,
    elements: list[dict[str, Any]],
) -> SegmentDocument:
    if elements:
        page_start = _safe_page(elements[0])
        page_end = _safe_page(elements[-1])
        inferred_type = _infer_first_segment_type(elements, [])
        if inferred_type == SEGMENT_TYPE_UNKNOWN:
            inferred_type = SEGMENT_TYPE_CONTRACT
        inferred_title = _infer_first_segment_title(elements)
    else:
        page_start = 1
        page_end = 1
        inferred_type = SEGMENT_TYPE_CONTRACT
        inferred_title = None

    segment = SegmentDocument(
        segment_id=make_segment_id(document_id=document_id, segment_order=0),
        document_id=document_id,
        document_version_id=None,
        segment_order=0,
        segment_type=inferred_type,
        segment_title=inferred_title,
        page_start=page_start,
        page_end=page_end,
        element_start=0,
        element_end=len(elements),
        confidence=SEGMENT_CONFIDENCE_HIGH,
        is_primary=True,
    )
    segment.scope_name = "main_contract"
    segment.segmentation_confidence_score = 1.0
    segment.segmentation_reasons = ["single_segment_mode"]
    return segment


def _match_boundary_marker(text: str) -> str | None:
    if _APPENDIX_RE.match(text):
        return "appendix"
    if _AMENDMENT_RE.match(text):
        return "amendment"
    if _ACT_RE.match(text):
        return "act"
    if _INVOICE_RE.match(text):
        return "invoice"
    if _PROTOCOL_RE.match(text):
        return "protocol"
    return None


def _infer_segment_type_from_text(text: str) -> str:
    if _APPENDIX_RE.match(text):
        return SEGMENT_TYPE_APPENDIX
    if _AMENDMENT_RE.match(text):
        return SEGMENT_TYPE_AMENDMENT
    if _ACT_RE.match(text):
        return SEGMENT_TYPE_ACT
    if _INVOICE_RE.match(text):
        return SEGMENT_TYPE_INVOICE
    if _PROTOCOL_RE.match(text):
        return SEGMENT_TYPE_PROTOCOL
    return SEGMENT_TYPE_UNKNOWN


def _infer_segment_title(text: str) -> str | None:
    title = normalize_spaces(text)
    return title or None


def _infer_first_segment_type(
    elements: list[dict[str, Any]],
    candidates: list[_BoundaryCandidate],
) -> str:
    if any(
        c.segment_type in {
            SEGMENT_TYPE_APPENDIX,
            SEGMENT_TYPE_AMENDMENT,
            SEGMENT_TYPE_ACT,
            SEGMENT_TYPE_INVOICE,
            SEGMENT_TYPE_PROTOCOL,
        }
        for c in candidates
    ):
        return SEGMENT_TYPE_CONTRACT

    for el in elements[:12]:
        if _is_non_boundary_element_type(el):
            continue

        text = normalize_spaces(str(el.get("text", "") or "")).lower()
        if not text:
            continue

        if "contract" in text or "договор" in text or "agreement" in text:
            return SEGMENT_TYPE_CONTRACT

    return SEGMENT_TYPE_UNKNOWN


def _infer_first_segment_title(elements: list[dict[str, Any]]) -> str | None:
    for idx, element in enumerate(elements[:10]):
        if _is_non_boundary_element_type(element) or _is_list_item_element(element):
            continue

        text = normalize_spaces(str(element.get("text", "") or ""))
        if not text:
            continue
        if len(text) > 200:
            continue
        if _looks_like_non_boundary_block(text):
            continue

        if _is_heading_candidate_element(element):
            return text

        if _is_heading_like(text):
            return text

        if idx == 0 and len(text.split()) <= 20:
            return text

    return None


def _safe_page(element: dict[str, Any]) -> int:
    page = element.get("page", 1)
    try:
        return int(page or 1)
    except Exception:
        return 1

def _element_type(element: dict[str, Any]) -> str:
    return str(element.get("element_type") or "").strip().lower()

def _is_non_boundary_element_type(element: dict[str, Any]) -> bool:
    element_type = _element_type(element)
    return element_type in {
        "signature_block",
        "requisites_block",
        "toc_content",
        "page_artifact",
        "table_content",
        "unknown_layout",
    }

def _is_heading_candidate_element(element: dict[str, Any]) -> bool:
    return _element_type(element) == "heading_candidate"

def _is_list_item_element(element: dict[str, Any]) -> bool:
    return _element_type(element) == "list_item"

def _page_offset(elements: list[dict[str, Any]], index: int) -> int:
    current_page = _safe_page(elements[index])
    offset = 0
    for i in range(index - 1, -1, -1):
        if _safe_page(elements[i]) != current_page:
            break
        offset += 1
    return offset


def _is_heading_like(text: str) -> bool:
    text = normalize_spaces(text)
    if not text:
        return False
    if _looks_like_non_boundary_block(text):
        return False

    parsed = _safe_parse_heading(text)
    if parsed:
        uid, title = parsed
        try:
            result = score_heading_candidate(
                uid=uid,
                title=title,
                raw_text=text,
            )
            return result.status in (CandidateStatus.ACCEPTED, CandidateStatus.AMBIGUOUS)
        except Exception:
            pass

    words = text.split()
    if 1 <= len(words) <= 10 and len(text) <= 100:
        if text.isupper():
            return True
        if text.endswith(":"):
            return True
        if words[0][:1].isdigit():
            return True

    return False


def _safe_parse_heading(text: str) -> tuple[str, str] | None:
    text = normalize_spaces(text)
    if not text:
        return None

    match = re.match(r"^(\d+(?:\.\d+)*)\.?\s+(.+)$", text)
    if match:
        return match.group(1), match.group(2)

    roman = re.match(r"^([IVXLCM]+)\.?\s+(.+)$", text, re.IGNORECASE)
    if roman:
        return roman.group(1), roman.group(2)

    letter = re.match(r"^([A-ZА-ЯЁ])[\.\)]\s+(.+)$", text, re.IGNORECASE)
    if letter:
        return letter.group(1), letter.group(2)

    return None


def _is_boundary_position(
    elements: list[dict[str, Any]],
    index: int,
    text: str,
) -> bool:
    element = elements[index]
    offset = _page_offset(elements, index)

    if offset < _NEW_PAGE_HEADING_WINDOW:
        return True

    if _is_heading_candidate_element(element):
        return True

    if _is_list_item_element(element):
        return False

    if _is_heading_like(text):
        return True

    if _looks_like_segment_start_context(elements, index):
        return True

    return False


def _looks_like_mid_paragraph_reference(
    elements: list[dict[str, Any]],
    candidate: _BoundaryCandidate,
) -> bool:
    idx = candidate.element_index
    text = candidate.text.lower()

    if len(text.split()) > 16:
        return True

    prev_text = ""
    if idx > 0:
        prev_text = normalize_spaces(str(elements[idx - 1].get("text", "") or "")).lower()

    next_text = ""
    if idx + 1 < len(elements):
        next_text = normalize_spaces(str(elements[idx + 1].get("text", "") or "")).lower()

    if prev_text and not prev_text.endswith((".", ":", ";")) and _page_offset(elements, idx) > 0:
        if "appendix" in text or "приложение" in text or "акт" in text or "протокол" in text:
            return True

    if text.startswith(("see appendix", "see annex", "см. приложение", "согласно приложению")):
        return True

    if next_text and len(candidate.text.split()) > 8 and len(next_text.split()) > 8:
        return True

    return False


def _detect_local_numbering_reset(
    elements: list[dict[str, Any]],
    index: int,
) -> dict[str, Any] | None:
    prev_uids: list[str] = []
    next_uids: list[str] = []

    for i in range(max(0, index - 12), index):
        if _is_non_boundary_element_type(elements[i]) or _is_list_item_element(elements[i]):
            continue
        parsed = _safe_parse_heading(normalize_spaces(str(elements[i].get("text", "") or "")))
        if parsed:
            prev_uids.append(parsed[0])

    for i in range(index, min(len(elements), index + 8)):
        if _is_non_boundary_element_type(elements[i]) or _is_list_item_element(elements[i]):
            continue
        parsed = _safe_parse_heading(normalize_spaces(str(elements[i].get("text", "") or "")))
        if parsed:
            next_uids.append(parsed[0])

    if not prev_uids or not next_uids:
        return None

    prev_has_progression = any(uid not in {"1", "1.1", "I", "A"} for uid in prev_uids)
    next_has_reset = any(uid in {"1", "1.1", "I", "A"} for uid in next_uids)

    if prev_has_progression and next_has_reset:
        return {
            "prev_uids_sample": prev_uids[-5:],
            "next_uids_sample": next_uids[:5],
        }

    return None


def _detect_formatting_shift(
    elements: list[dict[str, Any]],
    index: int,
) -> dict[str, Any] | None:
    current = elements[index]
    fmt = current.get("formatting") or {}
    if not isinstance(fmt, dict):
        return None

    is_all_caps = bool(fmt.get("is_all_caps"))
    is_centered = bool(fmt.get("is_centered"))
    font_size = fmt.get("font_size")

    strong_visual = is_all_caps or is_centered or (
        isinstance(font_size, (int, float)) and font_size >= 13
    )

    if strong_visual:
        return {
            "is_all_caps": is_all_caps,
            "is_centered": is_centered,
            "font_size": font_size,
        }

    return None


def _detect_heading_density_shift(
    elements: list[dict[str, Any]],
    index: int,
) -> dict[str, Any] | None:
    before = 0
    after = 0

    for i in range(max(0, index - 8), index):
        if _is_non_boundary_element_type(elements[i]) or _is_list_item_element(elements[i]):
            continue
        if _is_heading_candidate_element(elements[i]):
            before += 1
            continue
        text = normalize_spaces(str(elements[i].get("text", "") or ""))
        if text and _is_heading_like(text):
            before += 1

    for i in range(index, min(len(elements), index + 8)):
        if _is_non_boundary_element_type(elements[i]) or _is_list_item_element(elements[i]):
            continue
        if _is_heading_candidate_element(elements[i]):
            after += 1
            continue
        text = normalize_spaces(str(elements[i].get("text", "") or ""))
        if text and _is_heading_like(text):
            after += 1

    if after >= before + 2 and after >= 2:
        return {"before": before, "after": after}

    return None


def _looks_like_segment_start_context(
    elements: list[dict[str, Any]],
    index: int,
) -> bool:
    current_page = _safe_page(elements[index])

    before_same_page = 0
    for i in range(index - 1, -1, -1):
        if _safe_page(elements[i]) != current_page:
            break
        before_same_page += 1

    return before_same_page <= 2


def _looks_like_non_boundary_block(text: str) -> bool:
    text = normalize_spaces(text)
    if not text:
        return True
    if _SIGNATURE_LINE_RE.match(text):
        return True
    if _REQUISITES_LINE_RE.match(text):
        return True
    return False


def _confidence_label(score: float) -> str:
    if score >= 0.80:
        return SEGMENT_CONFIDENCE_HIGH
    if score >= 0.60:
        return SEGMENT_CONFIDENCE_MEDIUM
    return SEGMENT_CONFIDENCE_LOW


def _generate_scope_name(
    *,
    segment_type: str,
    index_within_type: int,
) -> str:
    segment_type = (segment_type or SEGMENT_TYPE_UNKNOWN).strip().lower()

    allowed = {
        SEGMENT_TYPE_CONTRACT,
        SEGMENT_TYPE_APPENDIX,
        SEGMENT_TYPE_ACT,
        SEGMENT_TYPE_AMENDMENT,
        SEGMENT_TYPE_INVOICE,
        SEGMENT_TYPE_PROTOCOL,
        SEGMENT_TYPE_UNKNOWN,
    }
    if segment_type not in allowed:
        segment_type = SEGMENT_TYPE_UNKNOWN

    segment_type = re.sub(r"[^a-z0-9_]+", "_", segment_type).strip("_") or "unknown"
    return f"{segment_type}_{index_within_type}"


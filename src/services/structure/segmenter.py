# src/services/structure/segmenter.py

"""
Deterministic segmentation of a physical file into logical document segments.

Для непрофессионального программиста:
Этот модуль пытается понять, состоит ли один PDF/DOCX файл из нескольких
логических документов: например, "договор + приложение", "договор + акт",
"договор + счет" и т.д.

На вход подается весь список elements[] из layout.
На выходе — список SegmentDocument.

Главные принципы:
- Алгоритм консервативный: если не уверен — не режет файл.
- Алгоритм детерминированный: одинаковый input -> одинаковый output.
- Алгоритм никогда не должен ломать пайплайн:
  любые внутренние ошибки -> fallback к одному сегменту.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from core.logging import get_logger
from services.structure.heading_patterns import normalize_spaces
from services.structure.heading_scoring import score_heading_candidate, CandidateStatus
from services.structure.models import (
    SegmentDocument,
    SEGMENT_TYPE_ACT,
    SEGMENT_TYPE_AMENDMENT,
    SEGMENT_TYPE_APPENDIX,
    SEGMENT_TYPE_CONTRACT,
    SEGMENT_TYPE_INVOICE,
    SEGMENT_TYPE_UNKNOWN,
    make_segment_id,
)

logger = get_logger(__name__)

_MIN_ELEMENTS_BETWEEN_BOUNDARIES = 3
_MAX_REASONABLE_SEGMENTS = 15
_NEW_PAGE_HEADING_WINDOW = 3


@dataclass(frozen=True)
class _BoundaryCandidate:
    """
    Внутренняя техническая модель кандидата на границу сегмента.

    Для непрофессионального программиста:
    Если мы видим подозрительное место в документе (например, на новой странице
    строку 'Appendix 1' или 'Приложение №1'), мы сначала считаем это только
    кандидатом. Потом отдельно решаем, настоящая это граница или ложное
    срабатывание.
    """

    element_index: int
    page: int
    text: str
    segment_type: str
    title: str | None
    confidence: str


# ---------------------------------------------------------------------------
# Публичная точка входа
# ---------------------------------------------------------------------------


def segment_elements(
    document_id: str,
    elements: list[dict[str, Any]],
) -> list[SegmentDocument]:
    """
    Splits elements[] into logical SegmentDocuments.

    Для непрофессионального программиста:
    Эта функция получает весь layout файла и пытается разделить его
    на логические документы.

    Примеры:
    - один договор -> [1 сегмент]
    - договор + приложение -> [contract, appendix]
    - договор + доп. соглашение + акт -> [contract, amendment, act]

    Важные гарантии:
    - никогда не бросает исключение наружу;
    - всегда возвращает хотя бы один сегмент;
    - если не находит надежных границ — возвращает один сегмент на весь файл.
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


# ---------------------------------------------------------------------------
# Основная реализация
# ---------------------------------------------------------------------------


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

    candidates = _collect_boundary_candidates(clean_elements)
    candidates = _validate_boundary_candidates(clean_elements, candidates)

    if not candidates:
        segments = [_make_single_segment(document_id=document_id, elements=clean_elements)]
        logger.info(
            "STRUCTURE segmenter: no boundaries found, single segment returned",
            extra={
                "document_id": document_id,
                "elements_count": len(clean_elements),
                "segments_count": 1,
            },
        )
        return segments

    segments = _build_segments_from_candidates(
        document_id=document_id,
        elements=clean_elements,
        candidates=candidates,
    )

    if not segments:
        return [_make_single_segment(document_id=document_id, elements=clean_elements)]

    if len(segments) > _MAX_REASONABLE_SEGMENTS:
        logger.warning(
            "STRUCTURE segmenter produced too many segments, falling back to single segment",
            extra={
                "document_id": document_id,
                "segments_count": len(segments),
                "max_reasonable_segments": _MAX_REASONABLE_SEGMENTS,
            },
        )
        return [_make_single_segment(document_id=document_id, elements=clean_elements)]

    _assign_primary_segment(segments)

    logger.info(
        "STRUCTURE segmenter completed",
        extra={
            "document_id": document_id,
            "elements_count": len(clean_elements),
            "segments_count": len(segments),
            "segment_types": [s.segment_type for s in segments],
        },
    )

    return segments


# ---------------------------------------------------------------------------
# Сбор кандидатов на границы
# ---------------------------------------------------------------------------


def _collect_boundary_candidates(
    elements: list[dict[str, Any]],
) -> list[_BoundaryCandidate]:
    """
    Проходит по elements и ищет места, похожие на начало нового логического документа.

    Ищем только сильные сигналы:
    - явные маркеры типа "Appendix 1", "Приложение №1", "Дополнительное соглашение";
    - только в начале страницы или очень близко к нему;
    - желательно если строка похожа на heading.
    """
    candidates: list[_BoundaryCandidate] = []

    for idx, element in enumerate(elements):
        raw_text = element.get("text", "")
        text = normalize_spaces(str(raw_text or ""))
        if not text:
            continue

        page = _safe_page(element)
        page_offset = _page_offset(elements, idx)

        if page_offset >= _NEW_PAGE_HEADING_WINDOW and not _is_heading_like(text):
            continue

        marker_match = _match_boundary_marker(text)
        if not marker_match:
            continue

        if not _is_boundary_position(elements, idx, text):
            continue

        seg_type = _infer_segment_type_from_text(text)
        title = _infer_segment_title(text)
        confidence = "HIGH" if page_offset == 0 else "MEDIUM"

        candidates.append(
            _BoundaryCandidate(
                element_index=idx,
                page=page,
                text=text,
                segment_type=seg_type,
                title=title,
                confidence=confidence,
            )
        )

    return candidates


def _validate_boundary_candidates(
    elements: list[dict[str, Any]],
    candidates: list[_BoundaryCandidate],
) -> list[_BoundaryCandidate]:
    """
    Фильтрует ложные срабатывания.

    Правила:
    - границы не должны стоять слишком близко друг к другу;
    - граница в середине текстового абзаца отбрасывается;
    - если кандидат слабый и слишком "шумный", лучше пропустить.
    """
    if not candidates:
        return []

    validated: list[_BoundaryCandidate] = []

    for candidate in candidates:
        if candidate.element_index <= 0:
            continue

        if validated:
            prev = validated[-1]
            if candidate.element_index - prev.element_index < _MIN_ELEMENTS_BETWEEN_BOUNDARIES:
                continue

        if _looks_like_mid_paragraph_reference(elements, candidate):
            continue

        validated.append(candidate)

    return validated


# ---------------------------------------------------------------------------
# Построение сегментов
# ---------------------------------------------------------------------------


def _build_segments_from_candidates(
    *,
    document_id: str,
    elements: list[dict[str, Any]],
    candidates: list[_BoundaryCandidate],
) -> list[SegmentDocument]:
    """
    По подтвержденным boundary candidates строит готовые SegmentDocument.
    """
    boundaries = [0] + [c.element_index for c in candidates]
    boundaries = sorted(set(boundaries))

    segments: list[SegmentDocument] = []

    for order, start_idx in enumerate(boundaries):
        end_idx = boundaries[order + 1] if order + 1 < len(boundaries) else len(elements)
        if start_idx >= end_idx:
            continue

        segment_elements_slice = elements[start_idx:end_idx]
        page_start = _safe_page(segment_elements_slice[0]) if segment_elements_slice else 1
        page_end = _safe_page(segment_elements_slice[-1]) if segment_elements_slice else page_start

        if order == 0:
            boundary_candidate = None
            segment_type = _infer_first_segment_type(elements, candidates)
            segment_title = _infer_first_segment_title(elements)
            confidence = "HIGH" if segment_type == SEGMENT_TYPE_CONTRACT else "MEDIUM"
        else:
            boundary_candidate = next(
                (c for c in candidates if c.element_index == start_idx),
                None,
            )
            segment_type = boundary_candidate.segment_type if boundary_candidate else SEGMENT_TYPE_UNKNOWN
            segment_title = boundary_candidate.title if boundary_candidate else None
            confidence = boundary_candidate.confidence if boundary_candidate else "MEDIUM"

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
            confidence=confidence,
            is_primary=False,
        )
        segments.append(segment)

    return segments


def _assign_primary_segment(segments: list[SegmentDocument]) -> None:
    """
    Правило primary segment:
    - первый contract с HIGH confidence;
    - иначе первый contract;
    - иначе первый по порядку.
    """
    if not segments:
        return

    for s in segments:
        s.is_primary = False

    contracts_high = [
        s for s in segments
        if s.segment_type == SEGMENT_TYPE_CONTRACT and s.confidence == "HIGH"
    ]
    if contracts_high:
        contracts_high[0].is_primary = True
        return

    contracts_any = [s for s in segments if s.segment_type == SEGMENT_TYPE_CONTRACT]
    if contracts_any:
        contracts_any[0].is_primary = True
        return

    segments[0].is_primary = True


# ---------------------------------------------------------------------------
# Fallback single segment
# ---------------------------------------------------------------------------


def _make_single_segment(
    *,
    document_id: str,
    elements: list[dict[str, Any]],
) -> SegmentDocument:
    """
    Безопасный fallback: весь файл = один сегмент.
    """
    if elements:
        page_start = _safe_page(elements[0])
        page_end = _safe_page(elements[-1])
    else:
        page_start = 1
        page_end = 1

    return SegmentDocument(
        segment_id=make_segment_id(document_id=document_id, segment_order=0),
        document_id=document_id,
        document_version_id=None,
        segment_order=0,
        segment_type=SEGMENT_TYPE_UNKNOWN,
        segment_title=None,
        page_start=page_start,
        page_end=page_end,
        element_start=0,
        element_end=len(elements),
        confidence="HIGH",
        is_primary=True,
    )


# ---------------------------------------------------------------------------
# Определение типов и заголовков
# ---------------------------------------------------------------------------


_APPENDIX_RE = re.compile(
    r"^(appendix\s+\w+|schedule\s+\w+|exhibit\s+\w+|annex\s+\w+|приложение\s+[№n]?\s*\d+)",
    re.IGNORECASE,
)

_AMENDMENT_RE = re.compile(
    r"^(addendum\s+\w+|amendment\s+(?:no\.?\s*)?\w+|supplemental agreement|дополнительное\s+соглашение(?:\s*[№n]?\s*\d+)?)",
    re.IGNORECASE,
)

_ACT_RE = re.compile(
    r"^(акт\s+(?:приема|приёма|сдачи|выполненных)|acceptance act|delivery act)",
    re.IGNORECASE,
)

_INVOICE_RE = re.compile(
    r"^(счет\s*(?:на\s+оплату)?|счёт\s*(?:на\s+оплату)?|invoice)\b",
    re.IGNORECASE,
)

_HORIZONTAL_RULE_RE = re.compile(r"^\s*-{3,}\s*$")


def _match_boundary_marker(text: str) -> bool:
    return bool(
        _APPENDIX_RE.match(text)
        or _AMENDMENT_RE.match(text)
        or _ACT_RE.match(text)
        or _INVOICE_RE.match(text)
        or _HORIZONTAL_RULE_RE.match(text)
    )


def _infer_segment_type_from_text(text: str) -> str:
    if _APPENDIX_RE.match(text):
        return SEGMENT_TYPE_APPENDIX
    if _AMENDMENT_RE.match(text):
        return SEGMENT_TYPE_AMENDMENT
    if _ACT_RE.match(text):
        return SEGMENT_TYPE_ACT
    if _INVOICE_RE.match(text):
        return SEGMENT_TYPE_INVOICE
    return SEGMENT_TYPE_UNKNOWN


def _infer_segment_title(text: str) -> str | None:
    title = normalize_spaces(text)
    return title or None


def _infer_first_segment_type(
    elements: list[dict[str, Any]],
    candidates: list[_BoundaryCandidate],
) -> str:
    """
    Логика для первого сегмента:
    - если потом есть явные appendix/amendment/act/invoice, то первый сегмент
      чаще всего является contract;
    - иначе unknown.
    """
    if any(c.segment_type in {
        SEGMENT_TYPE_APPENDIX,
        SEGMENT_TYPE_AMENDMENT,
        SEGMENT_TYPE_ACT,
        SEGMENT_TYPE_INVOICE,
    } for c in candidates):
        return SEGMENT_TYPE_CONTRACT

    first_text = normalize_spaces(str(elements[0].get("text", "") if elements else ""))
    if "contract" in first_text.lower() or "договор" in first_text.lower():
        return SEGMENT_TYPE_CONTRACT

    return SEGMENT_TYPE_UNKNOWN


def _infer_first_segment_title(elements: list[dict[str, Any]]) -> str | None:
    """
    Пытаемся взять первый разумный короткий заголовок файла.
    """
    for idx, element in enumerate(elements[:10]):
        text = normalize_spaces(str(element.get("text", "") or ""))
        if not text:
            continue
        if len(text) > 200:
            continue
        if _is_heading_like(text):
            return text
        if idx == 0 and len(text.split()) <= 20:
            return text
    return None


# ---------------------------------------------------------------------------
# Heuristics helpers
# ---------------------------------------------------------------------------


def _safe_page(element: dict[str, Any]) -> int:
    page = element.get("page", 1)
    try:
        return int(page or 1)
    except Exception:
        return 1


def _page_offset(elements: list[dict[str, Any]], index: int) -> int:
    """
    Возвращает позицию элемента внутри своей страницы:
    0 = первый элемент страницы, 1 = второй и т.д.
    """
    current_page = _safe_page(elements[index])
    offset = 0
    for i in range(index - 1, -1, -1):
        if _safe_page(elements[i]) != current_page:
            break
        offset += 1
    return offset


def _is_heading_like(text: str) -> bool:
    """
    Стараемся переиспользовать уже существующую scoring-логику.
    """
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
    if len(words) <= 12 and len(text) <= 120:
        return True

    return False


def _safe_parse_heading(text: str) -> tuple[str, str] | None:
    """
    Локальная упрощённая попытка понять, похож ли текст на heading.

    Здесь не используем полный parse_raw_heading, чтобы segmenter оставался
    чуть более независимым и устойчивым к необычным паттернам.
    """
    text = normalize_spaces(text)
    if not text:
        return None

    match = re.match(r"^(\d+(?:\.\d+)*)\.?\s+(.+)$", text)
    if match:
        return match.group(1), match.group(2)

    return None


def _is_boundary_position(
    elements: list[dict[str, Any]],
    index: int,
    text: str,
) -> bool:
    """
    Разрешаем границу только в сильной позиции:
    - очень близко к началу страницы;
    - или строка явно похожа на heading.
    """
    offset = _page_offset(elements, index)
    if offset < _NEW_PAGE_HEADING_WINDOW:
        return True

    return _is_heading_like(text)


def _looks_like_mid_paragraph_reference(
    elements: list[dict[str, Any]],
    candidate: _BoundaryCandidate,
) -> bool:
    """
    Защита от ложных срабатываний типа:
    'See Appendix 1 for details.'
    внутри обычного текста.
    """
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
        if "appendix" in text or "приложение" in text:
            return True

    if text.startswith(("see appendix", "see annex", "см. приложение", "согласно приложению")):
        return True

    if next_text and len(candidate.text.split()) > 8 and len(next_text.split()) > 8:
        return True

    return False


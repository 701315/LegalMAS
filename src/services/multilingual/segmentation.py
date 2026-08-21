# src/services/multilingual/segmentation.py

"""
Layer 2: Text Segmentation.

Задача:
- разбить multilingual elements на монолингвальные LanguageSegments
  на основе hints из Layer 1;
- извлечь anchor uid из каждого сегмента через existing parse_raw_heading /
  extract_appendix_number;
- классифицировать layout каждой страницы (parallel_columns, interleaved_lines,
  stacked_pairs, stacked_blocks, monolingual, table_page, empty).

НЕ делает:
- не определяет язык сегмента (это задача Layer 3);
- не делает alignment пар (это задача Layer 4);
- не изменяет text сегментов (lossless invariant).

Ключевые инварианты:
1. Lossless split:
   original.text.strip() == " ".join(seg.text for seg in segments).strip()

2. Позиции split из hints корректно разбивают текст:
   left = text[:pos].rstrip(), right = text[pos:].lstrip()

3. Multi-split для элементов с 3+ языками: итеративный split до
   монолингвальности каждой части.

4. Bbox для split-сегментов вычисляется пропорционально длине текста;
   для не-split — оригинальный bbox.

5. Anchor extraction делегируется existing коду без модификаций.

Примеры split из реального документа Simonova SPA:

    Element[43]:
        text: "APPENDIX No. 1 FORM OF THE TRANSFER CERTIFICATE / ПРИЛОЖЕНИЕ № 1 ФОРМА АКТА"
        bbox: [85.15, 405.48, 555.97, 416.48]
        hints: explicit_separator="/", positions=[47]

    → Layer 2 split:
        seg_e43_0: "APPENDIX No. 1 FORM OF THE TRANSFER CERTIFICATE" (EN)
        seg_e43_1: "ПРИЛОЖЕНИЕ № 1 ФОРМА АКТА" (RU)
        bbox_is_approximate=True для обоих

    Element[60]:
        text: "This Real Estate Sale and Purchase Agreement has Настоящий договор..."
        bbox: [55.1, 77.38, 547.19, 88.38]
        hints: script_boundary_positions=(49,)

    → Layer 2 split:
        seg_e60_0: "This Real Estate Sale and Purchase Agreement has" (EN)
        seg_e60_1: "Настоящий договор..." (RU)
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from core.logging import get_logger

# Existing anchor extraction functions — используем через прямые импорты,
# не форкаем и не модифицируем.
from services.structure._segmenter.patterns import extract_appendix_number
from services.structure.heading_patterns import parse_raw_heading

from services.multilingual.models import (
    BBox,
    LanguageSegment,
    NormalizationHints,
    PageLayout,
    PageLayoutType,
    ProcessingWarning,
    SplitReason,
    BboxSplitMethod,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

# Ширина пробела для вычисления gap между split-сегментами (в points).
# Используется для bbox proportional split.
_SPLIT_GAP_WIDTH_PT = 5.0

# Минимальная длина сегмента (символов) чтобы считать split валидным.
# Более короткие сегменты помечаются с low split_confidence.
_MIN_SEGMENT_LENGTH_CHARS = 3

# Threshold для split_confidence.
_SPLIT_CONFIDENCE_HIGH = 0.90     # длинные фрагменты + чёткий separator
_SPLIT_CONFIDENCE_MEDIUM = 0.80   # один сигнал средней силы
_SPLIT_CONFIDENCE_LOW = 0.60      # слабый сигнал или короткие фрагменты

# Максимум итераций multi-split. Защита от бесконечных циклов.
_MAX_SPLIT_ITERATIONS = 4

# ─── Page layout classification thresholds ───────────────────────────────────

# Минимум сегментов на странице для попытки классификации.
_MIN_SEGMENTS_FOR_LAYOUT_CLASSIFICATION = 3

# Ширина колонки для parallel_columns detection.
# Если сегменты на одной Y-строке имеют X0 в двух чётко разных зонах —
# это две колонки.
_COLUMN_GAP_MIN_PT = 30.0

# Y-tolerance для группировки сегментов "на одной строке".
_LINE_Y_TOLERANCE_PT = 5.0

# ---------------------------------------------------------------------------
# Публичный API
# ---------------------------------------------------------------------------


def segment_elements(
    elements: list[dict[str, Any]],
    hints_by_id: dict[str, NormalizationHints],
) -> tuple[list[LanguageSegment], dict[int, PageLayout], list[ProcessingWarning]]:
    """
    Layer 2 entry point.

    Разбить все multilingual elements на монолингвальные LanguageSegments,
    извлечь anchor uid, классифицировать layout каждой страницы.

    Аргументы:
        elements:     raw_layout["elements"] — список dict
        hints_by_id:  результат Layer 1 normalize_elements()

    Возвращает:
        (segments, page_layouts, warnings):
        - segments: list[LanguageSegment] в порядке reading_order_raw
        - page_layouts: dict {page_number → PageLayout}
        - warnings: список ProcessingWarning для audit

    Гарантии:
    - lossless invariant для split;
    - segments отсортированы по (page, top, x0) для деterministic output;
    - никогда не бросает исключений;
    - элементы с ошибками обработки создают минимальный LanguageSegment
      с split_reason="none" и низким split_confidence.

    Для непрофессионального программиста:
    Функция принимает исходные элементы + подсказки из Layer 1 и возвращает
    атомарные языковые сегменты. Если элемент содержал EN+RU текст — на выходе
    будет два сегмента вместо одного.
    """
    if not elements:
        return [], {}, []

    all_segments: list[LanguageSegment] = []
    warnings: list[ProcessingWarning] = []

    # Шаг 1: split каждого элемента на LanguageSegments
    for element in elements:
        if not isinstance(element, dict):
            continue

        element_id = element.get("element_id")
        if not element_id:
            continue

        element_id_str = str(element_id)
        hints = hints_by_id.get(element_id_str)

        if hints is None:
            # Элемент без hints — создаём один сегмент без split
            segment = _make_unsplit_segment(element, sub_index=0)
            if segment:
                all_segments.append(segment)
                warnings.append(
                    ProcessingWarning(
                        warning_type="missing_normalization_hints",
                        element_id=element_id_str,
                        page=_safe_page(element),
                        details={
                            "note": "element processed without Layer 1 hints",
                        },
                    )
                )
            continue

        try:
            element_segments, element_warnings = _split_element_recursive(
                element=element,
                hints=hints,
            )
            all_segments.extend(element_segments)
            warnings.extend(element_warnings)

        except Exception as exc:
            logger.warning(
                "Layer 2 segmentation failed for element",
                element_id=element_id_str,
                error=str(exc),
            )
            # Fallback: создаём один сегмент без split
            fallback_segment = _make_unsplit_segment(element, sub_index=0)
            if fallback_segment:
                all_segments.append(fallback_segment)
            warnings.append(
                ProcessingWarning(
                    warning_type="segmentation_error",
                    element_id=element_id_str,
                    page=_safe_page(element),
                    details={"error": str(exc)},
                )
            )

    # Шаг 2: сортировка сегментов в reading order (deterministic)
    all_segments.sort(key=_reading_order_sort_key)

    # Шаг 3: классификация layout каждой страницы
    page_layouts = _classify_page_layouts(all_segments)

    return all_segments, page_layouts, warnings


# ---------------------------------------------------------------------------
# Рекурсивный split (multi-split support)
# ---------------------------------------------------------------------------


def _split_element_recursive(
    element: dict[str, Any],
    hints: NormalizationHints,
) -> tuple[list[LanguageSegment], list[ProcessingWarning]]:
    """
    Разбить element на LanguageSegments используя hints.

    Multi-split: если после первого split любая часть содержит новые split
    boundaries — разбиваем её тоже. Максимум _MAX_SPLIT_ITERATIONS итераций.

    Возвращает:
        (segments, warnings)
    """
    warnings: list[ProcessingWarning] = []

    if not hints.needs_split:
        # Элемент не требует split — создаём один сегмент
        segment = _make_unsplit_segment(element, sub_index=0)
        return ([segment] if segment else [], warnings)

    # Первый split
    raw_text = element.get("text", "") or ""
    if not isinstance(raw_text, str):
        raw_text = str(raw_text)

    if not raw_text.strip():
        return [], warnings

    # Выбираем primary split position — по приоритету:
    # 1. explicit_separator (наиболее точный)
    # 2. script_boundary (primary signal)
    # 3. digit_letter_boundary (fallback)
    primary_split_pos, primary_split_reason = _select_primary_split(hints)

    if primary_split_pos is None:
        # Странная ситуация: hints.needs_split=True но не смогли выбрать позицию
        warnings.append(
            ProcessingWarning(
                warning_type="split_position_selection_failed",
                element_id=hints.source_element_id,
                page=_safe_page(element),
                details={"hints": _hints_summary(hints)},
            )
        )
        segment = _make_unsplit_segment(element, sub_index=0)
        return ([segment] if segment else [], warnings)

    # Выполняем first split
    parts = _perform_split(raw_text, primary_split_pos, primary_split_reason, hints)

    if not parts or len(parts) < 2:
        # Split не дал 2+ частей — оставляем как есть
        segment = _make_unsplit_segment(element, sub_index=0)
        return ([segment] if segment else [], warnings)

    # Multi-split: проверяем каждую часть на дальнейшие split boundaries
    all_parts = list(parts)
    iteration = 1

    while iteration < _MAX_SPLIT_ITERATIONS:
        new_parts: list[tuple[str, SplitReason, float]] = []
        any_split_happened = False

        for part_text, part_reason, part_confidence in all_parts:
            # Проверяем есть ли ещё split boundaries в этой части
            sub_split_pos, sub_split_reason = _detect_split_in_text(part_text)

            if sub_split_pos is None:
                # Эта часть уже монолингвальна
                new_parts.append((part_text, part_reason, part_confidence))
            else:
                # Разбиваем дальше
                any_split_happened = True
                sub_parts = _perform_split_on_text(
                    part_text, sub_split_pos, sub_split_reason
                )
                if len(sub_parts) < 2:
                    # Split не удался — оставляем как есть
                    new_parts.append((part_text, part_reason, part_confidence))
                else:
                    # Комбинируем reason (первичный + вторичный)
                    combined_reason = part_reason
                    for sub_text, _, sub_conf in sub_parts:
                        new_parts.append((sub_text, combined_reason, sub_conf))

        all_parts = new_parts
        iteration += 1

        if not any_split_happened:
            break

    if iteration >= _MAX_SPLIT_ITERATIONS and len(all_parts) > 5:
        warnings.append(
            ProcessingWarning(
                warning_type="max_split_iterations_reached",
                element_id=hints.source_element_id,
                page=_safe_page(element),
                details={
                    "iterations": iteration,
                    "final_parts_count": len(all_parts),
                },
            )
        )

    # Строим LanguageSegments из финальных parts
    segments = _build_segments_from_parts(
        element=element,
        parts=all_parts,
        primary_split_reason=primary_split_reason,
    )

    # Проверяем lossless invariant
    lossless_ok = _verify_lossless(raw_text, segments)
    if not lossless_ok:
        warnings.append(
            ProcessingWarning(
                warning_type="lossless_invariant_violated",
                element_id=hints.source_element_id,
                page=_safe_page(element),
                details={
                    "original_length": len(raw_text.strip()),
                    "segments_total_length": sum(len(s.text.strip()) for s in segments),
                },
            )
        )

    # Warnings для low-confidence splits
    for segment in segments:
        if segment.split_reason != "none" and segment.split_confidence < _SPLIT_CONFIDENCE_MEDIUM:
            warnings.append(
                ProcessingWarning(
                    warning_type="low_split_confidence",
                    element_id=hints.source_element_id,
                    page=_safe_page(element),
                    details={
                        "segment_id": segment.segment_id,
                        "split_confidence": round(segment.split_confidence, 3),
                        "text_length": len(segment.text),
                    },
                )
            )

    return segments, warnings


# ---------------------------------------------------------------------------
# Split position selection и execution
# ---------------------------------------------------------------------------


def _select_primary_split(
    hints: NormalizationHints,
) -> tuple[int | None, SplitReason]:
    """
    Выбрать primary split position из hints.

    Приоритет:
    1. explicit_separator (наиболее точный)
    2. script_boundary (primary signal)
    3. digit_letter_boundary (fallback)

    Возвращает первую позицию каждого типа (не все).
    Multi-split обрабатывает остальные позиции рекурсивно.
    """
    if hints.explicit_separator_positions:
        return hints.explicit_separator_positions[0], "explicit_separator"

    if hints.script_boundary_positions:
        return hints.script_boundary_positions[0], "script_boundary"

    if hints.digit_letter_boundary_positions:
        return hints.digit_letter_boundary_positions[0], "digit_letter_boundary"

    return None, "none"


def _perform_split(
    text: str,
    position: int,
    reason: SplitReason,
    hints: NormalizationHints,
) -> list[tuple[str, SplitReason, float]]:
    """
    Выполнить split текста на позиции.

    Для explicit_separator — исключаем сам символ разделителя из результата.
    Для script_boundary / digit_letter — берём чистый slice.

    Возвращает список (text, split_reason, confidence) для каждой части.
    """
    if position <= 0 or position >= len(text):
        return [(text, "none", 1.0)]

    if reason == "explicit_separator":
        # Пропускаем сам символ разделителя
        separator_char = hints.explicit_separator_detected
        if separator_char and position < len(text) and text[position] == separator_char:
            left = text[:position].rstrip()
            right = text[position + 1:].lstrip()
        else:
            # Fallback если separator не совпадает
            left = text[:position].rstrip()
            right = text[position:].lstrip()
    else:
        # script_boundary или digit_letter — position указывает начало правой части
        left = text[:position].rstrip()
        right = text[position:].lstrip()

    if not left or not right:
        return [(text, "none", 1.0)]

    # Вычисляем confidence
    confidence = _compute_split_confidence(left, right, reason)

    return [
        (left, reason, confidence),
        (right, reason, confidence),
    ]


def _perform_split_on_text(
    text: str,
    position: int,
    reason: SplitReason,
) -> list[tuple[str, SplitReason, float]]:
    """
    Простой split на позиции без hints (для recursive multi-split).
    """
    if position <= 0 or position >= len(text):
        return [(text, "none", 1.0)]

    left = text[:position].rstrip()
    right = text[position:].lstrip()

    if not left or not right:
        return [(text, "none", 1.0)]

    confidence = _compute_split_confidence(left, right, reason)

    return [
        (left, reason, confidence),
        (right, reason, confidence),
    ]


def _detect_split_in_text(text: str) -> tuple[int | None, SplitReason]:
    """
    Быстрая детекция split boundary в тексте (для recursive multi-split).

    Не пересчитывает всё через Layer 1 — использует упрощённую логику:
    - ищет только script boundary (primary signal)
    - explicit separator и digit-letter обрабатывает через regex

    Возвращает первую найденную позицию или (None, "none").
    """
    if not text or len(text) < 4:
        return None, "none"

    # Импортируем внутри чтобы избежать циклических зависимостей
    from services.multilingual.normalization import _detect_script_boundaries

    boundaries = _detect_script_boundaries(text)
    if boundaries:
        return boundaries[0], "script_boundary"

    return None, "none"


def _compute_split_confidence(
    left: str,
    right: str,
    reason: SplitReason,
) -> float:
    """
    Вычислить confidence split на основе длины фрагментов и типа signal.

    Правила:
    - explicit_separator: базовая 0.95 (наиболее надёжный)
    - script_boundary: базовая 0.90
    - digit_letter_boundary: базовая 0.80
    - Если хотя бы один фрагмент короче _MIN_SEGMENT_LENGTH_CHARS: снижаем до 0.60
    - Если оба фрагмента длинные (>10 символов): держим базовую
    """
    left_len = len(left.strip())
    right_len = len(right.strip())

    if left_len < _MIN_SEGMENT_LENGTH_CHARS or right_len < _MIN_SEGMENT_LENGTH_CHARS:
        return _SPLIT_CONFIDENCE_LOW

    if reason == "explicit_separator":
        return 0.95
    elif reason == "script_boundary":
        if left_len > 10 and right_len > 10:
            return 0.90
        return _SPLIT_CONFIDENCE_MEDIUM
    elif reason == "digit_letter_boundary":
        return 0.80

    return _SPLIT_CONFIDENCE_MEDIUM


# ---------------------------------------------------------------------------
# Построение LanguageSegment
# ---------------------------------------------------------------------------


def _build_segments_from_parts(
    element: dict[str, Any],
    parts: list[tuple[str, SplitReason, float]],
    primary_split_reason: SplitReason,
) -> list[LanguageSegment]:
    """
    Построить список LanguageSegments из parts после split.

    Каждый LanguageSegment получает:
    - sub_index в порядке появления
    - вычисленный bbox (пропорционально длине текста)
    - извлечённый anchor_uid через existing parse_raw_heading
    - inherited source_element_type
    """
    element_id = str(element.get("element_id", ""))
    source_element_type = str(element.get("type", "text") or "text")
    page = _safe_page(element)
    original_bbox = BBox.from_list(element.get("bbox"))
    reading_order_raw = _extract_reading_order(element)
    confidence = _extract_confidence(element)

    segments: list[LanguageSegment] = []
    total_text_length = sum(len(p[0]) for p in parts)

    if total_text_length == 0:
        return []

    current_x_offset = 0.0

    for sub_index, (part_text, part_reason, part_confidence) in enumerate(parts):
        if not part_text.strip():
            continue

        segment_id = f"seg_{element_id}_{sub_index}"

        # Вычисляем bbox
        if original_bbox.is_zero:
            # Нет оригинального bbox — используем zero
            segment_bbox = original_bbox
            bbox_is_approx = False
            bbox_method: BboxSplitMethod = "original"
        else:
            # Пропорциональный split bbox
            part_ratio = len(part_text) / total_text_length
            part_width = original_bbox.width * part_ratio

            new_x0 = original_bbox.x0 + current_x_offset
            new_x1 = new_x0 + part_width

            segment_bbox = BBox(
                x0=new_x0,
                top=original_bbox.top,
                x1=new_x1,
                bottom=original_bbox.bottom,
            )
            bbox_is_approx = True
            bbox_method = "proportional"

            # Сдвигаем offset для следующего сегмента, добавляя gap
            current_x_offset += part_width + _SPLIT_GAP_WIDTH_PT

        # Извлекаем anchor uid через existing функции
        anchor_uid = _extract_anchor_uid(part_text)

        segment = LanguageSegment(
            segment_id=segment_id,
            source_element_id=element_id,
            sub_index=sub_index,
            text=part_text,
            page=page,
            bbox=segment_bbox,
            bbox_is_approximate=bbox_is_approx,
            bbox_split_method=bbox_method,
            reading_order_raw=reading_order_raw,
            anchor_uid=anchor_uid,
            is_table_cell=False,  # заполним ниже если применимо
            cell_position=None,
            source_element_type=source_element_type,
            split_reason=part_reason,
            split_confidence=part_confidence,
        )

        segments.append(segment)

    return segments


def _make_unsplit_segment(
    element: dict[str, Any],
    sub_index: int,
) -> LanguageSegment | None:
    """
    Создать один LanguageSegment для элемента без split.
    """
    element_id = element.get("element_id")
    if not element_id:
        return None

    raw_text = element.get("text", "") or ""
    if not isinstance(raw_text, str):
        raw_text = str(raw_text)

    if not raw_text.strip():
        return None

    element_id_str = str(element_id)
    segment_id = f"seg_{element_id_str}_{sub_index}"
    page = _safe_page(element)
    bbox = BBox.from_list(element.get("bbox"))
    source_element_type = str(element.get("type", "text") or "text")
    reading_order_raw = _extract_reading_order(element)

    anchor_uid = _extract_anchor_uid(raw_text)

    return LanguageSegment(
        segment_id=segment_id,
        source_element_id=element_id_str,
        sub_index=sub_index,
        text=raw_text,
        page=page,
        bbox=bbox,
        bbox_is_approximate=False,
        bbox_split_method="original",
        reading_order_raw=reading_order_raw,
        anchor_uid=anchor_uid,
        is_table_cell=False,
        cell_position=None,
        source_element_type=source_element_type,
        split_reason="none",
        split_confidence=1.0,
    )


# ---------------------------------------------------------------------------
# Anchor extraction через existing функции
# ---------------------------------------------------------------------------


def _extract_anchor_uid(text: str) -> str | None:
    """
    Извлечь anchor uid используя existing функции.

    Приоритет:
    1. parse_raw_heading — универсальный анализ (numeric, roman, alpha, appendix)
    2. extract_appendix_number — fallback для appendix

    Возвращает string uid или None.

    Примеры:
    - "1. DEFINITIONS" → "1"
    - "1.1 Purpose"    → "1.1"
    - "APPENDIX No. 1 FORM OF THE TRANSFER CERTIFICATE" → "appendix-1"
    - "ПРИЛОЖЕНИЕ № 1 ФОРМА АКТА" → "приложение-1"
    - "Some regular text" → None
    """
    if not text or not text.strip():
        return None

    try:
        # Основной путь через parse_raw_heading
        parsed = parse_raw_heading(text)
        if parsed:
            uid, _ = parsed
            return uid
    except Exception as exc:
        logger.debug(
            "parse_raw_heading failed",
            text_preview=text[:80],
            error=str(exc),
        )

    try:
        # Fallback через extract_appendix_number
        appendix_num = extract_appendix_number(text)
        if appendix_num:
            # extract_appendix_number возвращает только номер ("1", "A"),
            # но не префикс. Для консистентности с parse_raw_heading формируем uid.
            # Не можем достоверно определить язык префикса без regex —
            # возвращаем нейтральный формат.
            return f"appendix-{appendix_num}"
    except Exception as exc:
        logger.debug(
            "extract_appendix_number failed",
            text_preview=text[:80],
            error=str(exc),
        )

    return None


# ---------------------------------------------------------------------------
# Page layout classification
# ---------------------------------------------------------------------------


def _classify_page_layouts(
    segments: list[LanguageSegment],
) -> dict[int, PageLayout]:
    """
    Классифицировать layout каждой страницы на основе распределения segments.

    Возможные типы:
    - parallel_columns: чётко две колонки по X, сегменты выровнены по Y
    - stacked_pairs:    последовательные пары сегментов, каждая на своей Y
    - stacked_blocks:   большие блоки одного скрипта, потом другого (титульный)
    - interleaved_lines: чередование скриптов в reading order
    - monolingual:      все сегменты одного скрипта
    - table_page:       если сегменты явно в табличной сетке
    - empty:            нет сегментов
    - unknown:          не удалось классифицировать
    """
    if not segments:
        return {}

    # Группируем по страницам
    segments_by_page: dict[int, list[LanguageSegment]] = defaultdict(list)
    for seg in segments:
        segments_by_page[seg.page].append(seg)

    layouts: dict[int, PageLayout] = {}

    for page, page_segments in segments_by_page.items():
        if not page_segments:
            layouts[page] = PageLayout(page=page, layout_type="empty", confidence=1.0)
            continue

        if len(page_segments) < _MIN_SEGMENTS_FOR_LAYOUT_CLASSIFICATION:
            # Слишком мало сегментов для классификации — считаем monolingual
            layouts[page] = PageLayout(
                page=page,
                layout_type="monolingual",
                confidence=0.5,
            )
            continue

        layout = _classify_single_page(page, page_segments)
        layouts[page] = layout

    return layouts


def _classify_single_page(
    page: int,
    segments: list[LanguageSegment],
) -> PageLayout:
    """
    Классифицировать layout одной страницы.

    Алгоритм:
    1. Проверить split-siblings: если много сегментов с одинаковым source_element_id
       и разными sub_index — это parallel_columns (склеенные PDF колонки).
    2. Проверить X-распределение: если сегменты кластеризуются в 2 зоны по X —
       parallel_columns.
    3. Проверить последовательные пары одинаковой Y-структуры — stacked_pairs.
    4. Проверить крупные блоки одного скрипта — stacked_blocks.
    5. Проверить чередование скриптов в reading order — interleaved_lines.
    6. Иначе monolingual или unknown.
    """
    # Sort segments by reading order (top, x0)
    sorted_segs = sorted(segments, key=lambda s: (s.bbox.top, s.bbox.x0))

    # Проверка 1: split-siblings (много сегментов с общим source_element_id)
    source_counts: dict[str, int] = defaultdict(int)
    for seg in sorted_segs:
        source_counts[seg.source_element_id] += 1

    split_sibling_pairs = sum(1 for count in source_counts.values() if count >= 2)
    total_source_elements = len(source_counts)

    if total_source_elements > 0 and split_sibling_pairs / total_source_elements > 0.5:
        # Больше половины source elements породили split — parallel_columns
        return _build_parallel_columns_layout(page, sorted_segs)

    # Проверка 2: X-кластеризация в 2 зоны
    left_x_coords = [s.bbox.x0 for s in sorted_segs if not s.bbox.is_zero]
    if left_x_coords:
        x_clusters = _detect_x_clusters(left_x_coords)
        if len(x_clusters) == 2 and _clusters_are_columns(x_clusters):
            return _build_parallel_columns_layout(page, sorted_segs)

    # Проверка 3: stacked_blocks (крупные блоки одного скрипта)
    block_boundaries = _detect_stacked_blocks(sorted_segs)
    if block_boundaries:
        return PageLayout(
            page=page,
            layout_type="stacked_blocks",
            block_boundaries=block_boundaries,
            confidence=0.8,
        )

    # Проверка 4: interleaved lines (чередование по reading order)
    if _is_interleaved(sorted_segs):
        # Собираем последовательность языков (по script)
        interleave_scripts = _extract_script_sequence(sorted_segs)
        return PageLayout(
            page=page,
            layout_type="interleaved_lines",
            interleave_languages=interleave_scripts,
            confidence=0.7,
        )

    # По умолчанию — monolingual (если один скрипт) или unknown
    unique_scripts = set()
    for seg in sorted_segs:
        script = _get_dominant_script(seg.text)
        if script != "other":
            unique_scripts.add(script)

    if len(unique_scripts) <= 1:
        return PageLayout(page=page, layout_type="monolingual", confidence=0.9)

    return PageLayout(page=page, layout_type="unknown", confidence=0.5)


def _build_parallel_columns_layout(
    page: int,
    sorted_segs: list[LanguageSegment],
) -> PageLayout:
    """Построить PageLayout для parallel_columns с X-диапазонами колонок."""
    left_xs: list[float] = []
    right_xs: list[float] = []

    # Определяем медианный x_center для деления на колонки
    all_centers = [s.bbox.x_center for s in sorted_segs if not s.bbox.is_zero]
    if not all_centers:
        return PageLayout(page=page, layout_type="parallel_columns", confidence=0.5)

    median_x = sorted(all_centers)[len(all_centers) // 2]

    for seg in sorted_segs:
        if seg.bbox.is_zero:
            continue
        if seg.bbox.x_center < median_x:
            left_xs.append(seg.bbox.x0)
        else:
            right_xs.append(seg.bbox.x0)

    left_range = (min(left_xs), max(left_xs)) if left_xs else None
    right_range = (min(right_xs), max(right_xs)) if right_xs else None

    return PageLayout(
        page=page,
        layout_type="parallel_columns",
        left_column_x_range=left_range,
        right_column_x_range=right_range,
        confidence=0.85,
    )


def _detect_x_clusters(x_coords: list[float]) -> list[list[float]]:
    """
    Простая кластеризация x_coords с gap-based split.

    Если между двумя соседними отсортированными x есть gap >= _COLUMN_GAP_MIN_PT —
    это граница кластеров.
    """
    if not x_coords:
        return []

    sorted_xs = sorted(x_coords)
    clusters: list[list[float]] = [[sorted_xs[0]]]

    for x in sorted_xs[1:]:
        if x - clusters[-1][-1] >= _COLUMN_GAP_MIN_PT:
            clusters.append([x])
        else:
            clusters[-1].append(x)

    return clusters


def _clusters_are_columns(clusters: list[list[float]]) -> bool:
    """
    Проверить что кластеры соответствуют двум колонкам.
    Каждый кластер должен содержать значимое количество элементов.
    """
    if len(clusters) != 2:
        return False
    return len(clusters[0]) >= 2 and len(clusters[1]) >= 2


def _detect_stacked_blocks(
    sorted_segs: list[LanguageSegment],
) -> list[int]:
    """
    Обнаружить крупные блоки сегментов одного скрипта подряд.

    Возвращает список индексов начал блоков (в sorted_segs), где происходит
    смена доминирующего скрипта.

    Пример: [0, 14] означает "блок 1: сегменты 0-13, блок 2: сегменты 14+".

    Только если найдено 2+ блока размером >= 5 сегментов каждый.
    """
    if len(sorted_segs) < 10:
        return []

    boundaries: list[int] = [0]
    current_script = _get_dominant_script(sorted_segs[0].text)

    for i, seg in enumerate(sorted_segs[1:], start=1):
        seg_script = _get_dominant_script(seg.text)
        if seg_script != "other" and seg_script != current_script:
            boundaries.append(i)
            current_script = seg_script

    if len(boundaries) < 2:
        return []

    # Проверяем что каждый блок значимого размера
    block_sizes = []
    for i in range(len(boundaries) - 1):
        block_sizes.append(boundaries[i + 1] - boundaries[i])
    block_sizes.append(len(sorted_segs) - boundaries[-1])

    if all(size >= 5 for size in block_sizes):
        return boundaries

    return []


def _is_interleaved(sorted_segs: list[LanguageSegment]) -> bool:
    """
    Проверить чередование скриптов в reading order.

    True если больше 60% соседних пар сегментов имеют разные скрипты.
    """
    if len(sorted_segs) < 4:
        return False

    prev_script: str | None = None
    switches = 0
    total_pairs = 0

    for seg in sorted_segs:
        script = _get_dominant_script(seg.text)
        if script == "other":
            continue

        if prev_script is not None:
            total_pairs += 1
            if script != prev_script:
                switches += 1

        prev_script = script

    if total_pairs == 0:
        return False

    return switches / total_pairs > 0.6


def _extract_script_sequence(sorted_segs: list[LanguageSegment]) -> list[str]:
    """
    Извлечь последовательность скриптов для interleaved_lines.

    Дедуплицируется: consecutive одинаковые скрипты сжимаются в один.
    Возвращает первые 10 значений для metadata (не хочется засорять long lists).
    """
    result: list[str] = []
    prev: str | None = None

    for seg in sorted_segs:
        script = _get_dominant_script(seg.text)
        if script == "other":
            continue
        if script != prev:
            result.append(script)
            prev = script

    return result[:10]


def _get_dominant_script(text: str) -> str:
    """
    Быстро определить доминирующий скрипт в тексте.
    Используется для page layout classification.
    """
    if not text:
        return "other"

    from services.multilingual.normalization import _script_of_char

    counts: dict[str, int] = defaultdict(int)
    for ch in text:
        script = _script_of_char(ch)
        if script != "other":
            counts[script] += 1

    if not counts:
        return "other"

    return max(counts.items(), key=lambda x: x[1])[0]


# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------


def _safe_page(element: dict[str, Any]) -> int:
    try:
        page_raw = element.get("page", 0)
        page = int(page_raw)
        return page if page > 0 else 0
    except (TypeError, ValueError):
        return 0


def _extract_reading_order(element: dict[str, Any]) -> int:
    """Извлечь reading_order или вычислить из bbox."""
    raw_order = element.get("reading_order")
    if isinstance(raw_order, int):
        return raw_order

    # Fallback: используем hash bbox+page для деterministic value
    bbox = BBox.from_list(element.get("bbox"))
    page = _safe_page(element)
    return page * 10000 + int(bbox.top * 10) + int(bbox.x0)


def _extract_confidence(element: dict[str, Any]) -> float:
    """Извлечь confidence из элемента, default 1.0."""
    try:
        return float(element.get("confidence", 1.0))
    except (TypeError, ValueError):
        return 1.0


def _reading_order_sort_key(seg: LanguageSegment) -> tuple:
    """Deterministic sort key для сегментов."""
    return (seg.page, seg.bbox.top, seg.bbox.x0, seg.sub_index)


def _verify_lossless(original_text: str, segments: list[LanguageSegment]) -> bool:
    """
    Проверить lossless invariant с учётом что explicit_separator может быть
    удалён при split.

    Правило:
    - все "контентные" символы (буквы + цифры) должны сохраняться;
    - separator характеры "/", "\\", "|", "\\t" могут быть потеряны
      если хотя бы один сегмент был получен через explicit_separator split;
    - whitespace нормализуется одинаково.

    Возвращает True если lossless invariant соблюдён.
    """
    # Проверяем: были ли split по explicit_separator?
    has_separator_split = any(
        seg.split_reason == "explicit_separator" for seg in segments
    )

    def _content_signature(text: str) -> str:
        """
        Извлечь "контентную подпись" текста — только буквы и цифры.
        Если был separator split — также удаляем separator характеры
        из оригинала для честного сравнения.
        """
        # Убираем separator characters из сравнения если был separator split
        if has_separator_split:
            for sep in ("/", "\\", "|", "\t"):
                text = text.replace(sep, "")
        # Нормализуем: только буквы и цифры в нижнем регистре
        return "".join(ch.lower() for ch in text if ch.isalnum())

    original_sig = _content_signature(original_text)
    segments_sig = _content_signature(
        "".join(seg.text for seg in segments if seg.text.strip())
    )

    return original_sig == segments_sig


def _hints_summary(hints: NormalizationHints) -> dict[str, Any]:
    """Компактное представление hints для warnings."""
    return {
        "script_boundary": hints.script_boundary_detected,
        "explicit_separator": hints.explicit_separator_detected,
        "digit_letter": hints.digit_letter_boundary_detected,
    }



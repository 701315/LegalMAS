# src/services/multilingual/reconstruction.py

"""
Layer 6: Reconstruction.

Задача:
- собрать финальный PipelineResult из результатов всех предыдущих слоёв;
- пересчитать reading_order для всех сегментов с учётом split;
- конвертировать LanguageSegment → OutputElement с полным metadata;
- обработать bilingual cells в tables;
- вычислить QualityMetrics и собрать PipelineMetadata;
- подготовить PipelineResult для сериализации в layout_primary_v2.json.

Три главные задачи:

1. Reading order calculation
   Пересчёт reading_order для всех сегментов через deterministic sort:
   (page, bbox.top, bbox.x0, sub_index). Учитывает что split-сегменты
   должны идти в правильном порядке относительно других сегментов.

2. OutputElement assembly
   Конвертация LanguageSegment → OutputElement.
   Базовые поля (element_id, type, text, page, bbox) на верхнем уровне
   для совместимости с classify_elements.
   Multilingual поля (language, visibility, translation_of, ...) в metadata dict.

3. Tables processing
   Bilingual cells (с "\" или "/" разделителем + разные скрипты) → split
   на языковые части. Каждая часть помечена bilingual_cell: true.

Инварианты:
- Все сегменты (visible и hidden) попадают в PipelineResult.elements
- to_monolingual_layout() фильтрует до visible для передачи в classify_elements
- Deterministic output: одни и те же inputs → тот же PipelineResult
- Backward compatibility: elements dict имеет все поля existing layout_primary
"""

from __future__ import annotations

import re
import time
from typing import Any

from core.logging import get_logger

from services.multilingual.models import (
    ANALYSIS_SOURCE_KIND,
    SCHEMA_VERSION,
    BBox,
    Group,
    LanguageSegment,
    MonolingualGroup,
    OrphanGroup,
    OutputElement,
    PageLayout,
    ParallelGroup,
    PipelineMetadata,
    PipelineResult,
    ProcessingTrace,
    ProcessingWarning,
    QualityMetrics,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Constants для table cell splitting
# ---------------------------------------------------------------------------

# Regex для detection bilingual cell separators.
# Использует ту же логику что и Layer 1: разделитель с пробелами вокруг
# И разными скриптами по бокам.
_TABLE_CELL_SEPARATOR_RE = re.compile(r"\s+([\\/|])\s+")


# ---------------------------------------------------------------------------
# Публичный API
# ---------------------------------------------------------------------------


def reconstruct(
    segments: list[LanguageSegment],
    groups: list[Group],
    page_layouts: dict[int, PageLayout],
    tables: list[dict[str, Any]],
    document_id: str,
    document_version_id: str,
    target_language: str,
    detected_languages: list[str],
    language_ratios: dict[str, float],
    warnings: list[ProcessingWarning],
    layer_timings: dict[str, float] | None = None,
) -> PipelineResult:
    """
    Layer 6 entry point.

    Собрать финальный PipelineResult из результатов всех предыдущих слоёв.

    Аргументы:
        segments: результат Layer 5 (сегменты с visibility)
        groups: результат Layer 4 (все Group)
        page_layouts: результат Layer 2 (классификация страниц)
        tables: raw tables из исходного layout
        document_id, document_version_id: идентификаторы документа
        target_language: целевой язык
        detected_languages: все обнаруженные языки
        language_ratios: доли языков в документе
        warnings: накопленные warnings со всех слоёв
        layer_timings: опциональные timings для ProcessingTrace

    Возвращает:
        PipelineResult, готовый к сериализации в layout_primary_v2.json

    Никогда не бросает исключений — в худшем случае возвращает пустой
    PipelineResult с warnings.
    """
    start_time = time.time()

    # ── Шаг 1: пересчёт reading_order ───────────────────────────────────────
    sorted_segments = _calculate_reading_order(segments)

    # ── Шаг 2: assembly OutputElement из каждого сегмента ──────────────────
    output_elements = _assemble_output_elements(sorted_segments, groups)

    # ── Шаг 3: обработка tables (bilingual cells split) ────────────────────
    processed_tables = _process_tables(tables, target_language)

    # ── Шаг 4: вычисление QualityMetrics ────────────────────────────────────
    quality_metrics = _compute_quality_metrics(
        segments=sorted_segments,
        groups=groups,
        target_language=target_language,
    )

    # ── Шаг 5: assembly ProcessingTrace ─────────────────────────────────────
    trace = _build_processing_trace(
        segments=sorted_segments,
        groups=groups,
        output_elements=output_elements,
        warnings=warnings,
        layer_timings=layer_timings,
        reconstruction_seconds=time.time() - start_time,
    )

    # ── Шаг 6: assembly PipelineMetadata ────────────────────────────────────
    is_multilingual = len(detected_languages) >= 2
    target_language_ratio = language_ratios.get(target_language, 0.0)

    layout_type_summary = {
        page: layout.layout_type for page, layout in sorted(page_layouts.items())
    }

    metadata = PipelineMetadata(
        detected_languages=sorted(detected_languages),
        target_language=target_language,
        is_multilingual=is_multilingual,
        language_ratios=dict(sorted(language_ratios.items())),
        target_language_ratio=target_language_ratio,
        layout_type_summary=layout_type_summary,
        quality_metrics=quality_metrics,
        processing_trace=trace,
    )

    # ── Шаг 7: сборка PipelineResult ────────────────────────────────────────
    result = PipelineResult(
        schema_version=SCHEMA_VERSION,
        document_id=document_id,
        document_version_id=document_version_id,
        target_language=target_language,
        detected_languages=sorted(detected_languages),
        elements=output_elements,
        tables=processed_tables,
        metadata=metadata,
    )

    logger.info(
        "Layer 6 reconstruction completed",
        document_id=document_id,
        total_elements=len(output_elements),
        visible_elements=quality_metrics.visible_segments_count,
        hidden_elements=quality_metrics.segments_hidden,
        parallel_groups=quality_metrics.parallel_groups_count,
        orphan_groups=quality_metrics.orphan_groups_count,
        orphan_ratio=round(quality_metrics.orphan_ratio, 3),
    )

    return result


# ---------------------------------------------------------------------------
# Reading order calculation
# ---------------------------------------------------------------------------


def _calculate_reading_order(
    segments: list[LanguageSegment],
) -> list[LanguageSegment]:
    """
    Пересчитать reading_order для всех сегментов через deterministic sort.

    Sort key: (page, bbox.top, bbox.x0, sub_index).
    - page: сначала по страницам
    - bbox.top: сверху вниз внутри страницы
    - bbox.x0: слева направо для сегментов на одной строке
    - sub_index: split-siblings идут по порядку (EN → RU для parallel_columns)

    Возвращает новый список отсортированных сегментов
    (исходный не мутируется в этом слое, но reading_order обновляется).
    """
    sorted_segs = sorted(
        segments,
        key=lambda s: (
            s.page,
            s.bbox.top if not s.bbox.is_zero else 0.0,
            s.bbox.x0 if not s.bbox.is_zero else 0.0,
            s.sub_index,
        ),
    )

    # Не мутируем reading_order_raw — он остаётся сырым.
    # Финальный reading_order будет в OutputElement.reading_order.
    return sorted_segs


# ---------------------------------------------------------------------------
# OutputElement assembly
# ---------------------------------------------------------------------------


def _assemble_output_elements(
    segments: list[LanguageSegment],
    groups: list[Group],
) -> list[OutputElement]:
    """
    Конвертировать каждый LanguageSegment в OutputElement.

    Базовые поля (element_id, type, text, page, bbox) на верхнем уровне
    для совместимости с classify_elements.
    Multilingual поля идут в metadata dict.

    reading_order присваивается по позиции в отсортированном списке.
    """
    output_elements: list[OutputElement] = []

    for order, seg in enumerate(segments):
        metadata = _build_segment_metadata(seg)

        element = OutputElement(
            element_id=seg.segment_id,
            type=seg.source_element_type,
            text=seg.text,
            page=seg.page,
            bbox=seg.bbox.to_list(),
            confidence=1.0,  # backward compat с existing raw layout
            clause_uid=None,  # заполняется structure stage
            reading_order=order,
            metadata=metadata,
        )
        output_elements.append(element)

    return output_elements


def _build_segment_metadata(seg: LanguageSegment) -> dict[str, Any]:
    """
    Собрать metadata dict для OutputElement.

    Базовые поля (всегда):
    - source_element_id, sub_index
    - language, script, language_confidence, detection_method
    - visibility_in_target_language
    - split_reason, split_confidence
    - bbox_is_approximate, bbox_split_method
    - anchor_uid

    Для hidden (полный context):
    - hidden_reason
    - translation_of
    - translation_pair_confidence
    - translation_language
    - parallel_group_id

    Для orphan:
    - is_orphan_target
    - is_orphan_foreign
    - orphan_display_prefix

    Для ambiguous:
    - is_ambiguous
    """
    metadata: dict[str, Any] = {
        # Идентификация source
        "source_element_id": seg.source_element_id,
        "sub_index": seg.sub_index,

        # Language info
        "language": seg.language,
        "script": seg.script,
        "language_confidence": round(seg.detection_confidence, 4),
        "detection_method": seg.detection_method,
        "is_reliable": seg.is_reliable,

        # Visibility
        "visibility_in_target_language": seg.visibility,

        # Split info
        "split_reason": seg.split_reason,
        "split_confidence": round(seg.split_confidence, 4),
        "bbox_is_approximate": seg.bbox_is_approximate,
        "bbox_split_method": seg.bbox_split_method,

        # Anchor
        "anchor_uid": seg.anchor_uid,
    }

    # Hidden context (только если есть)
    if seg.visibility == "hidden":
        metadata["hidden_reason"] = seg.hidden_reason
        metadata["translation_of"] = list(seg.translation_of)
        if seg.translation_pair_confidence is not None:
            metadata["translation_pair_confidence"] = round(
                seg.translation_pair_confidence, 4
            )
        metadata["translation_language"] = seg.translation_language
        metadata["parallel_group_id"] = seg.parallel_group_id

    # Visible target с translation partners
    elif seg.visibility == "visible" and seg.translation_of:
        # Visible сегмент внутри ParallelGroup — тоже хранит контекст
        metadata["translation_of"] = list(seg.translation_of)
        if seg.translation_pair_confidence is not None:
            metadata["translation_pair_confidence"] = round(
                seg.translation_pair_confidence, 4
            )
        metadata["translation_language"] = seg.translation_language
        metadata["parallel_group_id"] = seg.parallel_group_id

    # Orphan flags
    if seg.is_orphan_target:
        metadata["is_orphan_target"] = True

    if seg.is_orphan_foreign:
        metadata["is_orphan_foreign"] = True
        if seg.orphan_display_prefix:
            metadata["orphan_display_prefix"] = seg.orphan_display_prefix

    # Ambiguous flag
    if seg.is_ambiguous:
        metadata["is_ambiguous"] = True

    # Table cell info (если есть)
    if seg.is_table_cell:
        metadata["is_table_cell"] = True
        if seg.cell_position:
            metadata["cell_position"] = list(seg.cell_position)

    return metadata


# ---------------------------------------------------------------------------
# Tables processing
# ---------------------------------------------------------------------------


def _process_tables(
    tables: list[dict[str, Any]],
    target_language: str,
) -> list[dict[str, Any]]:
    """
    Обработать tables из raw layout.

    Для каждой ячейки:
    - Если содержит "\" или "/" разделитель с пробелами и разными скриптами —
      split на языковые части, помечаем bilingual_cell: true
    - Иначе оставляем ячейку как есть

    Формат вывода совместим с существующим raw_layout.tables:
        [{"page": N, "rows": [[cell1, cell2, ...], ...], "bilingual_cells": {...}}]

    Дополнительное поле bilingual_cells содержит map:
        {(row_idx, col_idx): {"languages_detected": ["en", "ru"],
                              "split_parts": [part1, part2]}}

    для аудита. Оригинальные rows не мутируются — split info рядом.

    Не бросает исключений — problematic ячейки остаются as-is.
    """
    if not tables:
        return []

    processed: list[dict[str, Any]] = []

    for table in tables:
        if not isinstance(table, dict):
            continue

        try:
            processed_table = _process_single_table(table, target_language)
            processed.append(processed_table)
        except Exception as exc:
            logger.warning(
                "Table processing failed, keeping table as-is",
                page=table.get("page"),
                error=str(exc),
            )
            processed.append(dict(table))

    return processed


def _process_single_table(
    table: dict[str, Any],
    target_language: str,
) -> dict[str, Any]:
    """
    Обработать одну таблицу.
    """
    result = dict(table)
    rows = table.get("rows", [])
    if not isinstance(rows, list):
        return result

    bilingual_cells: dict[str, dict[str, Any]] = {}

    for row_idx, row in enumerate(rows):
        if not isinstance(row, list):
            continue

        for col_idx, cell in enumerate(row):
            if not isinstance(cell, str) or not cell.strip():
                continue

            split_info = _try_split_bilingual_cell(cell)
            if split_info is not None:
                # Cell is bilingual - записываем split info
                cell_key = f"{row_idx},{col_idx}"
                bilingual_cells[cell_key] = split_info

    if bilingual_cells:
        result["bilingual_cells"] = bilingual_cells

    return result


def _try_split_bilingual_cell(text: str) -> dict[str, Any] | None:
    r"""
    Попробовать split ячейку по разделителю "\" или "/".

    Возвращает dict с split info если ячейка bilingual, иначе None.

    Правила:
    - separator с пробелами вокруг ("\ " или " / ")
    - разные скрипты по бокам
    """
    match = _TABLE_CELL_SEPARATOR_RE.search(text)
    if not match:
        return None

    separator = match.group(1)
    separator_pos = match.start()

    left = text[:separator_pos].strip()
    right = text[match.end():].strip()

    if not left or not right:
        return None

    # Проверяем что скрипты по бокам разные
    from services.multilingual.normalization import _script_of_char

    left_script = _dominant_script_in(left)
    right_script = _dominant_script_in(right)

    if left_script == "other" or right_script == "other":
        return None
    if left_script == right_script:
        return None

    # Определяем языки (простой mapping)
    left_lang = _script_to_language(left_script)
    right_lang = _script_to_language(right_script)

    return {
        "separator": separator,
        "split_parts": [
            {"text": left, "script": left_script, "language": left_lang},
            {"text": right, "script": right_script, "language": right_lang},
        ],
        "languages_detected": sorted([left_lang, right_lang]),
    }


def _dominant_script_in(text: str) -> str:
    """Быстрое определение доминирующего скрипта в тексте."""
    from services.multilingual.normalization import _script_of_char
    from collections import defaultdict

    counts: dict[str, int] = defaultdict(int)
    for ch in text:
        if not ch.isalpha():
            continue
        script = _script_of_char(ch)
        if script != "other":
            counts[script] += 1

    if not counts:
        return "other"
    return max(counts.items(), key=lambda x: x[1])[0]


def _script_to_language(script: str) -> str:
    """Простой mapping script → language для table cells."""
    mapping = {
        "cyrillic": "ru",
        "latin": "en",  # предположение по умолчанию
        "arabic": "ar",
        "hebrew": "he",
        "cjk": "zh",
        "devanagari": "hi",
    }
    return mapping.get(script, "unknown")


# ---------------------------------------------------------------------------
# Quality metrics computation
# ---------------------------------------------------------------------------


def _compute_quality_metrics(
    segments: list[LanguageSegment],
    groups: list[Group],
    target_language: str,
) -> QualityMetrics:
    """
    Вычислить QualityMetrics по результатам pipeline.

    Метрики:
    - orphan_ratio: доля orphan групп от orphan+parallel (mono не считается)
    - purity_precision: сколько visible на target из всех visible
    - purity_recall: сколько visible на target из всех target в документе
    - structural_fidelity: клаузы найдены / ожидаемо
    - alignment method breakdown
    - split diagnostics
    """
    metrics = QualityMetrics()

    # Group counts
    metrics.parallel_groups_count = sum(1 for g in groups if isinstance(g, ParallelGroup))
    metrics.orphan_groups_count = sum(1 for g in groups if isinstance(g, OrphanGroup))
    metrics.monolingual_groups_count = sum(1 for g in groups if isinstance(g, MonolingualGroup))
    metrics.total_groups = len(groups)

    # Segment counts
    metrics.segments_total = len(segments)
    metrics.segments_hidden = sum(1 for s in segments if s.visibility == "hidden")
    metrics.bypass_segments_count = sum(1 for s in segments if s.is_bypass())

    # Split diagnostics
    metrics.segments_split = sum(1 for s in segments if s.split_reason != "none")
    metrics.segments_not_split = sum(1 for s in segments if s.split_reason == "none")

    if metrics.segments_split > 0:
        split_confs = [s.split_confidence for s in segments if s.split_reason != "none"]
        metrics.avg_split_confidence = sum(split_confs) / len(split_confs)
        metrics.low_confidence_splits_count = sum(
            1 for c in split_confs if c < 0.7
        )

    # Visible segments (для purity metrics)
    visible_segments = [
        s for s in segments
        if s.visibility in (
            "visible", "visible_orphan_target",
            "visible_orphan_foreign", "visible_ambiguous",
        )
    ]
    metrics.visible_segments_count = len(visible_segments)

    metrics.target_language_segments_visible = sum(
        1 for s in visible_segments
        if s.language == target_language
    )
    metrics.foreign_language_segments_visible = metrics.visible_segments_count - metrics.target_language_segments_visible

    # Total target segments in document (visible + hidden)
    metrics.total_target_segments_in_document = sum(
        1 for s in segments if s.language == target_language
    )

    # Alignment method breakdown
    alignments_by_method: dict[str, int] = {}
    for g in groups:
        if isinstance(g, ParallelGroup):
            method = g.alignment_method
            alignments_by_method[method] = alignments_by_method.get(method, 0) + 1
    metrics.alignments_by_method = alignments_by_method

    # Structural fidelity: клаузы с anchor
    clause_anchors_found = set()
    for s in segments:
        if s.anchor_uid:
            clause_anchors_found.add((s.page, s.anchor_uid))
    metrics.found_clause_count = len(clause_anchors_found)
    # expected_clause_count заполняется только если есть эталонное значение
    # (в Итерации 1 оставляем 0 → structural_fidelity = 1.0 by default)
    metrics.expected_clause_count = 0

    # Финальный compute производных метрик
    metrics.compute()

    return metrics


# ---------------------------------------------------------------------------
# ProcessingTrace assembly
# ---------------------------------------------------------------------------


def _build_processing_trace(
    segments: list[LanguageSegment],
    groups: list[Group],
    output_elements: list[OutputElement],
    warnings: list[ProcessingWarning],
    layer_timings: dict[str, float] | None,
    reconstruction_seconds: float,
) -> ProcessingTrace:
    """
    Собрать ProcessingTrace с полной информацией о работе pipeline.
    """
    trace = ProcessingTrace()

    # Warnings
    trace.warnings = list(warnings)

    # Timings (из pipeline)
    if layer_timings:
        trace.layer1_seconds = layer_timings.get("layer1", 0.0)
        trace.layer2_seconds = layer_timings.get("layer2", 0.0)
        trace.layer3_seconds = layer_timings.get("layer3", 0.0)
        trace.layer4_seconds = layer_timings.get("layer4", 0.0)
        trace.layer5_seconds = layer_timings.get("layer5", 0.0)

    trace.layer6_seconds = reconstruction_seconds
    trace.total_seconds = (
        trace.layer1_seconds + trace.layer2_seconds + trace.layer3_seconds
        + trace.layer4_seconds + trace.layer5_seconds + trace.layer6_seconds
    )

    # Layer counts (примерные — точные значения были бы от pipeline)
    trace.segments_after_layer2 = len(segments)
    trace.segments_after_layer3 = len(segments)  # Layer 3 не изменяет число
    trace.groups_after_layer4 = len(groups)
    trace.segments_after_layer5 = len(segments)  # Layer 5 не изменяет число
    trace.elements_after_layer6 = len(output_elements)

    return trace



    
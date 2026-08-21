# src/services/multilingual/pipeline.py

"""
Multilingual Pipeline: оркестратор всех 6 слоёв.

Единая публичная функция: run_multilingual_pipeline(raw_layout, target_language).

Последовательность:
    raw_layout
        ↓
    Layer 1: Normalization (hints)
        ↓
    Layer 2: Segmentation (LanguageSegments + PageLayouts)
        ↓
    Layer 3: Classification (language per segment)
        ↓
    Layer 4: Alignment (Groups)
        ↓
    Layer 5: Selection (visibility)
        ↓
    Layer 6: Reconstruction (PipelineResult)
        ↓
    PipelineResult (готов для сериализации в layout_primary_v2.json)

Использование:
    result = run_multilingual_pipeline(
        raw_layout={...},
        target_language="ru",
    )
    # Для аудита — полный result со всеми сегментами:
    full_json = result.to_dict()
    # Для передачи в classify_elements — только visible:
    mono_layout = result.to_monolingual_layout()

Warnings и timings собираются в result.metadata.processing_trace.

Инварианты:
- Никогда не бросает исключений — вернёт PipelineResult даже при частичных сбоях
- Deterministic: одни и те же inputs -> тот же PipelineResult
- Не мутирует raw_layout
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from core.logging import get_logger

from services.multilingual.alignment import align_segments
from services.multilingual.classification import classify_segments
from services.multilingual.models import (
    LanguageSegment,
    PipelineResult,
    ProcessingWarning,
)
from services.multilingual.normalization import normalize_elements
from services.multilingual.reconstruction import reconstruct
from services.multilingual.segmentation import segment_elements
from services.multilingual.selection import apply_visibility

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Публичный API
# ---------------------------------------------------------------------------


def run_multilingual_pipeline(
    raw_layout: dict[str, Any],
    target_language: str,
) -> PipelineResult:
    """
    Запустить полный multilingual pipeline на raw_layout.

    Аргументы:
        raw_layout: результат extract stage. Должен содержать:
            - document_id: str
            - document_version_id: str
            - elements: list[dict] (element_id, text, page, bbox, ...)
            - tables: list[dict] (опционально)
            - metadata: dict (опционально)
        target_language: целевой язык (ISO 639-1: "ru", "en", "ar", ...)

    Возвращает:
        PipelineResult, готовый к сериализации в layout_primary_v2.json.

    Никогда не бросает исключений. При любой ошибке в слое:
    - Логирует warning
    - Использует fallback (например, пустой список сегментов)
    - Продолжает pipeline с оставшимися данными
    - Возвращает PipelineResult с warnings в processing_trace

    Для непрофессионального программиста:
    Функция принимает исходный layout документа (с разметкой на разных языках)
    и целевой язык пользователя. Возвращает layout_primary_v2 - структуру
    с определёнными языками, найденными парами перевода и правильной
    visibility. Результат готов для сохранения в MinIO и передачи в
    существующий classify_elements через to_monolingual_layout().
    """
    start_time = time.time()
    warnings: list[ProcessingWarning] = []
    layer_timings: dict[str, float] = {}

    # ── Извлечение input данных ─────────────────────────────────────────────
    document_id = str(raw_layout.get("document_id", ""))
    document_version_id = str(raw_layout.get("document_version_id", ""))
    elements = _safe_get_list(raw_layout, "elements")
    tables = _safe_get_list(raw_layout, "tables")

    logger.info(
        "Multilingual pipeline started",
        document_id=document_id,
        target_language=target_language,
        total_elements=len(elements),
        total_tables=len(tables),
    )

    # ── Layer 1: Normalization ──────────────────────────────────────────────
    layer1_start = time.time()
    hints_by_id, layer1_warnings = _safe_run(
        lambda: normalize_elements(elements, tables),
        default=({}, []),
        layer_name="layer1_normalization",
        warnings=warnings,
    )
    warnings.extend(layer1_warnings)
    layer_timings["layer1"] = time.time() - layer1_start

    logger.debug(
        "Layer 1 completed",
        document_id=document_id,
        hints_count=len(hints_by_id),
        elapsed=round(layer_timings["layer1"], 3),
    )

    # ── Layer 2: Segmentation ───────────────────────────────────────────────
    layer2_start = time.time()
    segments, page_layouts, layer2_warnings = _safe_run(
        lambda: segment_elements(elements, hints_by_id),
        default=([], {}, []),
        layer_name="layer2_segmentation",
        warnings=warnings,
    )
    warnings.extend(layer2_warnings)
    layer_timings["layer2"] = time.time() - layer2_start

    logger.debug(
        "Layer 2 completed",
        document_id=document_id,
        segments_count=len(segments),
        pages_count=len(page_layouts),
        elapsed=round(layer_timings["layer2"], 3),
    )

    # Если нет сегментов, продолжаем pipeline — Layer 6 всё равно
    # обработает tables и вернёт корректный результат.
    if not segments:
        logger.warning(
            "Multilingual pipeline: no segments after Layer 2, "
            "continuing with tables-only processing",
            document_id=document_id,
        )
        # Инициализируем пустые defaults для последующих слоёв
        warnings.append(
            ProcessingWarning(
                warning_type="no_segments_after_layer2",
                details={"note": "pipeline continues with tables processing only"},
            )
        )

    # ── Layer 3: Classification ─────────────────────────────────────────────
    layer3_start = time.time()
    segments, layer3_warnings = _safe_run(
        lambda: classify_segments(segments),
        default=(segments, []),
        layer_name="layer3_classification",
        warnings=warnings,
    )
    warnings.extend(layer3_warnings)
    layer_timings["layer3"] = time.time() - layer3_start

    # Вычисляем language ratios и detected_languages ПОСЛЕ Layer 3
    detected_languages, language_ratios = _compute_language_stats(segments)

    logger.debug(
        "Layer 3 completed",
        document_id=document_id,
        detected_languages=detected_languages,
        language_ratios={k: round(v, 3) for k, v in language_ratios.items()},
        elapsed=round(layer_timings["layer3"], 3),
    )

    # ── Layer 4: Alignment ──────────────────────────────────────────────────
    layer4_start = time.time()
    groups, layer4_warnings = _safe_run(
        lambda: align_segments(segments, page_layouts, target_language),
        default=([], []),
        layer_name="layer4_alignment",
        warnings=warnings,
    )
    warnings.extend(layer4_warnings)
    layer_timings["layer4"] = time.time() - layer4_start

    logger.debug(
        "Layer 4 completed",
        document_id=document_id,
        groups_count=len(groups),
        elapsed=round(layer_timings["layer4"], 3),
    )

    # ── Layer 5: Selection ──────────────────────────────────────────────────
    layer5_start = time.time()
    segments, layer5_warnings = _safe_run(
        lambda: apply_visibility(segments, groups, target_language),
        default=(segments, []),
        layer_name="layer5_selection",
        warnings=warnings,
    )
    warnings.extend(layer5_warnings)
    layer_timings["layer5"] = time.time() - layer5_start

    logger.debug(
        "Layer 5 completed",
        document_id=document_id,
        elapsed=round(layer_timings["layer5"], 3),
    )

    # ── Layer 6: Reconstruction ─────────────────────────────────────────────
    result = _safe_run(
        lambda: reconstruct(
            segments=segments,
            groups=groups,
            page_layouts=page_layouts,
            tables=tables,
            document_id=document_id,
            document_version_id=document_version_id,
            target_language=target_language,
            detected_languages=detected_languages,
            language_ratios=language_ratios,
            warnings=warnings,
            layer_timings=layer_timings,
        ),
        default=_build_empty_result(
            document_id=document_id,
            document_version_id=document_version_id,
            target_language=target_language,
            tables=tables,
            warnings=warnings,
            layer_timings=layer_timings,
        ),
        layer_name="layer6_reconstruction",
        warnings=warnings,
    )

    total_elapsed = time.time() - start_time

    logger.info(
        "Multilingual pipeline completed",
        document_id=document_id,
        target_language=target_language,
        detected_languages=detected_languages,
        total_elements=len(result.elements),
        visible_elements=result.metadata.quality_metrics.visible_segments_count,
        hidden_elements=result.metadata.quality_metrics.segments_hidden,
        parallel_groups=result.metadata.quality_metrics.parallel_groups_count,
        orphan_groups=result.metadata.quality_metrics.orphan_groups_count,
        orphan_ratio=round(result.metadata.quality_metrics.orphan_ratio, 3),
        total_warnings=len(warnings),
        total_seconds=round(total_elapsed, 3),
    )

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_run(
    func,
    default: Any,
    layer_name: str,
    warnings: list[ProcessingWarning],
) -> Any:
    """
    Безопасный wrapper для вызова слоя.

    Если функция бросает исключение — логируется warning, возвращается default.
    Pipeline продолжается с оставшимися данными.

    Для непрофессионального программиста:
    Это защита от того чтобы один сбой в одном слое ломал весь pipeline.
    Например, если Layer 3 упадёт на неожиданном тексте — Layer 4-6 всё
    равно смогут обработать что есть.
    """
    try:
        return func()
    except Exception as exc:
        logger.exception(
            f"Multilingual pipeline: {layer_name} failed, using fallback",
            error=str(exc),
        )
        warnings.append(
            ProcessingWarning(
                warning_type="layer_execution_failed",
                details={
                    "layer_name": layer_name,
                    "error": str(exc),
                    "fallback": "using default empty result",
                },
            )
        )
        return default


def _safe_get_list(data: dict, key: str) -> list:
    """Безопасно извлечь list из dict. Возвращает [] если ключ отсутствует
    или не список."""
    value = data.get(key)
    if isinstance(value, list):
        return value
    return []


def _compute_language_stats(
    segments: list[LanguageSegment],
) -> tuple[list[str], dict[str, float]]:
    """
    Вычислить detected_languages и language_ratios на основе классифицированных
    сегментов.

    Правила:
    - Считаем только сегменты с реальным языком (не bypass, не unknown, не mixed)
    - Ratio считается по количеству символов (не по количеству сегментов)
    - Возвращаем sorted list детектированных языков + dict с ratios

    Возвращает:
        (detected_languages, language_ratios)

    Пример:
        segments: [seg_ru(100 chars), seg_en(80 chars), seg_neutral(5 chars)]
        → detected_languages: ["en", "ru"]
        → language_ratios: {"ru": 0.556, "en": 0.444}
    """
    if not segments:
        return [], {}

    char_counts: dict[str, int] = defaultdict(int)
    total_chars = 0

    for seg in segments:
        # Игнорируем bypass (structured_data, neutral) и unknown/mixed
        if seg.language in ("structured_data", "neutral", "unknown", "mixed"):
            continue

        if not seg.language:
            continue

        chars = len(seg.text.strip())
        if chars == 0:
            continue

        char_counts[seg.language] += chars
        total_chars += chars

    if total_chars == 0:
        return [], {}

    detected_languages = sorted(char_counts.keys())
    language_ratios = {
        lang: char_counts[lang] / total_chars
        for lang in detected_languages
    }

    return detected_languages, language_ratios


def _build_empty_result(
    document_id: str,
    document_version_id: str,
    target_language: str,
    tables: list,
    warnings: list[ProcessingWarning],
    layer_timings: dict[str, float],
) -> PipelineResult:
    """
    Построить пустой PipelineResult для случаев когда pipeline не смог
    произвести элементы (например, no segments после Layer 2).
    """
    from services.multilingual.models import (
        ANALYSIS_SOURCE_KIND,
        SCHEMA_VERSION,
        PipelineMetadata,
        ProcessingTrace,
        QualityMetrics,
    )

    trace = ProcessingTrace()
    trace.warnings = list(warnings)
    trace.layer1_seconds = layer_timings.get("layer1", 0.0)
    trace.layer2_seconds = layer_timings.get("layer2", 0.0)
    trace.total_seconds = sum(layer_timings.values())

    metadata = PipelineMetadata(
        target_language=target_language,
        processing_trace=trace,
    )

    return PipelineResult(
        schema_version=SCHEMA_VERSION,
        document_id=document_id,
        document_version_id=document_version_id,
        target_language=target_language,
        elements=[],
        tables=tables,
        metadata=metadata,
    )



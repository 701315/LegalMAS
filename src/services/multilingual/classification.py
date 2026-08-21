"""
Layer 3: Language Classification.

Задача:
- определить язык каждого LanguageSegment;
- пометить bypass сегменты (structured data, neutral);
- применить document-level prior для коротких и низкоуверенных текстов;
- применить split-context inference для восстановление языков в split-парах;
- применить neighbor voting для edge cases (только внутри одного script).

НЕ делает:
- не разбивает сегменты (это задача Layer 2);
- не делает alignment пар (это задача Layer 4);
- не изменяет text сегментов (lossless invariant).

Архитектура (трехпроходный алгоритм):
1. Первый проход: классификация длинных и надёжных сегментов (длина ≥ 30 символов);
2. Вычисление document-level language prior по надёжным сегментам;
3. Второй проход: классификация коротких, неуверенных или unknown сегментов с учётом prior;
4. Пост-обработка: split-context inference + script-aware neighbor voting.

Инварианты:
- Работает универсально для любой пары/набора языков.
- Script guard: соседний элемент с другим скриптом НЕ может изменить язык элемента.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from core.logging import get_logger
from services.language_detector import LanguageDetectionResult, get_language_detector
from services.multilingual.models import LanguageSegment, ProcessingWarning

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

# Минимальная длина для надёжной lingua classification (первый проход)
_MIN_CHARS_FOR_RELIABLE = 30

# Минимальная длина для вызова lingua
_MIN_CHARS_FOR_LINGUA = 10

# Porog confidence для признания длинного сегмента надёжным
_RELIABLE_CONFIDENCE_THRESHOLD = 0.50

# Тексты короче этого порога подвергаются агрессивному prior override
_SHORT_TEXT_AGGRESSIVE_PRIOR_THRESHOLD = 20

# Порог уверенности lingua, ниже которого prior имеет приоритет на коротких текстах
_SHORT_TEXT_MIN_LINGUA_CONFIDENCE = 0.50

# Порог уверенности, ниже которого сегмент номинируется на neighbor voting
_NEIGHBOR_VOTING_CONFIDENCE_THRESHOLD = 0.30

# Максимальная длина текста для участия в neighbor voting
_NEIGHBOR_VOTING_MAX_TEXT_LEN = 30

# Радиус поиска соседей для neighbor voting
_NEIGHBOR_VOTING_RADIUS = 3

# Минимальная доля согласия соседей для переопределения языка (60%)
_NEIGHBOR_VOTING_MIN_AGREEMENT = 0.60

# Пороги для mixed content detection (смешанные скрипты)
_MIXED_CONTENT_SECOND_SCRIPT_RATIO = 0.30
_MIXED_CONTENT_MIN_SECOND_SCRIPT_CHARS = 4

# ---------------------------------------------------------------------------
# Script → language mapping для однозначных скриптов (fast path)
# ---------------------------------------------------------------------------

_UNAMBIGUOUS_SCRIPT_TO_LANGUAGE: dict[str, str] = {
    "cyrillic": "ru",
    "hebrew": "he",
    "devanagari": "hi",
    "arabic": "ar",
    "cjk": "zh",
}


# ---------------------------------------------------------------------------
# Document-level language prior
# ---------------------------------------------------------------------------


def _compute_language_prior(
    segments: list[LanguageSegment],
) -> dict[str, dict[str, float]]:
    """
    Вычислить распределение языков по документу для каждого script.

    Используем ТОЛЬКО очень надёжные сегменты:
    - Длина ≥ 50 символов
    - Confidence ≥ 0.80
    - is_reliable == True
    - language не в (neutral, structured_data, unknown, mixed)
    """
    reliable = [
        s for s in segments
        if (
            len(s.text.strip()) >= 50
            and s.is_reliable
            and s.detection_confidence >= 0.80
            and s.language not in ("neutral", "structured_data", "unknown", "mixed")
        )
    ]

    if not reliable:
        return {
            script: {lang: 1.0}
            for script, lang in _UNAMBIGUOUS_SCRIPT_TO_LANGUAGE.items()
        }

    script_lang_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    
    for seg in reliable:
        if seg.script != "other":
            script_lang_counts[seg.script][seg.language] += 1

    prior: dict[str, dict[str, float]] = {}
    for script, lang_counts in script_lang_counts.items():
        total = sum(lang_counts.values())
        if total > 0:
            prior[script] = {
                lang: count / total
                for lang, count in lang_counts.items()
            }

    return prior


def _adjust_confidence_with_prior(
    detected_language: str,
    detected_confidence: float,
    prior: dict[str, float],
    text_length: int = 0,
) -> tuple[str, float]:
    """
    Скорректировать confidence lingua с учётом document prior.

    Логика:
    1. Для коротких или неуверенных (или unknown) текстов prior выигрывает.
    2. Для длинных текстов вычисляем нормализованный Bayesian posterior.
    """
    if not prior:
        return detected_language, detected_confidence

    is_short_text = text_length < _SHORT_TEXT_AGGRESSIVE_PRIOR_THRESHOLD
    is_low_confidence = (
        detected_confidence < _SHORT_TEXT_MIN_LINGUA_CONFIDENCE
        or detected_language == "unknown"
    )

    # Режим 1: Агрессивный override
    if is_low_confidence or is_short_text:
        best_lang = max(prior.keys(), key=lambda l: prior[l])
        return best_lang, prior[best_lang] * 0.7

    # Режим 2: Bayesian posterior
    scores: dict[str, float] = {}
    for lang, lang_prior in prior.items():
        if lang == detected_language:
            scores[lang] = detected_confidence * lang_prior
        else:
            scores[lang] = (1.0 - detected_confidence) * lang_prior

    if not scores:
        return detected_language, detected_confidence

    best_lang = max(scores.keys(), key=lambda l: scores[l])
    total_score = sum(scores.values())
    
    if total_score > 0:
        normalized_conf = scores[best_lang] / total_score
    else:
        normalized_conf = detected_confidence

    return best_lang, normalized_conf


# ---------------------------------------------------------------------------
# Вспомогательные публичные функции (для юнит-тестов и отладки)
# ---------------------------------------------------------------------------


def _find_dominant_language(languages: list[str]) -> tuple[str, float]:
    """
    Найти наиболее часто встречающийся язык в списке кодов.
    Возвращает (language_code, ratio).
    """
    if not languages:
        return "unknown", 0.0

    counts: dict[str, int] = defaultdict(int)
    for lang in languages:
        counts[lang] += 1

    total = len(languages)
    best_lang = max(counts.keys(), key=lambda l: counts[l])
    return best_lang, counts[best_lang] / total


def _needs_neighbor_voting(segment: LanguageSegment) -> bool:
    """
    Проверить, требуется ли сегменту попытка голосования соседей.
    """
    if segment.detection_method in ("structured_data_bypass", "neutral_bypass"):
        return False

    if segment.detection_confidence > _NEIGHBOR_VOTING_CONFIDENCE_THRESHOLD:
        return False

    if len(segment.text.strip()) >= _NEIGHBOR_VOTING_MAX_TEXT_LEN:
        return False

    return True


# ---------------------------------------------------------------------------
# Публичный API
# ---------------------------------------------------------------------------


def classify_segments(
    segments: list[LanguageSegment],
) -> tuple[list[LanguageSegment], list[ProcessingWarning]]:
    """
    Layer 3 entry point.

    Определить язык каждого LanguageSegment используя трехпроходный алгоритм:
    1. Первый проход: надёжные длинные сегменты (длина ≥ 30);
    2. Вычисление document-level language prior;
    3. Второй проход: короткие или неуверенно классифицированные сегменты с prior;
    4. Пост-обработка: split-context inference + neighbor voting.
    """
    if not segments:
        return [], []

    warnings: list[ProcessingWarning] = []
    detector = get_language_detector()

    # ── ПРОХОД 1: Надёжные длинные сегменты ────────────────────────────────
    for segment in segments:
        if len(segment.text.strip()) >= _MIN_CHARS_FOR_RELIABLE:
            try:
                _classify_single_segment(segment, detector, use_prior=False)
            except Exception as exc:
                logger.warning(
                    "Layer 3 Pass 1 classification failed for segment",
                    segment_id=segment.segment_id,
                    error=str(exc),
                )
                _apply_unknown_fallback(segment)

    # ── Вычисляем language prior по документу ─────────────────────────────
    prior = _compute_language_prior(segments)

    # ── ПРОХОД 2: Короткие или неуверенные сегменты с prior ────────────────
    for segment in segments:
        if (
            len(segment.text.strip()) < _MIN_CHARS_FOR_RELIABLE
            or not segment.is_reliable
            or segment.language == "unknown"
        ):
            try:
                _classify_single_segment(segment, detector, use_prior=True, prior=prior)
            except Exception as exc:
                logger.warning(
                    "Layer 3 Pass 2 classification failed for segment",
                    segment_id=segment.segment_id,
                    error=str(exc),
                )
                _apply_unknown_fallback(segment)

    # ── ПОСТ-ОБРАБОТКА: Split Context Inference & Neighbor Voting ─────────
    _apply_split_context_language_inference(segments, warnings, prior)
    _apply_neighbor_voting(segments, warnings, prior)

    return segments, warnings


# ---------------------------------------------------------------------------
# Первичная классификация одного сегмента
# ---------------------------------------------------------------------------


def _classify_single_segment(
    segment: LanguageSegment,
    detector: Any,
    use_prior: bool = False,
    prior: dict[str, dict[str, float]] | None = None,
) -> None:
    """
    Классифицировать один сегмент.
    """
    text = segment.text
    stripped = text.strip() if text else ""

    if not stripped:
        _apply_unknown_fallback(segment)
        return

    # ── Правило 1: neutral bypass ────────────────────────────────────────
    if _is_pure_neutral(stripped):
        segment.language = "neutral"
        segment.script = "other"
        segment.detection_confidence = 1.0
        segment.detection_method = "neutral_bypass"
        segment.is_reliable = True
        return

    # ── Правило 2: structured data bypass ────────────────────────────────
    if _is_definitely_structured_data(stripped):
        segment.language = "structured_data"
        segment.script = "other"
        segment.detection_confidence = 1.0
        segment.detection_method = "structured_data_bypass"
        segment.is_reliable = True
        return

    # ── Правило 3: mixed content detection ───────────────────────────────
    mixed_scripts = _detect_mixed_scripts(stripped)
    if mixed_scripts:
        segment.language = "mixed"
        segment.script = mixed_scripts[0]
        segment.detection_confidence = 0.5
        segment.detection_method = "script_only"
        segment.is_reliable = False
        return

    # ── Правило 4: script detection ──────────────────────────────────────
    script = detector.detect_script(stripped)
    segment.script = script

    if script in _UNAMBIGUOUS_SCRIPT_TO_LANGUAGE:
        segment.language = _UNAMBIGUOUS_SCRIPT_TO_LANGUAGE[script]
        segment.detection_confidence = 0.90
        segment.detection_method = "script_only"
        segment.is_reliable = True
        return

    # ── Правило 5: слишком короткий текст для lingua ─────────────────────
    text_length = len(stripped)
    if text_length < _MIN_CHARS_FOR_LINGUA:
        if use_prior and prior and script in prior:
            best_lang = max(prior[script].keys(), key=lambda l: prior[script][l])
            segment.language = best_lang
            segment.detection_confidence = prior[script][best_lang] * 0.6
            segment.detection_method = "prior_only"
            segment.is_reliable = False
        else:
            segment.language = "unknown"
            segment.script = script
            segment.detection_confidence = 0.0
            segment.detection_method = "too_short"
            segment.is_reliable = False
        return

    # ── Правило 6: lingua detection ──────────────────────────────────────
    try:
        result: LanguageDetectionResult = detector.detect_language(stripped)
        segment.language = result.language_code
        segment.script = result.script_code
        segment.detection_confidence = result.confidence
        segment.detection_method = "lingua"

        # Применяем prior adjustment
        if use_prior and prior:
            effective_prior = prior.get(result.script_code) or prior.get(script) or {}
            if effective_prior:
                new_lang, new_conf = _adjust_confidence_with_prior(
                    segment.language,
                    segment.detection_confidence,
                    effective_prior,
                    text_length=text_length,
                )
                if new_lang != segment.language or new_conf != segment.detection_confidence:
                    segment.language = new_lang
                    segment.detection_confidence = new_conf
                    segment.detection_method = "prior_adjusted"

        threshold = (
            _RELIABLE_CONFIDENCE_THRESHOLD
            if text_length >= _MIN_CHARS_FOR_RELIABLE
            else 0.80
        )
        segment.is_reliable = (
            segment.detection_confidence >= threshold
            and segment.language not in ("unknown", "mixed")
        )

    except Exception as exc:
        logger.warning(
            "Lingua detection failed, falling back to script or prior",
            segment_id=segment.segment_id,
            error=str(exc),
        )
        if use_prior and prior and script in prior:
            best_lang = max(prior[script].keys(), key=lambda l: prior[script][l])
            segment.language = best_lang
            segment.detection_confidence = 0.40
            segment.detection_method = "prior_fallback"
            segment.is_reliable = False
        else:
            segment.language = _fallback_language_from_script(script)
            segment.detection_confidence = 0.30
            segment.detection_method = "script_fallback"
            segment.is_reliable = False


# ---------------------------------------------------------------------------
# Split Context Inference
# ---------------------------------------------------------------------------


def _apply_split_context_language_inference(
    segments: list[LanguageSegment],
    warnings: list[ProcessingWarning],
    prior: dict[str, dict[str, float]] | None = None,
) -> None:
    """
    Восстановить language для ambiguous split-sibling сегментов.
    Если один исходный элемент был точно разбит на два разных скрипта, 
    и одна половина осталась unknown — восстанавливаем её язык по скрипту и prior.
    """
    by_source: dict[str, list[LanguageSegment]] = defaultdict(list)
    for seg in segments:
        by_source[seg.source_element_id].append(seg)

    for source_id, group in by_source.items():
        if len(group) < 2 or not all(seg.split_reason != "none" for seg in group):
            continue
        if not all(seg.split_confidence >= 0.90 for seg in group):
            continue

        scripts = {seg.script for seg in group if seg.script and seg.script != "other"}
        if len(scripts) < 2:
            continue

        known_segments = [s for s in group if s.language not in ("unknown", "mixed")]
        ambiguous_segments = [s for s in group if s.language in ("unknown", "mixed")]

        if not known_segments or not ambiguous_segments:
            continue

        for seg in ambiguous_segments:
            inferred_language: str | None = None
            inferred_confidence = 0.0

            script_prior = (prior or {}).get(seg.script, {})
            if script_prior:
                inferred_language = max(script_prior, key=lambda l: script_prior[l])
                inferred_confidence = script_prior[inferred_language] * 0.65

            if not inferred_language:
                fallback_language = _contextual_fallback_language_from_script(seg.script)
                if fallback_language != "unknown":
                    inferred_language = fallback_language
                    inferred_confidence = 0.35

            if not inferred_language:
                continue

            old_language = seg.language
            seg.language = inferred_language
            seg.detection_confidence = max(seg.detection_confidence, inferred_confidence)
            seg.detection_method = "split_context_inference"
            seg.is_reliable = False

            warnings.append(
                ProcessingWarning(
                    warning_type="split_context_inference_applied",
                    element_id=seg.source_element_id,
                    page=seg.page,
                    details={
                        "segment_id": seg.segment_id,
                        "old_language": old_language,
                        "new_language": inferred_language,
                        "script": seg.script,
                        "text_preview": seg.text[:40],
                    },
                )
            )


def _contextual_fallback_language_from_script(script: str) -> str:
    mapping = {
        "latin": "en",
        "cyrillic": "ru",
        "arabic": "ar",
        "hebrew": "he",
        "cjk": "zh",
        "devanagari": "hi",
    }
    return mapping.get(script, "unknown")


# ---------------------------------------------------------------------------
# Neighbor voting (fallback)
# ---------------------------------------------------------------------------


def _apply_neighbor_voting(
    segments: list[LanguageSegment],
    warnings: list[ProcessingWarning],
    prior: dict[str, dict[str, float]] | None = None,
) -> None:
    """
    Применить neighbor voting для сегментов с низким confidence.
    Ключевое правило: Сосед с другим скриптом НЕ имеет права голосовать.
    """
    for i, segment in enumerate(segments):
        if not _needs_neighbor_voting(segment):
            continue

        votes = _collect_neighbor_languages(segments, i, prior)
        if not votes:
            continue

        lang_weights: dict[str, float] = {}
        for lang, weight in votes:
            lang_weights[lang] = lang_weights.get(lang, 0.0) + weight

        if not lang_weights:
            continue

        dominant_lang = max(lang_weights.items(), key=lambda x: x[1])[0]
        total_weight = sum(lang_weights.values())
        dominant_ratio = lang_weights[dominant_lang] / total_weight

        if dominant_ratio >= _NEIGHBOR_VOTING_MIN_AGREEMENT and dominant_lang != segment.language:
            old_lang = segment.language
            segment.language = dominant_lang
            segment.detection_method = "neighbor_inheritance"
            segment.detection_confidence = 0.50
            segment.is_reliable = False

            warnings.append(
                ProcessingWarning(
                    warning_type="neighbor_voting_applied",
                    element_id=segment.source_element_id,
                    page=segment.page,
                    details={
                        "segment_id": segment.segment_id,
                        "old_language": old_lang,
                        "new_language": dominant_lang,
                        "dominant_ratio": round(dominant_ratio, 2),
                        "text_preview": segment.text[:40],
                    },
                )
            )


def _collect_neighbor_languages(
    segments: list[LanguageSegment],
    center_index: int,
    prior: dict[str, dict[str, float]] | None = None,
) -> list[tuple[str, float]]:
    center_seg = segments[center_index]
    if not center_seg.script or center_seg.script == "other":
        return []

    votes: list[tuple[str, float]] = []

    for direction in [-1, 1]:
        for offset in range(1, _NEIGHBOR_VOTING_RADIUS + 1):
            i = center_index + (direction * offset)
            if i < 0 or i >= len(segments):
                continue

            neighbor = segments[i]

            if neighbor.language in ("structured_data", "neutral", "unknown", "mixed"):
                continue

            if not neighbor.is_reliable and neighbor.detection_confidence < 0.70:
                continue

            # ИНВАРИАНТ: Сосед с другим script НЕ имеет права голосовать
            if neighbor.script != center_seg.script:
                continue

            distance_weight = 1.0 / offset
            prior_weight = 1.0
            if prior and center_seg.script in prior:
                prior_weight = prior[center_seg.script].get(neighbor.language, 0.5)

            weight = distance_weight * neighbor.detection_confidence * prior_weight
            votes.append((neighbor.language, weight))

    return votes


# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------


def _fallback_language_from_script(script: str) -> str:
    return _UNAMBIGUOUS_SCRIPT_TO_LANGUAGE.get(script, "unknown")


def _apply_unknown_fallback(segment: LanguageSegment) -> None:
    segment.language = "unknown"
    segment.script = "other"
    segment.detection_confidence = 0.0
    segment.detection_method = "too_short"
    segment.is_reliable = False


# ---------------------------------------------------------------------------
# Structured data & Neutral detection
# ---------------------------------------------------------------------------

_LAYER3_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
_LAYER3_URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
_LAYER3_PHONE_RE = re.compile(r"^\+\d[\d\s\-\(\)]{5,}$")
_LAYER3_IBAN_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$")
_LAYER3_SWIFT_RE = re.compile(r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?$")


def _is_definitely_structured_data(text: str) -> bool:
    if not text:
        return False
    if _LAYER3_EMAIL_RE.match(text):
        return True
    if _LAYER3_URL_RE.match(text):
        return True
    if _LAYER3_PHONE_RE.match(text):
        return True
    if _LAYER3_IBAN_RE.match(text):
        return True
    if _LAYER3_SWIFT_RE.match(text) and len(text) in (8, 11):
        return True
    return False


def _is_pure_neutral(text: str) -> bool:
    if not text:
        return False
    if text.strip().startswith("+"):
        return False
    return not any(ch.isalpha() for ch in text)


def _detect_mixed_scripts(text: str) -> list[str] | None:
    from services.multilingual.normalization import _script_of_char

    script_counts: dict[str, int] = defaultdict(int)
    total_letters = 0

    for ch in text:
        if ch.isalpha():
            script = _script_of_char(ch)
            if script != "other":
                script_counts[script] += 1
                total_letters += 1

    if total_letters == 0 or len(script_counts) < 2:
        return None

    sorted_scripts = sorted(script_counts.items(), key=lambda x: x[1], reverse=True)
    second_count = sorted_scripts[1][1]
    second_ratio = second_count / total_letters

    if (
        second_ratio < _MIXED_CONTENT_SECOND_SCRIPT_RATIO
        or second_count < _MIXED_CONTENT_MIN_SECOND_SCRIPT_CHARS
    ):
        return None

    return [s for s, _ in sorted_scripts]


    
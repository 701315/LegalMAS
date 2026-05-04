# src/classifiers/stage8/l2_header.py

"""
L2 Header Classifier — классификация по заголовку документа (Stage 8).

Production-версия с расширенным форматом classification_runtime_v1:
- использует явные weight, distinctiveness, context из YAML
- использует severity: hard/soft для exclusions из YAML
- использует scoring parameters из YAML per-type
- убраны hardcoded списки _GENERIC_TERMS и _HARD_EXCLUSION_TERMS
- убраны hardcoded веса (0.35, 0.50, 0.30...)
- universal engine: вся policy в YAML, код только исполняет

Назначение:
- Второй уровень каскада после L1.
- Анализирует заголовок / шапку документа (первые строки текста) и
  ищет характерные шаблоны для типов документов.

Источники сигналов:
- YAMLRegistry.get_all_configs() возвращает DocumentTypeConfig для каждого типа.
- В DocumentTypeConfig ожидаются:
  - scoring: dict с параметрами (accept_threshold, ambiguity_margin, ...)
  - lexical_signals: dict[str, list[dict]] с группами high/medium/low
  - negative_signals: list[dict] с severity: hard/soft
  - LEGACY: header_patterns, keywords_high/medium/low, exclusions (для backwards compatibility)

Как работает:
- На вход подаётся уже извлечённый header_text.
- Для каждого типа:
  - проверяем negative_signals с severity: hard → SUPPRESS type
  - собираем positive score из lexical_signals с учётом weight, distinctiveness, context
  - вычитаем penalties из negative_signals с severity: soft
  - применяем ambiguity_penalty если top2 candidates близки
- На основании накопленного score и penalties вычисляем confidence.

Роль в каскаде:
- L2 даёт более надёжный сигнал, чем L1.
- При высокой уверенности и отсутствии exclusions HybridClassifier может остановиться на L2.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ..base import BaseClassifier, ClassificationResult
from ..yaml_registry import YAMLRegistry, DocumentTypeConfig
from core.config import settings
from core.constants import ClassificationLevel
from core.logging import get_logger

logger = get_logger(__name__)


# === REMOVED: _GENERIC_TERMS, _HARD_EXCLUSION_TERMS ===
# Больше не нужны — всё в YAML


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _safe_pattern_str(pattern: Any) -> str:
    """Extract pattern string from compiled regex or dict."""
    if hasattr(pattern, "pattern"):
        return pattern.pattern
    return str(pattern)


def _estimate_input_quality(header_text: str) -> float:
    """
    Оценка качества входа для orchestrator/voter.
    Короткий заголовок даёт менее надёжный сигнал.
    """
    text_len = len((header_text or "").strip())
    if text_len <= 0:
        return 0.0
    if text_len >= 120:
        return 1.0
    return round(max(0.5, text_len / 120.0), 3)


class L2HeaderClassifier(BaseClassifier):
    """
    L2: Header/keyword classifier на базе YAMLRegistry с расширенным форматом.

    Ожидает, что DocumentTypeConfig формирует для каждого типа:
      - scoring: dict с параметрами
      - lexical_signals: dict[str, list[dict]] — high/medium/low
      - negative_signals: list[dict] — с severity/weight
      - LEGACY: header_patterns, keywords_*, exclusions (fallback)
    """

    def __init__(self, registry: YAMLRegistry | None = None) -> None:
        self._registry = registry or YAMLRegistry.get_instance()

    @property
    def level(self) -> ClassificationLevel:
        """Возвращает агрегированный уровень каскада для этого классификатора."""
        return ClassificationLevel.L2_KEYWORDS

    async def classify(
        self,
        text: str,
        filename: str,
        folder_path: str,
        text_sanitized: str | None = None,
        metadata: dict | None = None,
    ) -> ClassificationResult:
        """
        Классификация по заголовку/шапке.

        text — сюда должен приходить уже подготовленный header_text (или полный текст,
        из которого первые строки содержат заголовок).
        filename, folder_path, text_sanitized, metadata — сейчас не используются.

        Возвращает:
        - ClassificationResult с best type и confidence
        - extra содержит полную диагностику для orchestrator
        """
        header_text = (text or "").strip()
        input_quality = _estimate_input_quality(header_text)

        logger.info(
            "L2 classify start",
            extra={
                "filename": filename,
                "folder_path": folder_path,
                "header_len": len(header_text),
                "header_preview": repr(header_text[:400]),
                "input_quality": input_quality,
            },
        )

        if not header_text:
            logger.info(
                "L2 final result",
                extra={
                    "best_type": "UNKNOWN",
                    "best_conf": 0.0,
                    "best_evidence": None,
                    "best_extra": None,
                },
            )
            return ClassificationResult(
                doctype="UNKNOWN",
                confidence=0.0,
                level=self.level,
                method="header_pattern",
                evidence=None,
                extra=self._empty_extra(input_quality),
            )

        best_type: str = "UNKNOWN"
        best_conf: float = 0.0
        best_evidence: Optional[str] = None
        best_extra: Dict[str, Any] = {}

        scored_candidates: List[Dict[str, Any]] = []

        # Global defaults (fallback если нет scoring в YAML)
        global_accept = float(getattr(settings, "CLASSIFICATION_L2_ACCEPT", 0.75))
        global_ambiguity_margin = 0.15

        for cfg in self._registry.get_all_configs():
            cfg = cfg  # type: DocumentTypeConfig

            # === NEW: Используем расширенный формат, если есть ===
            has_extended = hasattr(cfg, "lexical_signals") and cfg.lexical_signals
            has_negative = hasattr(cfg, "negative_signals") and cfg.negative_signals

            if has_extended:
                result = self._classify_with_extended_format(
                    cfg, header_text, input_quality, global_accept, global_ambiguity_margin
                )
            else:
                # LEGACY: fallback на старый формат
                result = self._classify_with_legacy_format(
                    cfg, header_text, input_quality, global_accept
                )

            if result is None:
                continue

            scored_candidates.append(result)

            if result["confidence"] > best_conf:
                best_conf = result["confidence"]
                best_type = result["type_code"]
                best_evidence = result["evidence"]
                best_extra = dict(result["extra"])

        # Sort candidates by confidence
        scored_candidates.sort(key=lambda x: float(x["confidence"]), reverse=True)

        # Ambiguity penalty
        ambiguity_penalty = 0.0
        if len(scored_candidates) >= 2 and best_type != "UNKNOWN":
            top1_conf = float(scored_candidates[0]["confidence"])
            top2_conf = float(scored_candidates[1]["confidence"])
            margin = top1_conf - top2_conf

            # Используем ambiguity_margin из scoring winner type или global default
            winner_cfg = self._registry.get_config(best_type)
            ambiguity_margin = global_ambiguity_margin
            if winner_cfg and hasattr(winner_cfg, "scoring") and winner_cfg.scoring:
                ambiguity_margin = float(
                    winner_cfg.scoring.get("ambiguity_margin", global_ambiguity_margin)
                )

            if margin < ambiguity_margin:
                ambiguity_penalty = 0.15 * (1.0 - margin / ambiguity_margin)

            if best_extra:
                best_extra["ambiguity_penalty"] = round(_clamp(ambiguity_penalty, 0.0, 0.15), 3)
                best_extra["top2_margin"] = round(margin, 4)
                best_extra["runner_up_type"] = scored_candidates[1]["type_code"]
                best_extra["runner_up_confidence"] = round(top2_conf, 4)
        elif best_extra:
            best_extra["ambiguity_penalty"] = 0.0
            best_extra["top2_margin"] = 1.0

        logger.info(
            "L2 final result",
            extra={
                "best_type": best_type,
                "best_conf": round(best_conf, 4),
                "best_evidence": best_evidence,
                "best_extra": best_extra or None,
            },
        )

        return ClassificationResult(
            doctype=best_type,
            confidence=best_conf,
            level=self.level,
            method="header_pattern",
            evidence=best_evidence,
            extra=best_extra or None,
        )

    def _classify_with_extended_format(
        self,
        cfg: DocumentTypeConfig,
        header_text: str,
        input_quality: float,
        global_accept: float,
        global_ambiguity_margin: float,
    ) -> Dict[str, Any] | None:
        """
        Классификация с использованием расширенного формата:
        - config.lexical_signals: dict[str, list[dict]]
        - config.negative_signals: list[dict]
        - config.scoring: dict

        Возвращает dict с type_code, confidence, evidence, extra или None если suppressed.
        """
        # Extract scoring parameters from YAML or use defaults
        scoring = getattr(cfg, "scoring", {}) or {}
        accept_threshold = float(scoring.get("accept_threshold", global_accept))
        input_quality_weight = float(scoring.get("input_quality_weight", 1.0))

        lexical_signals = getattr(cfg, "lexical_signals", {})
        negative_signals = getattr(cfg, "negative_signals", [])

        # Check for data availability
        has_signals = any(lexical_signals.get(level) for level in ("high", "medium", "low"))
        if not has_signals and not negative_signals:
            return None

        # === STEP 1: Check hard exclusions (severity: hard) ===
        hard_exclusion_hits = 0
        soft_exclusion_hits = 0
        matched_exclusions: List[str] = []

        for neg_signal in negative_signals:
            pattern = neg_signal.get("pattern")
            severity = neg_signal.get("severity", "soft")

            if not pattern:
                continue

            try:
                if pattern.search(header_text):
                    pattern_str = _safe_pattern_str(pattern)
                    matched_exclusions.append(f"EXCL[{severity}]: {pattern_str}")

                    if severity == "hard":
                        hard_exclusion_hits += 1
                    else:
                        soft_exclusion_hits += 1
            except Exception as e:
                logger.warning(
                    "L2 negative signal pattern error",
                    extra={
                        "type_code": cfg.type_code,
                        "pattern": _safe_pattern_str(pattern),
                        "error": str(e),
                    },
                )

        # SUPPRESS type if hard exclusion found
        if hard_exclusion_hits >= 1:
            logger.info(
                "L2 type HARD SUPPRESSED by exclusions",
                extra={
                    "type_code": cfg.type_code,
                    "hard_exclusion_hits": hard_exclusion_hits,
                    "matched_exclusions": matched_exclusions,
                    "reason": "hard_exclusion_detected",
                },
            )
            return None

        # === STEP 2: Collect positive signals ===
        positive_score = 0.0
        matched_patterns: List[str] = []

        # Counters for diagnostics
        signal_counts = {
            "high_distinctive": 0,
            "high_generic": 0,
            "medium_distinctive": 0,
            "medium_generic": 0,
            "low": 0,
        }

        for level in ("high", "medium", "low"):
            signals = lexical_signals.get(level, [])
            for signal in signals:
                pattern = signal.get("pattern")
                weight = signal.get("weight", 0.3)
                distinctiveness = signal.get("distinctiveness", "medium")
                context = signal.get("context", "any")

                if not pattern:
                    continue

                # Context filtering (для будущего: если передаём header/body separately)
                # Пока всё в header_text, поэтому context не фильтруем

                try:
                    if pattern.search(header_text):
                        pattern_str = _safe_pattern_str(pattern)
                        matched_patterns.append(
                            f"{level.upper()}[{distinctiveness},{weight}]: {pattern_str}"
                        )

                        # Add weighted score
                        positive_score += weight

                        # Update counters for diagnostics
                        if level == "high":
                            if distinctiveness == "high":
                                signal_counts["high_distinctive"] += 1
                            else:
                                signal_counts["high_generic"] += 1
                        elif level == "medium":
                            if distinctiveness == "high":
                                signal_counts["medium_distinctive"] += 1
                            else:
                                signal_counts["medium_generic"] += 1
                        else:
                            signal_counts["low"] += 1

                except Exception as e:
                    logger.warning(
                        "L2 lexical signal pattern error",
                        extra={
                            "type_code": cfg.type_code,
                            "level": level,
                            "pattern": _safe_pattern_str(pattern),
                            "error": str(e),
                        },
                    )

        # If no positive signals matched, skip this type
        if positive_score == 0.0:
            return None

        # === STEP 3: Calculate signal quality ===
        total_distinctive = (
            signal_counts["high_distinctive"] + signal_counts["medium_distinctive"]
        )
        total_generic = signal_counts["high_generic"] + signal_counts["medium_generic"]
        total_signals = total_distinctive + total_generic

        if total_signals > 0:
            signal_quality = total_distinctive / total_signals
        else:
            signal_quality = 0.5  # neutral if only low-level signals

        # === STEP 4: Apply soft exclusion penalties ===
        soft_excl_penalty = 0.0
        if soft_exclusion_hits > 0:
            # Accumulate penalties from soft negative signals
            for neg_signal in negative_signals:
                if neg_signal.get("severity") == "soft":
                    pattern = neg_signal.get("pattern")
                    if pattern and pattern.search(header_text):
                        penalty_weight = abs(float(neg_signal.get("weight", -0.3)))
                        soft_excl_penalty += penalty_weight

        # === STEP 5: Calculate final confidence ===
        # Base formula: positive_score * signal_quality - soft_excl_penalty
        conf = positive_score * signal_quality - soft_excl_penalty

        # Apply input quality weight
        conf = conf * (input_quality ** input_quality_weight)

        # Clamp to [0, 1]
        conf = _clamp(conf, 0.0, 1.0)

        # === STEP 6: Build diagnostics ===
        current_extra: Dict[str, Any] = {
            "positive_score": round(positive_score, 3),
            "signal_quality": round(signal_quality, 3),
            "soft_excl_penalty": round(soft_excl_penalty, 3),
            "input_quality": input_quality,
            "input_quality_weight": input_quality_weight,
            "high_distinctive_hits": signal_counts["high_distinctive"],
            "high_generic_hits": signal_counts["high_generic"],
            "medium_distinctive_hits": signal_counts["medium_distinctive"],
            "medium_generic_hits": signal_counts["medium_generic"],
            "low_hits": signal_counts["low"],
            "soft_exclusion_hits": soft_exclusion_hits,
            "hard_exclusion_hits": hard_exclusion_hits,
            "has_exclusion_hit": (hard_exclusion_hits + soft_exclusion_hits) > 0,
            "exclusion_hits": hard_exclusion_hits + soft_exclusion_hits,
            "matched_type": cfg.type_code,
            "matched_patterns_preview": matched_patterns[:15],
            "matched_exclusions_preview": matched_exclusions[:5],
            "accept_threshold": accept_threshold,
            "format": "extended_v1",
        }

        logger.info(
            "L2 type stats (extended format)",
            extra={
                "type_code": cfg.type_code,
                **current_extra,
                "final_conf": round(conf, 3),
            },
        )

        evidence = (
            f"positive_score={round(positive_score, 2)}, "
            f"signal_quality={round(signal_quality, 2)}, "
            f"high_dist={signal_counts['high_distinctive']}, "
            f"high_gen={signal_counts['high_generic']}, "
            f"medium_dist={signal_counts['medium_distinctive']}, "
            f"medium_gen={signal_counts['medium_generic']}, "
            f"low={signal_counts['low']}, "
            f"soft_excl={soft_exclusion_hits}, hard_excl={hard_exclusion_hits}; "
            f"patterns={matched_patterns[:10]}"
        )

        return {
            "type_code": cfg.type_code,
            "confidence": conf,
            "extra": current_extra,
            "evidence": evidence,
        }

    def _classify_with_legacy_format(
        self,
        cfg: DocumentTypeConfig,
        header_text: str,
        input_quality: float,
        global_accept: float,
    ) -> Dict[str, Any] | None:
        """
        LEGACY: классификация со старым форматом (keywords_high/medium/low, exclusions).
        
        Этот метод сохраняет старую логику с hardcoded весами и эвристикой distinctive/generic
        для типов, которые ещё не мигрированы на расширенный формат.
        
        Используется только если config.lexical_signals отсутствует или пуст.
        """
        header_patterns = getattr(cfg, "header_patterns", []) or []
        keywords_high = getattr(cfg, "keywords_high", []) or []
        keywords_medium = getattr(cfg, "keywords_medium", []) or []
        keywords_low = getattr(cfg, "keywords_low", []) or []
        exclusion_keywords = getattr(cfg, "exclusions", []) or []

        if (
            not header_patterns
            and not keywords_high
            and not keywords_medium
            and not keywords_low
            and not exclusion_keywords
        ):
            return None

        # Legacy counters
        header_pattern_hits = 0
        distinctive_high_hits = 0
        distinctive_medium_hits = 0
        generic_high_hits = 0
        generic_medium_hits = 0
        low_hits = 0
        soft_exclusion_hits = 0
        hard_exclusion_hits = 0
        matched_patterns: List[str] = []

        # REMOVED: эвристика _is_distinctive_pattern больше не используется
        # Вместо этого для legacy формата всё считается generic (консервативно)

        for p in header_patterns:
            try:
                if p.search(header_text):
                    header_pattern_hits += 1
                    matched_patterns.append(f"HEADER: {_safe_pattern_str(p)}")
            except Exception as e:
                logger.warning(
                    "Invalid header pattern",
                    extra={
                        "pattern": _safe_pattern_str(p),
                        "type_code": cfg.type_code,
                        "error": str(e),
                    },
                )

        # Keywords high - treat all as generic for legacy
        for p in keywords_high:
            try:
                if p.search(header_text):
                    generic_high_hits += 1
                    matched_patterns.append(f"HIGH: {_safe_pattern_str(p)}")
            except Exception:
                pass

        # Keywords medium - treat all as generic
        for p in keywords_medium:
            try:
                if p.search(header_text):
                    generic_medium_hits += 1
                    matched_patterns.append(f"MEDIUM: {_safe_pattern_str(p)}")
            except Exception:
                pass

        # Keywords low
        for p in keywords_low:
            try:
                if p.search(header_text):
                    low_hits += 1
                    matched_patterns.append(f"LOW: {_safe_pattern_str(p)}")
            except Exception:
                pass

        # Exclusions - все считаем soft (консервативно)
        for p in exclusion_keywords:
            try:
                if p.search(header_text):
                    soft_exclusion_hits += 1
                    matched_patterns.append(f"EXCLUSION: {_safe_pattern_str(p)}")
            except Exception:
                pass

        total_positive = (
            header_pattern_hits
            + distinctive_high_hits
            + distinctive_medium_hits
            + generic_high_hits
            + generic_medium_hits
            + low_hits
        )

        if total_positive == 0:
            return None

        # Legacy scoring formula (hardcoded weights)
        conf = 0.0

        if header_pattern_hits > 0:
            conf += 0.35 + 0.10 * min(header_pattern_hits - 1, 2)

        if generic_high_hits > 0:
            conf += 0.05 + 0.02 * min(generic_high_hits - 1, 2)

        if generic_medium_hits > 0:
            conf += 0.02 + 0.01 * min(generic_medium_hits - 1, 2)

        conf += 0.01 * min(low_hits, 3)

        # Legacy soft exclusion penalty
        if soft_exclusion_hits > 0:
            conf -= 0.20 * min(soft_exclusion_hits, 2)

        conf = _clamp(conf, 0.0, 1.0)

        current_extra: Dict[str, Any] = {
            "header_pattern_hits": header_pattern_hits,
            "distinctive_high_hits": distinctive_high_hits,
            "distinctive_medium_hits": distinctive_medium_hits,
            "generic_high_hits": generic_high_hits,
            "generic_medium_hits": generic_medium_hits,
            "low_hits": low_hits,
            "soft_exclusion_hits": soft_exclusion_hits,
            "hard_exclusion_hits": hard_exclusion_hits,
            "has_exclusion_hit": soft_exclusion_hits > 0,
            "exclusion_hits": soft_exclusion_hits,
            "input_quality": input_quality,
            "matched_type": cfg.type_code,
            "matched_patterns_preview": matched_patterns[:15],
            "accept_threshold": global_accept,
            "format": "legacy",
        }

        logger.info(
            "L2 type stats (legacy format)",
            extra={
                "type_code": cfg.type_code,
                **current_extra,
                "final_conf": round(conf, 3),
            },
        )

        evidence = (
            f"header={header_pattern_hits}, "
            f"high={generic_high_hits}, medium={generic_medium_hits}, "
            f"low={low_hits}, excl={soft_exclusion_hits}; "
            f"patterns={matched_patterns[:10]}"
        )

        return {
            "type_code": cfg.type_code,
            "confidence": conf,
            "extra": current_extra,
            "evidence": evidence,
        }

    def _empty_extra(self, input_quality: float) -> Dict[str, Any]:
        """Return empty diagnostics for UNKNOWN result."""
        return {
            "positive_score": 0.0,
            "signal_quality": 0.0,
            "soft_excl_penalty": 0.0,
            "input_quality": input_quality,
            "high_distinctive_hits": 0,
            "high_generic_hits": 0,
            "medium_distinctive_hits": 0,
            "medium_generic_hits": 0,
            "low_hits": 0,
            "soft_exclusion_hits": 0,
            "hard_exclusion_hits": 0,
            "has_exclusion_hit": False,
            "exclusion_hits": 0,
            "matched_type": "UNKNOWN",
            "matched_patterns_preview": [],
            "format": "none",
        }
    
    

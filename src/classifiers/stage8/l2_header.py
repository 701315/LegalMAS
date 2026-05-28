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

from typing import Any

from core.config import settings
from core.constants import ClassificationLevel
from core.logging import get_logger

from ..base import BaseClassifier, ClassificationResult
from ..yaml_registry import DocumentTypeConfig, YAMLRegistry

logger = get_logger(__name__)

# После строки: logger = get_logger(__name__)
# Добавить:

# ---------------------------------------------------------------------------
# L2 Legacy scoring constants
# Используются только в _classify_with_legacy_format.
# Не выносятся в config.py — это внутренняя алгоритмическая логика,
# а не системные пороги, управляемые оператором.
# ---------------------------------------------------------------------------
_LEGACY_HEADER_PATTERN_BASE: float = 0.35  # базовый вклад header_pattern hit
_LEGACY_HEADER_PATTERN_EXTRA: float = 0.10  # бонус за каждый доп. hit (max 2)
_LEGACY_DISTINCTIVE_HIGH_BASE: float = 0.05  # базовый вклад distinctive_high hit
_LEGACY_DISTINCTIVE_HIGH_EXTRA: float = 0.02  # бонус за каждый доп. hit (max 2)
_LEGACY_GENERIC_MEDIUM_BASE: float = 0.02  # базовый вклад generic_medium hit
_LEGACY_GENERIC_MEDIUM_EXTRA: float = 0.01  # бонус за каждый доп. hit (max 2)
_LEGACY_LOW_HIT_WEIGHT: float = 0.01  # вклад каждого low hit (max 3)
_LEGACY_SOFT_EXCL_PENALTY: float = 0.20  # штраф за каждый soft exclusion hit (max 2)
_LEGACY_MAX_AMBIGUITY_PENALTY: float = 0.15  # максимальный ambiguity penalty


def _clamp(value: float, min_value: float, max_value: float) -> float:
    """Clamp float value to an inclusive range."""
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
    if text_len >= settings.CLASSIFICATION_L2_INPUT_QUALITY_FULL_CHARS:
        return 1.0
    return round(
        max(0.5, text_len / settings.CLASSIFICATION_L2_INPUT_QUALITY_FULL_CHARS),
        3,
    )


def _normalize_context(value: Any) -> str:
    """
    Нормализует context из YAML.

    Допустимые значения:
    - "header"
    - "body"
    - "any"

    Любое неизвестное значение трактуем как "any",
    чтобы не ломать legacy/грязные конфиги.
    """
    normalized = str(value or "any").strip().lower()
    if normalized in {"header", "body", "any"}:
        return normalized
    return "any"


def _iter_context_texts(
    *,
    context: str,
    header_text: str,
    snippet_text: str,
) -> list[tuple[str, str]]:
    """
    Возвращает список текстовых областей, в которых надо искать паттерн.

    Для непрофессионального программиста:
    - context="header"  → ищем только в заголовке;
    - context="body"    → ищем только в snippet/body;
    - context="any"     → ищем отдельно в header и отдельно в body.

    Мы НЕ склеиваем header+body в один текст, потому что договорились:
    `context: any` должен проверяться по каждой области отдельно.
    """
    if context == "header":
        return [("header", header_text)]
    if context == "body":
        return [("body", snippet_text)]
    return [("header", header_text), ("body", snippet_text)]


def _search_pattern_in_context(
    *,
    pattern: Any,
    context: str,
    header_text: str,
    snippet_text: str,
) -> tuple[bool, str | None]:
    """
    Ищет regex-паттерн в нужной текстовой области с учётом context.

    Возвращает:
    - matched: найден ли хотя бы один матч;
    - matched_in: "header" / "body" / None

    Если context="any" и паттерн найден и там и там,
    возвращаем первую найденную область. Сам паттерн засчитывается только один раз.
    """
    for area_name, area_text in _iter_context_texts(
        context=context,
        header_text=header_text,
        snippet_text=snippet_text,
    ):
        if not area_text:
            continue
        if pattern.search(area_text):
            return True, area_name
    return False, None


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

        Параметры:
        - text: header_text, то есть текст заголовка документа.
        - metadata: опциональный словарь. Если в нём есть `snippet_text`,
          то паттерны с context="body" будут искать совпадения именно там.

        Возвращает:
        - ClassificationResult с best type и confidence.
        - extra содержит полную диагностику для orchestrator.
        """
        header_text = (text or "").strip()
        metadata = metadata or {}
        snippet_text = str(metadata.get("snippet_text") or "").strip()
        input_quality = _estimate_input_quality(header_text)

        logger.info(
            "L2 classify start",
            extra={
                "filename": filename,
                "folder_path": folder_path,
                "header_len": len(header_text),
                "snippet_len": len(snippet_text),
                "header_preview": repr(header_text[:400]),
                "snippet_preview": repr(snippet_text[:400]),
                "input_quality": input_quality,
            },
        )

        if not header_text and not snippet_text:
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
        best_evidence: str | None = None
        best_extra: dict[str, Any] = {}

        scored_candidates: list[dict[str, Any]] = []

        global_accept: float = settings.CLASSIFICATION_L2_ACCEPT
        global_ambiguity_margin: float = settings.CLASSIFICATION_L2_AMBIGUITY_MARGIN

        for cfg in self._registry.get_all_configs():
            has_extended = hasattr(cfg, "lexical_signals") and cfg.lexical_signals
            has_negative = hasattr(cfg, "negative_signals") and cfg.negative_signals

            if has_extended or has_negative:
                result = self._classify_with_extended_format(
                    cfg=cfg,
                    header_text=header_text,
                    snippet_text=snippet_text,
                    input_quality=input_quality,
                    global_accept=global_accept,
                    global_ambiguity_margin=global_ambiguity_margin,
                )
            else:
                result = self._classify_with_legacy_format(
                    cfg=cfg,
                    header_text=header_text,
                    input_quality=input_quality,
                    global_accept=global_accept,
                )

            if result is None:
                continue

            scored_candidates.append(result)

            if float(result["confidence"]) > best_conf:
                best_conf = float(result["confidence"])
                best_type = str(result["type_code"])
                best_evidence = result["evidence"]
                best_extra = dict(result["extra"])

        scored_candidates.sort(key=lambda x: float(x["confidence"]), reverse=True)

        ambiguity_penalty = 0.0
        if len(scored_candidates) >= 2 and best_type != "UNKNOWN":
            top1_conf = float(scored_candidates[0]["confidence"])
            top2_conf = float(scored_candidates[1]["confidence"])
            margin = top1_conf - top2_conf

            winner_cfg = self._registry.get_config(best_type)
            ambiguity_margin = global_ambiguity_margin
            if winner_cfg and hasattr(winner_cfg, "scoring") and winner_cfg.scoring:
                ambiguity_margin = float(
                    winner_cfg.scoring.get("ambiguity_margin", global_ambiguity_margin)
                )

            if ambiguity_margin > 0 and margin < ambiguity_margin:
                ambiguity_penalty = _LEGACY_MAX_AMBIGUITY_PENALTY * (
                    1.0 - margin / ambiguity_margin
                )

            if best_extra:
                best_extra["ambiguity_penalty"] = round(
                    _clamp(ambiguity_penalty, 0.0, _LEGACY_MAX_AMBIGUITY_PENALTY),
                    3,
                )
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
        snippet_text: str,
        input_quality: float,
        global_accept: float,
        global_ambiguity_margin: float,
    ) -> dict[str, Any] | None:
        """
        Классификация с использованием расширенного формата:
        - config.lexical_signals: dict[str, list[dict]]
        - config.negative_signals: list[dict]
        - config.scoring: dict

        Возвращает dict с type_code, confidence, evidence, extra или None если suppressed.
        """
        scoring = getattr(cfg, "scoring", {}) or {}
        accept_threshold = float(scoring.get("accept_threshold", global_accept))
        input_quality_weight = float(scoring.get("input_quality_weight", 1.0))

        lexical_signals = getattr(cfg, "lexical_signals", {}) or {}
        negative_signals = getattr(cfg, "negative_signals", []) or []

        has_signals = any(lexical_signals.get(level) for level in ("high", "medium", "low"))
        if not has_signals and not negative_signals:
            return None

        hard_exclusion_hits = 0
        soft_exclusion_hits = 0
        matched_exclusions: list[str] = []

        for neg_signal in negative_signals:
            pattern = neg_signal.get("pattern")
            severity = str(neg_signal.get("severity", "soft")).strip().lower()
            context = _normalize_context(neg_signal.get("context", "any"))

            if not pattern:
                continue

            try:
                matched, matched_in = _search_pattern_in_context(
                    pattern=pattern,
                    context=context,
                    header_text=header_text,
                    snippet_text=snippet_text,
                )
                if matched:
                    pattern_str = _safe_pattern_str(pattern)
                    matched_exclusions.append(
                        f"EXCL[{severity},{context},{matched_in}]: {pattern_str}"
                    )

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
                        "severity": severity,
                        "context": context,
                        "error": str(e),
                    },
                )

        if hard_exclusion_hits >= 1:
            logger.info(
                "L2 type HARD SUPPRESSED by exclusions",
                extra={
                    "type_code": cfg.type_code,
                    "hard_exclusion_hits": hard_exclusion_hits,
                    "soft_exclusion_hits": soft_exclusion_hits,
                    "matched_exclusions": matched_exclusions,
                    "reason": "hard_exclusion_detected",
                },
            )
            return None

        positive_score = 0.0
        matched_patterns: list[str] = []

        signal_counts = {
            "high_distinctive": 0,
            "high_generic": 0,
            "medium_distinctive": 0,
            "medium_generic": 0,
            "low": 0,
        }

        for level in ("high", "medium", "low"):
            signals = lexical_signals.get(level, []) or []
            for signal in signals:
                pattern = signal.get("pattern")
                weight = float(
                    signal.get("weight", settings.CLASSIFICATION_L2_DEFAULT_POSITIVE_WEIGHT)
                )
                distinctiveness = str(signal.get("distinctiveness", "medium")).strip().lower()
                context = _normalize_context(signal.get("context", "any"))

                if not pattern:
                    continue

                try:
                    matched, matched_in = _search_pattern_in_context(
                        pattern=pattern,
                        context=context,
                        header_text=header_text,
                        snippet_text=snippet_text,
                    )
                    if matched:
                        pattern_str = _safe_pattern_str(pattern)
                        matched_patterns.append(
                            f"{level.upper()}[{distinctiveness},{weight},{context},{matched_in}]: {pattern_str}"
                        )

                        positive_score += weight

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
                            "distinctiveness": distinctiveness,
                            "context": context,
                            "error": str(e),
                        },
                    )

        if positive_score == 0.0:
            return None

        total_distinctive = signal_counts["high_distinctive"] + signal_counts["medium_distinctive"]
        total_generic = signal_counts["high_generic"] + signal_counts["medium_generic"]
        total_signals = total_distinctive + total_generic

        if total_signals > 0:
            signal_quality = total_distinctive / total_signals
        else:
            signal_quality = 0.5

        soft_excl_penalty = 0.0
        if soft_exclusion_hits > 0:
            for neg_signal in negative_signals:
                if str(neg_signal.get("severity", "soft")).strip().lower() != "soft":
                    continue

                pattern = neg_signal.get("pattern")
                context = _normalize_context(neg_signal.get("context", "any"))
                if not pattern:
                    continue

                matched, _ = _search_pattern_in_context(
                    pattern=pattern,
                    context=context,
                    header_text=header_text,
                    snippet_text=snippet_text,
                )
                if matched:
                    penalty_weight = abs(
                        float(
                            neg_signal.get(
                                "weight", settings.CLASSIFICATION_L2_DEFAULT_NEGATIVE_WEIGHT
                            )
                        )
                    )
                    soft_excl_penalty += penalty_weight

        conf = positive_score * signal_quality - soft_excl_penalty
        conf = conf * (input_quality**input_quality_weight)
        conf = _clamp(conf, 0.0, 1.0)

        current_extra: dict[str, Any] = {
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
            "ambiguity_margin": float(scoring.get("ambiguity_margin", global_ambiguity_margin)),
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
    ) -> dict[str, Any] | None:
        """
        LEGACY: классификация со старым форматом (keywords_high/medium/low, exclusions).

        Этот метод сохраняет старую формулу confidence для обратной совместимости,
        но исправляет диагностику хитов:
        - keywords_high считаются distinctive_high_hits,
        - keywords_medium остаются generic_medium_hits,
        - exclusions остаются soft для legacy.
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

        header_pattern_hits = 0
        distinctive_high_hits = 0
        distinctive_medium_hits = 0
        generic_high_hits = 0
        generic_medium_hits = 0
        low_hits = 0
        soft_exclusion_hits = 0
        hard_exclusion_hits = 0
        matched_patterns: list[str] = []

        for pattern in header_patterns:
            try:
                if pattern.search(header_text):
                    header_pattern_hits += 1
                    matched_patterns.append(f"HEADER: {_safe_pattern_str(pattern)}")
            except Exception as e:
                logger.warning(
                    "Invalid header pattern",
                    extra={
                        "pattern": _safe_pattern_str(pattern),
                        "type_code": cfg.type_code,
                        "error": str(e),
                    },
                )

        # FIXED:
        # keywords_high в legacy теперь считаем distinctive, а не generic.
        for pattern in keywords_high:
            try:
                if pattern.search(header_text):
                    distinctive_high_hits += 1
                    matched_patterns.append(f"HIGH: {_safe_pattern_str(pattern)}")
            except Exception as e:
                logger.warning(
                    "Invalid legacy high keyword pattern",
                    extra={
                        "pattern": _safe_pattern_str(pattern),
                        "type_code": cfg.type_code,
                        "error": str(e),
                    },
                )

        for pattern in keywords_medium:
            try:
                if pattern.search(header_text):
                    generic_medium_hits += 1
                    matched_patterns.append(f"MEDIUM: {_safe_pattern_str(pattern)}")
            except Exception as e:
                logger.warning(
                    "Invalid legacy medium keyword pattern",
                    extra={
                        "pattern": _safe_pattern_str(pattern),
                        "type_code": cfg.type_code,
                        "error": str(e),
                    },
                )

        for pattern in keywords_low:
            try:
                if pattern.search(header_text):
                    low_hits += 1
                    matched_patterns.append(f"LOW: {_safe_pattern_str(pattern)}")
            except Exception as e:
                logger.warning(
                    "Invalid legacy low keyword pattern",
                    extra={
                        "pattern": _safe_pattern_str(pattern),
                        "type_code": cfg.type_code,
                        "error": str(e),
                    },
                )

        # Legacy exclusions остаются soft.
        for pattern in exclusion_keywords:
            try:
                if pattern.search(header_text):
                    soft_exclusion_hits += 1
                    matched_patterns.append(f"EXCLUSION[soft]: {_safe_pattern_str(pattern)}")
            except Exception as e:
                logger.warning(
                    "Invalid legacy exclusion pattern",
                    extra={
                        "pattern": _safe_pattern_str(pattern),
                        "type_code": cfg.type_code,
                        "error": str(e),
                    },
                )

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

        # Сохраняем legacy confidence formula без изменений.
        conf = 0.0

        if header_pattern_hits > 0:
            conf += _LEGACY_HEADER_PATTERN_BASE + _LEGACY_HEADER_PATTERN_EXTRA * min(
                header_pattern_hits - 1, 2
            )

        if distinctive_high_hits > 0:
            conf += _LEGACY_DISTINCTIVE_HIGH_BASE + _LEGACY_DISTINCTIVE_HIGH_EXTRA * min(
                distinctive_high_hits - 1, 2
            )

        if generic_medium_hits > 0:
            conf += _LEGACY_GENERIC_MEDIUM_BASE + _LEGACY_GENERIC_MEDIUM_EXTRA * min(
                generic_medium_hits - 1, 2
            )

        conf += _LEGACY_LOW_HIT_WEIGHT * min(low_hits, 3)

        if soft_exclusion_hits > 0:
            conf -= _LEGACY_SOFT_EXCL_PENALTY * min(soft_exclusion_hits, 2)

        conf = _clamp(conf, 0.0, 1.0)

        total_distinctive = distinctive_high_hits + distinctive_medium_hits
        total_generic = generic_high_hits + generic_medium_hits

        if (total_distinctive + total_generic) > 0:
            signal_quality = total_distinctive / (total_distinctive + total_generic)
        else:
            signal_quality = 0.5

        current_extra: dict[str, Any] = {
            "header_pattern_hits": header_pattern_hits,
            "distinctive_high_hits": distinctive_high_hits,
            "distinctive_medium_hits": distinctive_medium_hits,
            "generic_high_hits": generic_high_hits,
            "generic_medium_hits": generic_medium_hits,
            "low_hits": low_hits,
            "signal_quality": round(signal_quality, 3),
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
            f"distinctive_high={distinctive_high_hits}, "
            f"generic_medium={generic_medium_hits}, "
            f"low={low_hits}, excl={soft_exclusion_hits}; "
            f"patterns={matched_patterns[:10]}"
        )

        return {
            "type_code": cfg.type_code,
            "confidence": conf,
            "extra": current_extra,
            "evidence": evidence,
        }

    def _empty_extra(self, input_quality: float) -> dict[str, Any]:
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

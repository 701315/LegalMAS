"""
L2 Header Classifier — классификация по заголовку документа (Stage 8).

Production-версия с:
- разделением distinctive/generic keywords через эвристику
- жёстким подавлением типов при hard exclusions
- калибруемым confidence через signal quality и genericity penalty
- полной диагностикой в extra для orchestrator и voting

Назначение:
- Второй уровень каскада после L1.
- Анализирует заголовок / шапку документа (первые строки текста) и
  ищет характерные шаблоны для типов документов.

Источники сигналов:
- YAMLRegistry.get_all_configs() возвращает DocumentTypeConfig для каждого типа.
- В DocumentTypeConfig ожидаются:
  - header_patterns (compiled regex) — характерные паттерны шапки;
  - keywords_high / keywords_medium / keywords_low — ключевые слова;
  - exclusions — слова/фразы, которые подавляют тип.

Как работает:
- На вход подаётся уже извлечённый header_text.
- Для каждого типа:
  - матчим header_patterns (regex);
  - считаем попадания по keywords_high/medium/low (строки);
  - считаем exclusions (строки) с разделением на hard/soft.
- На основании количества попаданий по уровням и exclusions вычисляем confidence.

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

# === Эвристика для разделения distinctive/generic keywords ===
# Пока YAML не обновлён до v2 schema, используем простое правило:
# Если regex содержит \b (word boundary) и не содержит очень общих слов,
# считаем его distinctive. Иначе — generic.
_GENERIC_TERMS = {
    # Русские общие термины
    "покупател", "продавец", "сторон", "договор", "соглашени",
    "цена", "сумм", "срок", "услуг", "работ", "исполнител",
    "заказчик", "поставщик", "компани", "организаци",
    # Английские общие термины
    "buyer", "seller", "party", "parties", "agreement", "contract",
    "price", "amount", "term", "service", "work", "contractor",
    "customer", "supplier", "company", "organization",
}

_HARD_EXCLUSION_TERMS = {
    "spa", "share purchase", "m&a", "merger", "acquisition",
    "real estate", "недвижимост", "lease", "аренд", "лизинг",
    "employment", "труд", "franchise", "франшиз",
}


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _safe_pattern_str(pattern: Any) -> str:
    return getattr(pattern, "pattern", str(pattern))


def _is_distinctive_pattern(pattern_str: str) -> bool:
    """
    Простая эвристика: паттерн distinctive, если:
    - содержит \\b (word boundary) — значит, ищет целое слово
    - НЕ содержит только общие термины из _GENERIC_TERMS

    Для непрофессионального программиста:
    - Это временное решение до обновления YAML.
    - Мы пытаемся отличить "договор поставки" (distinctive)
      от "покупатель" (generic).
    """
    lower = pattern_str.lower()

    if r"\b" not in pattern_str:
        return False

    for term in _GENERIC_TERMS:
        if term in lower:
            return False

    return True


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
    L2: Header/keyword classifier на базе YAMLRegistry.

    Ожидает, что DocumentTypeConfig формирует для каждого типа:
      - header_patterns (compiled regex, re.IGNORECASE),
      - keywords_high / keywords_medium / keywords_low (compiled regex),
      - exclusions (compiled regex из classification_runtime_v1.rules.exclusions).
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
                extra={
                    "header_pattern_hits": 0,
                    "distinctive_high_hits": 0,
                    "distinctive_medium_hits": 0,
                    "generic_high_hits": 0,
                    "generic_medium_hits": 0,
                    "low_hits": 0,
                    "soft_exclusion_hits": 0,
                    "hard_exclusion_hits": 0,
                    "has_exclusion_hit": False,
                    "exclusion_hits": 0,
                    "high_hits": 0,
                    "medium_hits": 0,
                    "signal_quality": 0.0,
                    "genericity_penalty": 0.0,
                    "soft_excl_penalty": 0.0,
                    "ambiguity_penalty": 0.0,
                    "input_quality": input_quality,
                    "matched_type": "UNKNOWN",
                    "matched_patterns_preview": [],
                },
            )

        best_type: str = "UNKNOWN"
        best_conf: float = 0.0
        best_evidence: Optional[str] = None
        best_extra: Dict[str, Any] = {}

        scored_candidates: List[Dict[str, Any]] = []

        base_accept = float(getattr(settings, "CLASSIFICATION_L2_ACCEPT", 0.75))
        excl_hard_threshold = int(getattr(settings, "CLASSIFICATION_L2_EXCL_HARD", 2))
        excl_soft_threshold = int(getattr(settings, "CLASSIFICATION_L2_EXCL_SOFT", 1))

        for cfg in self._registry.get_all_configs():
            cfg = cfg  # type: DocumentTypeConfig

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
                continue

            header_pattern_hits = 0
            distinctive_high_hits = 0
            distinctive_medium_hits = 0
            generic_high_hits = 0
            generic_medium_hits = 0
            low_hits = 0
            soft_exclusion_hits = 0
            hard_exclusion_hits = 0
            matched_patterns: List[str] = []

            logger.debug(
                "L2 patterns used",
                extra={
                    "type_code": cfg.type_code,
                    "header_patterns_count": len(header_patterns),
                    "keywords_high_count": len(keywords_high),
                    "keywords_medium_count": len(keywords_medium),
                    "keywords_low_count": len(keywords_low),
                    "exclusions_count": len(exclusion_keywords),
                },
            )

            for p in header_patterns:
                try:
                    if p.search(header_text):
                        header_pattern_hits += 1
                        matched_patterns.append(f"HEADER: {_safe_pattern_str(p)}")
                except Exception as e:
                    logger.warning(
                        "Invalid header pattern in YAMLRegistry",
                        extra={
                            "pattern": _safe_pattern_str(p),
                            "type_code": cfg.type_code,
                            "error": str(e),
                        },
                    )

            def _match_patterns_categorized(
                patterns: List[Any], category: str
            ) -> tuple[int, int]:
                distinctive = 0
                generic = 0

                for p in patterns or []:
                    try:
                        if hasattr(p, "search"):
                            regex = p
                        else:
                            pattern_str = (str(p) or "").strip()
                            if not pattern_str:
                                continue
                            regex = re.compile(pattern_str, re.IGNORECASE)

                        if regex.search(header_text):
                            pattern_str = _safe_pattern_str(regex)
                            matched_patterns.append(f"{category.upper()}: {pattern_str}")

                            if _is_distinctive_pattern(pattern_str):
                                distinctive += 1
                            else:
                                generic += 1
                    except Exception as e:
                        logger.warning(
                            "L2 keyword pattern error",
                            extra={
                                "type_code": cfg.type_code,
                                "category": category,
                                "pattern": _safe_pattern_str(p),
                                "error": str(e),
                            },
                        )
                return distinctive, generic

            dist_high, gen_high = _match_patterns_categorized(keywords_high, "high")
            dist_med, gen_med = _match_patterns_categorized(keywords_medium, "medium")

            distinctive_high_hits += dist_high
            generic_high_hits += gen_high
            distinctive_medium_hits += dist_med
            generic_medium_hits += gen_med

            for p in keywords_low or []:
                try:
                    if hasattr(p, "search"):
                        regex = p
                    else:
                        pattern_str = (str(p) or "").strip()
                        if not pattern_str:
                            continue
                        regex = re.compile(pattern_str, re.IGNORECASE)

                    if regex.search(header_text):
                        low_hits += 1
                        matched_patterns.append(f"LOW: {_safe_pattern_str(regex)}")
                except Exception as e:
                    logger.warning(
                        "L2 low keyword error",
                        extra={
                            "type_code": cfg.type_code,
                            "pattern": _safe_pattern_str(p),
                            "error": str(e),
                        },
                    )

            for p in exclusion_keywords or []:
                try:
                    if hasattr(p, "search"):
                        regex = p
                    else:
                        pattern_str = (str(p) or "").strip()
                        if not pattern_str:
                            continue
                        regex = re.compile(pattern_str, re.IGNORECASE)

                    if regex.search(header_text):
                        pattern_str = _safe_pattern_str(regex)
                        matched_patterns.append(f"EXCLUSION: {pattern_str}")

                        is_hard = any(term in pattern_str.lower() for term in _HARD_EXCLUSION_TERMS)
                        if is_hard:
                            hard_exclusion_hits += 1
                        else:
                            soft_exclusion_hits += 1
                except Exception as e:
                    logger.warning(
                        "L2 exclusion pattern error",
                        extra={
                            "type_code": cfg.type_code,
                            "pattern": _safe_pattern_str(p),
                            "error": str(e),
                        },
                    )

            total_exclusion_hits = hard_exclusion_hits + soft_exclusion_hits
            has_exclusion_hit = total_exclusion_hits > 0

            if hard_exclusion_hits >= 1:
                logger.info(
                    "L2 type HARD SUPPRESSED by exclusions",
                    extra={
                        "type_code": cfg.type_code,
                        "header_pattern_hits": header_pattern_hits,
                        "distinctive_high_hits": distinctive_high_hits,
                        "hard_exclusion_hits": hard_exclusion_hits,
                        "reason": "hard_exclusion_detected",
                    },
                )
                continue

            total_positive = (
                header_pattern_hits
                + distinctive_high_hits
                + distinctive_medium_hits
                + generic_high_hits
                + generic_medium_hits
                + low_hits
            )
            if total_positive == 0:
                continue

            conf = 0.0

            if header_pattern_hits > 0:
                base_header = 0.35
                if distinctive_high_hits >= 1 or distinctive_medium_hits >= 2:
                    base_header = 0.50
                conf += base_header + 0.10 * min(header_pattern_hits - 1, 2)

            if distinctive_high_hits > 0:
                conf += 0.30 + 0.08 * min(distinctive_high_hits - 1, 3)

            if distinctive_medium_hits > 0:
                conf += 0.10 + 0.04 * min(distinctive_medium_hits - 1, 3)

            if generic_high_hits > 0:
                conf += 0.05 + 0.02 * min(generic_high_hits - 1, 2)

            if generic_medium_hits > 0:
                conf += 0.02 + 0.01 * min(generic_medium_hits - 1, 2)

            conf += 0.01 * min(low_hits, 3)

            total_dist = distinctive_high_hits + distinctive_medium_hits
            total_gen = generic_high_hits + generic_medium_hits

            if total_dist + total_gen > 0:
                signal_quality = total_dist / (total_dist + total_gen)
            else:
                signal_quality = 0.5

            genericity_penalty = 0.0
            if total_gen > total_dist:
                genericity_penalty = 0.12 * min(total_gen - total_dist, 3)

            soft_excl_penalty = 0.0
            if soft_exclusion_hits > 0:
                soft_excl_penalty = 0.20 * min(soft_exclusion_hits, 2)

            conf = conf * signal_quality - genericity_penalty - soft_excl_penalty
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
                "has_exclusion_hit": has_exclusion_hit,
                "exclusion_hits": total_exclusion_hits,
                "high_hits": distinctive_high_hits + generic_high_hits,
                "medium_hits": distinctive_medium_hits + generic_medium_hits,
                "signal_quality": round(signal_quality, 3),
                "genericity_penalty": round(genericity_penalty, 3),
                "soft_excl_penalty": round(soft_excl_penalty, 3),
                "ambiguity_penalty": 0.0,
                "input_quality": input_quality,
                "matched_type": cfg.type_code,
                "matched_patterns_preview": matched_patterns[:15],
                "base_accept_threshold": base_accept,
                "soft_exclusion_threshold": excl_soft_threshold,
                "hard_exclusion_threshold": excl_hard_threshold,
            }

            logger.info(
                "L2 type stats",
                extra={
                    "type_code": cfg.type_code,
                    "header_pattern_hits": header_pattern_hits,
                    "distinctive_high_hits": distinctive_high_hits,
                    "distinctive_medium_hits": distinctive_medium_hits,
                    "generic_high_hits": generic_high_hits,
                    "generic_medium_hits": generic_medium_hits,
                    "low_hits": low_hits,
                    "soft_exclusion_hits": soft_exclusion_hits,
                    "hard_exclusion_hits": hard_exclusion_hits,
                    "signal_quality": round(signal_quality, 3),
                    "genericity_penalty": round(genericity_penalty, 3),
                    "soft_excl_penalty": round(soft_excl_penalty, 3),
                    "input_quality": input_quality,
                    "final_conf": round(conf, 3),
                },
            )

            scored_candidates.append(
                {
                    "type_code": cfg.type_code,
                    "confidence": conf,
                    "extra": current_extra,
                    "evidence": (
                        f"header={header_pattern_hits}, "
                        f"dist_high={distinctive_high_hits}, dist_med={distinctive_medium_hits}, "
                        f"gen_high={generic_high_hits}, gen_med={generic_medium_hits}, "
                        f"low={low_hits}, soft_excl={soft_exclusion_hits}, hard_excl={hard_exclusion_hits}; "
                        f"patterns={matched_patterns[:10]}"
                    ),
                }
            )

            if conf > best_conf:
                best_conf = conf
                best_type = cfg.type_code
                best_evidence = scored_candidates[-1]["evidence"]
                best_extra = dict(current_extra)

        scored_candidates.sort(key=lambda x: float(x["confidence"]), reverse=True)

        ambiguity_penalty = 0.0
        if len(scored_candidates) >= 2 and best_type != "UNKNOWN":
            top1_conf = float(scored_candidates[0]["confidence"])
            top2_conf = float(scored_candidates[1]["confidence"])
            margin = top1_conf - top2_conf
            if margin < 0.15:
                ambiguity_penalty = 0.15 * (1.0 - margin / 0.15)
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
    
    

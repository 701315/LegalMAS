# src/classifiers/stage8/_priority_rules.py

# src/classifiers/stage8/_priority_rules.py

"""
Специальные правила приоритета ДО голосования.

PR4: вынесен из hybrid_classifier.py.

Содержит:
  PriorityRulesEvaluator — класс с методом evaluate(...)

Правила:
  1. Сильный L2 выигрывает, если:
     - нет сильного семантического конфликта с L3 при слабом lexical L2;
     - нет согласованного сигнала L1+L3 против L2.

  2. L1 и L2 согласны и оба >= 0.7 -> HYBRID.

evaluate() возвращает готовый dict-результат или None.
None означает "продолжать каскад".
"""
from __future__ import annotations

import time
from typing import Any

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)


class PriorityRulesEvaluator:
    """
    Инкапсулирует специальные правила приоритета классификации.

    Принимает зависимости через конструктор — не обращается к HybridClassifier.
    Это позволяет тестировать правила изолированно.

    Зависимости:
      registry — YAMLRegistry (для чтения per-type strong_signal_threshold)
      builder  — ResultBuilder (для построения финального result dict)
      metrics  — MetricsClient (для записи classification_duration)
    """

    def __init__(self, registry: Any, builder: Any, metrics: Any) -> None:
        self._registry = registry
        self._builder = builder
        self._metrics = metrics

    def evaluate(
        self,
        *,
        doc_id: str,
        top_l1: dict | None,
        top_l2: Any | None,
        top_l3: Any | None,
        candidates: list[dict],
        details: dict,
        language: str | None,
        jurisdiction: str | None,
        started_at: float,
    ) -> dict | None:
        """
        Применяет правила приоритета ДО голосования.

        Возвращает:
          dict  — финальный результат классификации (ранний выход)
          None  — продолжать каскад (правила не сработали)

        Важно:
          details изменяется in-place (как и везде в каскаде).
          candidates используется только для чтения — не изменяется.
        """
        details.setdefault("contradiction_detected", False)

        result = self._rule_strong_l2(
            doc_id=doc_id,
            top_l1=top_l1,
            top_l2=top_l2,
            top_l3=top_l3,
            candidates=candidates,
            details=details,
            language=language,
            jurisdiction=jurisdiction,
            started_at=started_at,
        )
        if result is not None:
            return result

        result = self._rule_l1_l2_agree(
            doc_id=doc_id,
            top_l1=top_l1,
            top_l2=top_l2,
            candidates=candidates,
            details=details,
            language=language,
            jurisdiction=jurisdiction,
            started_at=started_at,
        )
        return result

    # ──────────────────────────────────────────────────────────────────
    # Правило 1: сильный L2
    # ──────────────────────────────────────────────────────────────────

    def _rule_strong_l2(
        self,
        *,
        doc_id: str,
        top_l1: dict | None,
        top_l2: Any | None,
        top_l3: Any | None,
        candidates: list[dict],
        details: dict,
        language: str | None,
        jurisdiction: str | None,
        started_at: float,
    ) -> dict | None:
        """
        Правило 1: сильный L2 выигрывает с защитой от ложной ранней победы.

        Возвращает dict или None.
        """
        if not top_l2:
            return None

        global_strong_l2: float = settings.CLASSIFICATION_L2_STRONG
        l1_consensus_min: float = settings.CLASSIFICATION_L1_CONSENSUS_MIN
        l3_consensus_min_raw: float = settings.CLASSIFICATION_L3_CONSENSUS_RAW_MIN
        l3_strong_conflict_raw: float = settings.CLASSIFICATION_L3_STRONG_CONFLICT_RAW

        l2_type = top_l2.doctype
        l2_conf = float(top_l2.confidence)

        l1_type = top_l1.get("type_code") if top_l1 else None
        l1_conf = float(top_l1.get("confidence", 0.0)) if top_l1 else 0.0

        l3_type = getattr(top_l3, "doctype", None) if top_l3 else None
        l3_conf = float(getattr(top_l3, "confidence", 0.0)) if top_l3 else 0.0
        l3_extra = (getattr(top_l3, "extra", {}) or {}) if top_l3 else {}
        l3_raw_sim = float(l3_extra.get("raw_similarity", 0.0)) if top_l3 else 0.0

        l1_l3_consensus_against_l2 = (
            bool(l1_type)
            and bool(l3_type)
            and l1_type == l3_type
            and l1_type != l2_type
            and l1_conf >= l1_consensus_min
            and l3_raw_sim >= l3_consensus_min_raw
        )

        winner_cfg = self._registry.get_config(l2_type)
        strong_l2 = global_strong_l2
        if winner_cfg is not None:
            scoring = getattr(winner_cfg, "scoring", {}) or {}
            strong_l2 = float(
                scoring.get("strong_signal_threshold", global_strong_l2)
            )

        if l2_conf < strong_l2:
            return None

        l2_extra = getattr(top_l2, "extra", {}) or {}
        l2_high_hits = int(l2_extra.get("high_hits", 0))
        l2_medium_hits = int(l2_extra.get("medium_hits", 0))
        distinctive_high = int(l2_extra.get("distinctive_high_hits", l2_high_hits))
        distinctive_medium = int(
            l2_extra.get("distinctive_medium_hits", l2_medium_hits // 2)
        )
        generic_high = int(l2_extra.get("generic_high_hits", 0))

        weak_l2_signal = (
            (distinctive_high == 0 and generic_high > 0)
            or (distinctive_high == 1 and distinctive_medium == 0)
        )

        # 1A: L1 + L3 консенсус против L2
        if l1_l3_consensus_against_l2:
            details["contradiction_detected"] = True
            details["l2_strong_suppressed"] = {
                "reason": "L1_L3_CONSENSUS_AGAINST_L2",
                "l2_type": l2_type,
                "l2_conf": l2_conf,
                "l2_strong_threshold": strong_l2,
                "l1_type": l1_type,
                "l1_conf": l1_conf,
                "l3_type": l3_type,
                "l3_conf": l3_conf,
                "l3_raw_similarity": l3_raw_sim,
                "decision": "continue_to_voting",
            }
            details["contradiction_summary"] = {
                "l2_type": l2_type,
                "l2_conf": l2_conf,
                "l1_type": l1_type,
                "l1_conf": l1_conf,
                "l3_type": l3_type,
                "l3_conf": l3_conf,
                "l3_raw_similarity": l3_raw_sim,
                "mode": "l1_l3_consensus_against_l2",
            }
            logger.warning(
                "Hybrid decision L2_STRONG_SUPPRESSED by L1+L3 consensus",
                extra={
                    "doc_id": doc_id,
                    "l2_type": l2_type,
                    "l2_conf": l2_conf,
                    "l2_strong_threshold": strong_l2,
                    "l1_type": l1_type,
                    "l1_conf": l1_conf,
                    "l3_type": l3_type,
                    "l3_conf": l3_conf,
                    "l3_raw_similarity": l3_raw_sim,
                },
            )
            return None

        # 1B: сильный семантический конфликт L3 при слабом lexical L2
        l3_conflict = bool(top_l3 and l3_type != l2_type)
        l3_semantic_strong = l3_conflict and (l3_raw_sim >= l3_strong_conflict_raw)

        if l3_conflict:
            details["contradiction_detected"] = True
            details["contradiction_summary"] = {
                "l2_type": l2_type,
                "l2_conf": l2_conf,
                "l3_type": l3_type,
                "l3_conf": l3_conf,
                "l3_raw_similarity": l3_raw_sim,
                "mode": "l2_vs_l3_conflict",
            }
            logger.info(
                "L2_STRONG_WINS: conflict detected with L3",
                extra={
                    "doc_id": doc_id,
                    "l2_type": l2_type,
                    "l2_conf": l2_conf,
                    "l2_strong_threshold": strong_l2,
                    "l2_distinctive_high_hits": distinctive_high,
                    "l2_distinctive_medium_hits": distinctive_medium,
                    "l2_generic_high_hits": generic_high,
                    "l2_high_hits_total": l2_high_hits,
                    "l3_type": l3_type,
                    "l3_conf": l3_conf,
                    "l3_raw_similarity": l3_raw_sim,
                    "l3_strong_conflict_raw": l3_strong_conflict_raw,
                    "l3_semantic_strong": l3_semantic_strong,
                    "weak_l2_signal": weak_l2_signal,
                },
            )

        if l3_conflict and l3_semantic_strong and weak_l2_signal:
            details["l2_strong_suppressed"] = {
                "reason": "L3_SEMANTIC_CONFLICT",
                "l2_type": l2_type,
                "l2_conf": l2_conf,
                "l2_strong_threshold": strong_l2,
                "l2_high_hits": l2_high_hits,
                "l2_distinctive_high_hits": distinctive_high,
                "l2_distinctive_medium_hits": distinctive_medium,
                "l2_generic_high_hits": generic_high,
                "l3_type": l3_type,
                "l3_conf": l3_conf,
                "l3_raw_similarity": l3_raw_sim,
                "l3_strong_conflict_raw": l3_strong_conflict_raw,
                "decision": "continue_to_voting",
            }
            logger.warning(
                "Hybrid decision L2_STRONG_SUPPRESSED by L3",
                extra={
                    "doc_id": doc_id,
                    "l2_type": l2_type,
                    "l2_conf": l2_conf,
                    "l2_strong_threshold": strong_l2,
                    "l3_type": l3_type,
                    "l3_conf": l3_conf,
                    "l3_raw_similarity": l3_raw_sim,
                },
            )
            return None

        # L2_STRONG_WINS
        return self._build_l2_strong_wins(
            doc_id=doc_id,
            l2_type=l2_type,
            l2_conf=l2_conf,
            strong_l2=strong_l2,
            l2_high_hits=l2_high_hits,
            l2_medium_hits=l2_medium_hits,
            distinctive_high=distinctive_high,
            distinctive_medium=distinctive_medium,
            generic_high=generic_high,
            candidates=candidates,
            details=details,
            language=language,
            jurisdiction=jurisdiction,
            started_at=started_at,
        )

    # ──────────────────────────────────────────────────────────────────
    # Правило 2: L1 + L2 согласны
    # ──────────────────────────────────────────────────────────────────

    def _rule_l1_l2_agree(
        self,
        *,
        doc_id: str,
        top_l1: dict | None,
        top_l2: Any | None,
        candidates: list[dict],
        details: dict,
        language: str | None,
        jurisdiction: str | None,
        started_at: float,
    ) -> dict | None:
        """
        Правило 2: L1 и L2 согласны и оба >= 0.7 -> HYBRID.

        Возвращает dict или None.
        """
        if not (
            top_l1
            and top_l2
            and top_l1["type_code"] == top_l2.doctype
            and float(top_l1["confidence"]) >= settings.CLASSIFICATION_L1_L2_AGREE_MIN
            and float(top_l2.confidence) >= settings.CLASSIFICATION_L1_L2_AGREE_MIN
        ):
            return None

        from ._decision_support import build_voting_details
        from ._decision_logger import DecisionStrategy, log_classification_decision

        final_type = top_l2.doctype
        final_conf = float(
            (float(top_l1["confidence"]) + float(top_l2.confidence)) / 2.0
        )

        details["voting"] = build_voting_details(
            strategy="L1_L2_AGREE",
            reason=f"L1 and L2 agree with >= {settings.CLASSIFICATION_L1_L2_AGREE_MIN}",
            extra={
                "type": final_type,
                "score": final_conf,
                "confidence": final_conf,
                "margin": None,
                "support_count": 2,
                "support_levels": ["L1", "L2"],
                "l1_conf": round(float(top_l1["confidence"]), 4),
                "l2_conf": round(float(top_l2.confidence), 4),
            },
        )

        log_classification_decision(
            doc_id=doc_id,
            decided_by=DecisionStrategy.L1_L2_AGREE,
            final_type=final_type,
            final_confidence=final_conf,
            levels_tried=details["levels_tried"],
            started_at=started_at,
            voting_score=(details.get("voting") or {}).get("score"),
            single_source_cap_applied=(details.get("voting") or {}).get(
                "single_source_cap_applied"
            ),
            extra={
                "l1_conf": round(float(top_l1["confidence"]), 4),
                "l2_conf": round(float(top_l2.confidence), 4),
            },
        )

        self._metrics.classification_duration.labels(
            source="l1_l2_agree"
        ).observe(time.time() - started_at)

        return self._builder.build(
            levels_tried=details["levels_tried"],
            candidates=candidates,
            final_type=final_type,
            final_confidence=final_conf,
            level="HYBRID",
            language=language,
            jurisdiction=jurisdiction,
            applicable_triggers=self._builder.build_triggers(doc_id, final_type),
            details=details,
        )

    # ──────────────────────────────────────────────────────────────────
    # Вспомогательный builder для L2_STRONG_WINS
    # ──────────────────────────────────────────────────────────────────

    def _build_l2_strong_wins(
        self,
        *,
        doc_id: str,
        l2_type: str,
        l2_conf: float,
        strong_l2: float,
        l2_high_hits: int,
        l2_medium_hits: int,
        distinctive_high: int,
        distinctive_medium: int,
        generic_high: int,
        candidates: list[dict],
        details: dict,
        language: str | None,
        jurisdiction: str | None,
        started_at: float,
    ) -> dict:
        """Строит финальный result для стратегии L2_STRONG_WINS."""
        from ._decision_support import build_voting_details
        from ._decision_logger import DecisionStrategy, log_classification_decision

        details["voting"] = build_voting_details(
            strategy="L2_STRONG_WINS",
            reason=(
                f"L2 confidence >= effective strong threshold {strong_l2}, "
                "no decisive semantic conflict and no L1+L3 consensus against L2"
            ),
            extra={
                "type": l2_type,
                "score": l2_conf,
                "confidence": l2_conf,
                "margin": None,
                "support_count": 1,
                "support_levels": ["L2"],
                "l2_high_hits": l2_high_hits,
                "l2_medium_hits": l2_medium_hits,
                "l2_distinctive_high_hits": distinctive_high,
                "l2_distinctive_medium_hits": distinctive_medium,
                "l2_generic_high_hits": generic_high,
                "l2_strong_threshold": strong_l2,
            },
        )

        log_classification_decision(
            doc_id=doc_id,
            decided_by=DecisionStrategy.L2_STRONG_WINS,
            final_type=l2_type,
            final_confidence=l2_conf,
            levels_tried=details["levels_tried"],
            started_at=started_at,
            contradiction=details.get("contradiction_detected", False),
            voting_score=(details.get("voting") or {}).get("score"),
            single_source_cap_applied=(details.get("voting") or {}).get(
                "single_source_cap_applied"
            ),
            extra={
                "l2_strong_threshold": strong_l2,
                "l2_distinctive_high_hits": distinctive_high,
                "l2_distinctive_medium_hits": distinctive_medium,
                "l2_generic_high_hits": generic_high,
            },
        )

        self._metrics.classification_duration.labels(
            source="l2_strong"
        ).observe(time.time() - started_at)

        return self._builder.build(
            levels_tried=details["levels_tried"],
            candidates=candidates,
            final_type=l2_type,
            final_confidence=l2_conf,
            level="L2",
            language=language,
            jurisdiction=jurisdiction,
            applicable_triggers=self._builder.build_triggers(doc_id, l2_type),
            details=details,
        )








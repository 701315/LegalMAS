# src/classifiers/stage8/_finalization.py

"""
Финализация fallback-результата для HybridClassifier.

PR5: вынесен из hybrid_classifier.py.

Содержит:
  FallbackFinalizer — построение финального fallback-результата
                      (UNKNOWN или слабый HYBRID).

Намеренно НЕ содержит:
  - orchestration каскада;
  - L1/L2/L3/L4 execution;
  - state HybridClassifier.

Зависимости передаются через конструктор:
  - builder
  - metrics
"""

from __future__ import annotations

import time
from typing import Any

from ._decision_logger import DecisionStrategy, log_classification_decision


class FallbackFinalizer:
    """
    Финализирует fallback-результат классификации.

    Отвечает за:
      - запись duration-метрики source="fallback";
      - вычисление corridor-скорректированного типа для логов/explainability;
      - выбор DecisionStrategy.FALLBACK_UNKNOWN / FALLBACK_LOW;
      - логирование final decision;
      - вызов builder.build(...).

    Важно:
      - builder остаётся single source of truth для итогового payload;
      - details["fallback"] содержит explainability snapshot;
      - applicable_triggers, если не переданы явно, строятся через builder.
    """

    def __init__(self, builder: Any, metrics: Any) -> None:
        self._builder = builder
        self._metrics = metrics

    def build_fallback_result(
        self,
        *,
        doc_id: str,
        final_type: str,
        final_conf: float,
        voted: dict | None,
        candidates: list[dict],
        details: dict,
        language: str | None,
        jurisdiction: str | None,
        started_at: float,
        applicable_triggers: list[str] | None = None,
    ) -> dict:
        """
        Строит финальный fallback: UNKNOWN или слабый HYBRID.

        Возвращает dict в том же формате, что и ResultBuilder.build(...).

        Параметры:
          doc_id               — идентификатор документа или сегмента
          final_type           — исходный тип после pre-L4 routing / voting
          final_conf           — confidence исходного типа
          voted                — raw voted payload или None
          candidates           — текущий список кандидатов
          details              — details dict (используется для логов и build)
          language             — язык результата
          jurisdiction         — юрисдикция результата
          started_at           — timestamp начала classify_* для duration
          applicable_triggers  — если задан, используется как есть;
                                 иначе строится через builder.build_triggers
        """
        self._metrics.classification_duration.labels(source="fallback").observe(
            time.time() - started_at
        )

        details = details or {}
        levels_tried = list(details.get("levels_tried") or [])

        raw_final_type = str(final_type or "UNKNOWN")
        final_conf = self._safe_float(final_conf, 0.0)

        final_type_after_corridor = self._builder.apply_unknown_corridor(
            raw_final_type,
            final_conf,
        )
        zone, requires_review_by_conf = self._builder.confidence_zone(final_conf)
        unknown_corridor_applied = final_type_after_corridor != raw_final_type

        voting_details = details.get("voting") or {}
        voting_score = voting_details.get("score")
        single_source_cap_applied = voting_details.get("single_source_cap_applied")
        voting_margin = details.get("voting_margin")

        l4_gate = details.get("L4_gate") if isinstance(details.get("L4_gate"), dict) else {}
        l4_status = l4_gate.get("status")
        l4_skip_reason = l4_gate.get("skip_reason")
        l4_failure_reason = l4_gate.get("failure_reason")
        l4_review_preferred = bool(l4_gate.get("review_preferred", False))
        l4_adjudication_reason = l4_gate.get("adjudication_reason")

        contradiction_detected = bool(details.get("contradiction_detected", False))
        domain_conflict = bool(details.get("domain_conflict", False))
        input_quality = self._safe_float(details.get("input_quality", 1.0), 1.0)

        # Итоговый review-флаг должен учитывать не только confidence zone,
        # но и policy-сигналы L4/manual-review.
        requires_review = bool(
            requires_review_by_conf
            or l4_review_preferred
            or contradiction_detected
            or (final_type_after_corridor == "UNKNOWN")
        )

        decided_by = (
            DecisionStrategy.FALLBACK_UNKNOWN
            if final_type_after_corridor == "UNKNOWN"
            else DecisionStrategy.FALLBACK_LOW
        )

        details["fallback"] = {
            "raw_final_type": raw_final_type,
            "final_type_after_corridor": final_type_after_corridor,
            "final_confidence": final_conf,
            "confidence_zone": zone,
            "requires_manual_review": requires_review,
            "requires_manual_review_by_confidence": requires_review_by_conf,
            "unknown_corridor_applied": unknown_corridor_applied,
            "voted_present": voted is not None,
            "voted_type": voting_details.get("type"),
            "voting_score": voting_score,
            "voting_margin": voting_margin,
            "support_count": voting_details.get("support_count"),
            "support_levels": voting_details.get("support_levels"),
            "contradiction_detected": contradiction_detected,
            "domain_conflict": domain_conflict,
            "input_quality": input_quality,
            "l4_status": l4_status,
            "l4_skip_reason": l4_skip_reason,
            "l4_failure_reason": l4_failure_reason,
            "l4_review_preferred": l4_review_preferred,
            "l4_adjudication_reason": l4_adjudication_reason,
        }

        log_classification_decision(
            doc_id=doc_id,
            decided_by=decided_by,
            final_type=final_type_after_corridor,
            final_confidence=final_conf,
            levels_tried=levels_tried,
            started_at=started_at,
            requires_manual_review=requires_review,
            confidence_zone=zone,
            unknown_corridor_applied=unknown_corridor_applied,
            voting_score=voting_score,
            single_source_cap_applied=single_source_cap_applied,
            contradiction=contradiction_detected,
            extra={
                "raw_final_type": raw_final_type,
                "voted_type": voting_details.get("type"),
                "voting_margin": voting_margin,
                "support_count": voting_details.get("support_count"),
                "support_levels": voting_details.get("support_levels"),
                "domain_conflict": domain_conflict,
                "input_quality": input_quality,
                "l4_status": l4_status,
                "l4_skip_reason": l4_skip_reason,
                "l4_failure_reason": l4_failure_reason,
                "l4_review_preferred": l4_review_preferred,
                "l4_adjudication_reason": l4_adjudication_reason,
            },
        )

        safe_applicable_triggers = (
            list(applicable_triggers)
            if applicable_triggers is not None
            else self._resolve_applicable_triggers(
                doc_id=doc_id,
                raw_final_type=raw_final_type,
                final_type_after_corridor=final_type_after_corridor,
            )
        )

        fallback_level = self._fallback_level(
            raw_final_type=raw_final_type,
            final_type_after_corridor=final_type_after_corridor,
            voted=voted,
        )

        return self._builder.build(
            levels_tried=levels_tried,
            candidates=candidates,
            final_type=raw_final_type,
            final_confidence=final_conf,
            level=fallback_level,
            language=language,
            jurisdiction=jurisdiction,
            applicable_triggers=safe_applicable_triggers,
            details=details,
        )

    def _resolve_applicable_triggers(
        self,
        *,
        doc_id: str,
        raw_final_type: str,
        final_type_after_corridor: str,
    ) -> list[str]:
        """
        Для fallback не надо строить triggers для UNKNOWN.

        Если corridor уже уронил результат в UNKNOWN, возвращаем [].
        Иначе строим triggers по raw_final_type — builder затем сам
        останется source of truth для финального payload.
        """
        if final_type_after_corridor == "UNKNOWN":
            return []
        if not raw_final_type or raw_final_type == "UNKNOWN":
            return []
        return self._builder.build_triggers(doc_id, raw_final_type)

    @staticmethod
    def _fallback_level(
        *,
        raw_final_type: str,
        final_type_after_corridor: str,
        voted: dict | None,
    ) -> str | None:
        """
        Возвращает level для fallback payload.

        Семантика:
        - если после corridor итог UNKNOWN, level=None;
        - если был voted signal и corridor не сбросил результат в UNKNOWN,
          сохраняем level="HYBRID";
        - иначе level=None.
        """
        if final_type_after_corridor == "UNKNOWN":
            return None
        if voted is not None and raw_final_type != "UNKNOWN":
            return "HYBRID"
        return None

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    


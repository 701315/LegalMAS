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
      - вычисление corridor-скорректированного типа для логов;
      - выбор DecisionStrategy.FALLBACK_UNKNOWN / FALLBACK_LOW;
      - логирование final decision;
      - вызов builder.build(...) с сохранением исходного final_type
        как single source of truth.

    Важно:
      - в логах используется final_type_out (после unknown corridor);
      - в builder передаётся исходный final_type;
      - applicable_triggers, если не переданы явно, строятся из builder.
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

        # Для логов используем corridor-скорректированный type,
        # но builder отдаём исходный final_type, чтобы он был single source of truth.
        final_type_out = self._builder.apply_unknown_corridor(final_type, final_conf)
        zone, requires_review = self._builder.confidence_zone(final_conf)

        decided_by = (
            DecisionStrategy.FALLBACK_UNKNOWN
            if final_type_out == "UNKNOWN"
            else DecisionStrategy.FALLBACK_LOW
        )

        unknown_corridor_applied = final_type_out != (final_type or "UNKNOWN")

        voting_details = details.get("voting") or {}
        voting_score = voting_details.get("score")
        single_source_cap_applied = voting_details.get("single_source_cap_applied")
        voting_margin = details.get("voting_margin")

        log_classification_decision(
            doc_id=doc_id,
            decided_by=decided_by,
            final_type=final_type_out,
            final_confidence=final_conf,
            levels_tried=details["levels_tried"],
            started_at=started_at,
            requires_manual_review=requires_review,
            confidence_zone=zone,
            unknown_corridor_applied=unknown_corridor_applied,
            voting_score=voting_score,
            single_source_cap_applied=single_source_cap_applied,
            extra={
                "voted_type": voting_details.get("type"),
                "voting_margin": voting_margin,
                "support_count": voting_details.get("support_count"),
                "support_levels": voting_details.get("support_levels"),
            },
        )

        safe_applicable_triggers = (
            list(applicable_triggers)
            if applicable_triggers is not None
            else self._builder.build_triggers(doc_id, final_type)
        )

        return self._builder.build(
            levels_tried=details["levels_tried"],
            candidates=candidates,
            final_type=final_type,
            final_confidence=final_conf,
            level="HYBRID" if voted is not None and final_type_out != "UNKNOWN" else None,
            language=language,
            jurisdiction=jurisdiction,
            applicable_triggers=safe_applicable_triggers,
            details=details,
        )
    


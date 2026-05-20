# src/classifiers/stage8/_voting.py

"""
Взвешенное голосование по кандидатам L1–L3.

Production-версия:
- учитывает confidence и вес уровня;
- поддерживает legacy/preferred negative-сигналы;
- не делает повторный penalty по signal_quality, если он уже учтён в confidence;
- считает agreement по уникальным уровням, а не по количеству записей;
- нормализует score по сумме весов реально активных уровней;
- считает margin по нормализованной шкале;
- ограничивает single-source результат сверху (single-source cap);
- отдельно возвращает voting_score и decision confidence;
- возвращает ranking для HybridClassifier;
- остаётся обратно совместимой по ключам:
  type / confidence / margin / language / jurisdiction / ranking.
"""

from __future__ import annotations

from typing import Any

from core.config import settings


class WeightedVoter:
    """
    Принимает список кандидатов вида:
    [
        {
            "type_code": "contract1.3goodssupply",
            "confidence": 0.82,
            "level": "L2",
            "language": "ru",
            "jurisdiction": "RU",
            "signal_quality": 0.75,                 # optional
            "negative_hits": 1,                     # optional, legacy fallback
            "soft_negative_hits": 1,                # optional, preferred
            "hard_negative_hits": 0,                # optional, preferred
            "ambiguity_penalty": 0.10,              # optional
            "signal_quality_in_confidence": True,   # optional
        },
        ...
    ]

    И возвращает победителя или None.

    Основная логика:
    - каждый кандидат получает effective_score;
    - effective_score суммируется по type_code;
    - score типа затем нормализуется по сумме весов уровней,
      которые реально внесли ненулевой вклад;
    - agreement bonus добавляется после нормализации;
    - для single-source типа применяется верхний cap;
    - ranking строится по финальной нормализованной шкале;
    - decision confidence считается отдельно через margin bonus.
    """

    def __init__(self, level_weights: dict[str, float]) -> None:
        self.level_weights = level_weights
        self.single_source_cap = self._clamp(
            self._safe_float(
                getattr(settings, "CLASSIFICATION_SINGLE_SOURCE_CAP", 0.80),
                0.80,
            ),
            0.0,
            1.0,
        )

    @staticmethod
    def _safe_float(value: Any, default: float) -> float:
        """Безопасно преобразует значение в float."""
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        """Безопасно преобразует значение в int."""
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        """Ограничивает число диапазоном [low, high]."""
        return max(low, min(high, value))

    def vote(self, candidates: list[dict]) -> dict | None:
        """
        Логика production-голосования:

        1. Для каждого кандидата считаем effective_score:
           base_score = confidence * level_weight * effective_signal_quality

           где:
           - effective_signal_quality = 1.0, если signal_quality уже учтён
             внутри confidence;
           - иначе = signal_quality.

        2. Применяем negative / ambiguity penalties:
           - hard_negative_hits > 0 => effective_score = 0.0
           - soft_negative_hits => мягкое ослабление
           - ambiguity_penalty => мягкое ослабление

        3. Складываем effective_score по каждому type_code.

        4. Нормализуем score каждого типа по сумме весов только тех уровней,
           которые внесли положительный вклад.

        5. После нормализации даём agreement bonus за поддержку типа
           несколькими УНИКАЛЬНЫМИ уровнями.

        6. Если тип поддержан только одним уровнем, применяем single-source cap.

        7. Строим ranking и считаем margin между 1-м и 2-м местом
           уже в финальной нормализованной шкале.

        8. Возвращаем:
           {
             "type": ...,
             "voting_score": ...,
             "confidence": ...,
             "margin": ...,
             "language": ...,
             "jurisdiction": ...,
             "ranking": [...]
           }

        Важно:
        - если signal_quality не передан, берём 1.0;
        - если negative_hits не передан, берём 0;
        - если ambiguity_penalty не передан, берём 0.0;
        - если hard_negative_hits > 0, кандидат принудительно получает 0 score.
        """
        if not candidates:
            return None

        type_raw_scores: dict[str, float] = {}
        type_meta: dict[str, dict[str, Any]] = {}
        type_support_levels: dict[str, set[str]] = {}
        type_active_weight_sum: dict[str, float] = {}
        type_best_component_confidence: dict[str, float] = {}
        type_best_component_score: dict[str, float] = {}

        for candidate in candidates:
            type_code = candidate.get("type_code")
            if not type_code:
                continue

            level = str(candidate.get("level", "L1"))
            level_weight = self._safe_float(self.level_weights.get(level, 0.20), 0.20)
            level_weight = self._clamp(level_weight, 0.0, 1.0)

            confidence = self._clamp(
                self._safe_float(candidate.get("confidence", 0.0), 0.0),
                0.0,
                1.0,
            )
            signal_quality = self._clamp(
                self._safe_float(candidate.get("signal_quality", 1.0), 1.0),
                0.0,
                1.0,
            )

            soft_negative_hits = max(
                0,
                self._safe_int(
                    candidate.get("soft_negative_hits", candidate.get("negative_hits", 0)),
                    0,
                ),
            )
            hard_negative_hits = max(
                0,
                self._safe_int(candidate.get("hard_negative_hits", 0), 0),
            )

            ambiguity_penalty = self._clamp(
                self._safe_float(candidate.get("ambiguity_penalty", 0.0), 0.0),
                0.0,
                0.5,
            )

            sq_already_applied = bool(candidate.get("signal_quality_in_confidence", False))
            effective_signal_quality = 1.0 if sq_already_applied else signal_quality

            base_score = confidence * level_weight * effective_signal_quality

            if hard_negative_hits > 0:
                effective_score = 0.0
            else:
                negative_factor = 1.0 - min(0.60, 0.20 * soft_negative_hits)
                negative_factor = self._clamp(negative_factor, 0.0, 1.0)

                ambiguity_factor = 1.0 - ambiguity_penalty
                ambiguity_factor = self._clamp(ambiguity_factor, 0.50, 1.0)

                effective_score = base_score * negative_factor * ambiguity_factor
                effective_score = self._clamp(effective_score, 0.0, 1.0)

            type_raw_scores[type_code] = type_raw_scores.get(type_code, 0.0) + effective_score

            if effective_score > 0.0:
                type_support_levels.setdefault(type_code, set()).add(level)
                type_active_weight_sum[type_code] = (
                    type_active_weight_sum.get(type_code, 0.0) + level_weight
                )

            prev_best_score = type_best_component_score.get(type_code, -1.0)
            if effective_score > prev_best_score:
                type_best_component_score[type_code] = effective_score
                type_best_component_confidence[type_code] = confidence
                type_meta[type_code] = {
                    "language": candidate.get("language", "ru"),
                    "jurisdiction": candidate.get("jurisdiction", "RU"),
                    "best_component_score": effective_score,
                    "best_component_confidence": confidence,
                    "best_level": level,
                }

        if not type_raw_scores:
            return None

        type_normalized_scores: dict[str, float] = {}
        type_final_scores: dict[str, float] = {}
        type_agreement_bonus: dict[str, float] = {}
        type_single_source_capped: dict[str, bool] = {}

        for type_code, raw_score in type_raw_scores.items():
            active_weight_sum = type_active_weight_sum.get(type_code, 0.0)

            if active_weight_sum > 0.0:
                normalized_score = raw_score / active_weight_sum
            else:
                normalized_score = 0.0

            normalized_score = self._clamp(normalized_score, 0.0, 1.0)
            type_normalized_scores[type_code] = normalized_score

            support_level_count = len(type_support_levels.get(type_code, set()))
            agreement_adj = min(0.08, 0.04 * max(0, support_level_count - 1))
            type_agreement_bonus[type_code] = agreement_adj

            final_score = self._clamp(normalized_score + agreement_adj, 0.0, 1.0)

            single_source_capped = False
            if support_level_count == 1 and final_score > self.single_source_cap:
                final_score = self.single_source_cap
                single_source_capped = True

            type_single_source_capped[type_code] = single_source_capped
            type_final_scores[type_code] = final_score

        def _ranking_key(item: tuple[str, float]) -> tuple[float, int, float, float, str]:
            type_code, final_score = item
            support_level_count = len(type_support_levels.get(type_code, set()))
            active_weight_sum = type_active_weight_sum.get(type_code, 0.0)
            best_component_score = type_best_component_score.get(type_code, 0.0)
            return (
                final_score,
                support_level_count,
                active_weight_sum,
                best_component_score,
                type_code,
            )

        ranked = sorted(type_final_scores.items(), key=_ranking_key, reverse=True)

        best_type, best_final_score = ranked[0]
        second_final_score = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = max(0.0, best_final_score - second_final_score)

        margin_bonus = min(0.10, margin * 0.5)

        final_confidence = self._clamp(
            best_final_score + margin_bonus,
            0.0,
            1.0,
        )

        meta = type_meta.get(best_type, {})

        ranking = []
        for type_code, final_score in ranked[:5]:
            ranking.append(
                {
                    "type": type_code,
                    "score": round(final_score, 4),
                    "raw_score": round(type_raw_scores.get(type_code, 0.0), 4),
                    "normalized_score": round(type_normalized_scores.get(type_code, 0.0), 4),
                    "agreement_bonus": round(type_agreement_bonus.get(type_code, 0.0), 4),
                    "support_count": len(type_support_levels.get(type_code, set())),
                    "support_levels": sorted(type_support_levels.get(type_code, set())),
                    "active_weight_sum": round(type_active_weight_sum.get(type_code, 0.0), 4),
                    "best_component_score": round(
                        type_best_component_score.get(type_code, 0.0), 4
                    ),
                    "best_component_confidence": round(
                        type_best_component_confidence.get(type_code, 0.0), 4
                    ),
                    "single_source_capped": bool(
                        type_single_source_capped.get(type_code, False)
                    ),
                }
            )

        return {
            "type": best_type,
            "voting_score": round(best_final_score, 4),
            "confidence": round(final_confidence, 4),
            "margin": round(margin, 4),
            "language": meta.get("language", "ru"),
            "jurisdiction": meta.get("jurisdiction", "RU"),
            "single_source_cap_applied": bool(
                type_single_source_capped.get(best_type, False)
            ),
            "support_count": len(type_support_levels.get(best_type, set())),
            "support_levels": sorted(type_support_levels.get(best_type, set())),
            "ranking": ranking,
        }

    
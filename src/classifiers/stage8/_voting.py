# src/classifiers/stage8/_voting.py

"""
Взвешенное голосование по кандидатам L1–L3.

Production-версия:
- учитывает confidence и вес уровня;
- учитывает качество сигнала (signal_quality);
- учитывает отрицательные сигналы (negative_hits);
- учитывает ambiguity_penalty;
- возвращает margin и ranking для HybridClassifier;
- остаётся обратно совместимой по ключам type/confidence/language/jurisdiction.
"""

from __future__ import annotations

from typing import Any


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
            "signal_quality": 0.75,          # optional
            "negative_hits": 1,              # optional, legacy fallback
            "soft_negative_hits": 1,         # optional, preferred
            "hard_negative_hits": 0,         # optional, preferred
            "ambiguity_penalty": 0.10,       # optional
        },
        ...
    ]

    И возвращает победителя или None.

    Для непрофессионального программиста:
    - каждый кандидат получает свой "эффективный балл";
    - потом баллы складываются по типам документов;
    - если один и тот же тип поддержан несколькими уровнями, это усиливает его;
    - hard-negative сигнал считается критическим:
      такой кандидат не должен выигрывать голосование.
    """

    def __init__(self, level_weights: dict[str, float]) -> None:
        self.level_weights = level_weights

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
           effective_score =
               confidence
               * level_weight
               * signal_quality
               - negative_penalty
               - ambiguity_penalty

        2. Складываем effective_score по каждому type_code.

        3. Даём небольшой bonus за agreement:
           если один и тот же type_code поддержан несколькими уровнями,
           это повышает доверие.

        4. Считаем margin между первым и вторым местом.

        5. Возвращаем:
           {
             "type": ...,
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

        type_scores: dict[str, float] = {}
        type_meta: dict[str, dict[str, Any]] = {}
        type_support_count: dict[str, int] = {}

        for candidate in candidates:
            type_code = candidate.get("type_code")
            if not type_code:
                continue

            level = candidate.get("level", "L1")
            level_weight = self._safe_float(self.level_weights.get(level, 0.20), 0.20)

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

            # Новый preferred-контракт:
            # - soft_negative_hits: штрафуем как обычные отрицательные сигналы
            # - hard_negative_hits: считаем критическим конфликтом
            #
            # Legacy fallback:
            # - если soft_negative_hits не передан, используем old negative_hits
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

            # Дефекты 1 + 8: если signal_quality уже учтён внутри confidence (extended_v1),
            # не применяем его повторно — иначе double-penalization
            sq_already_applied = bool(candidate.get("signal_quality_in_confidence", False))
            effective_sq = 1.0 if sq_already_applied else signal_quality
            base_score = confidence * level_weight * effective_sq

            # Hard-negative сигнал — защитный стоп-кран:
            # такой кандидат не должен выигрывать голосование.
            if hard_negative_hits > 0:
                negative_penalty = 1.0
                effective_score = 0.0
            else:
                negative_penalty = min(0.36, 0.12 * soft_negative_hits)
                effective_score = max(0.0, base_score - negative_penalty - ambiguity_penalty)

            type_scores[type_code] = type_scores.get(type_code, 0.0) + effective_score
            type_support_count[type_code] = type_support_count.get(type_code, 0) + 1

            prev = type_meta.get(type_code)
            if prev is None or effective_score > prev.get("best_component_score", 0.0):
                type_meta[type_code] = {
                    "language": candidate.get("language", "ru"),
                    "jurisdiction": candidate.get("jurisdiction", "RU"),
                    "best_component_score": effective_score,
                    "best_level": level,
                }

        if not type_scores:
            return None

        # Agreement bonus удалён отсюда — применяется ПОСЛЕ нормализации (дефект 6).
        # Применять до нормализации бессмысленно: бонус масштабируется вместе с best_score.

        ranked = sorted(type_scores.items(), key=lambda item: item[1], reverse=True)
        best_type, best_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = max(0.0, best_score - second_score)

        # Дефект 2: нормализация через сумму весов активных уровней.
        # Без нормализации best_score при одном L2 максимально = 0.40,
        # что делает final_confidence <= 0.55 — ниже hybrid_accept = 0.65.
        active_weight_sum = sum(
            self._safe_float(self.level_weights.get(c.get("level", "L1"), 0.20), 0.20)
            for c in candidates
            if c.get("type_code") == best_type
        )
        if active_weight_sum > 0:
            normalized_confidence = best_score / active_weight_sum
        else:
            normalized_confidence = best_score

        # Дефект 6: agreement_bonus применяется ПОСЛЕ нормализации.
        # Предсказуемый эффект: +0.04 за каждый дополнительный согласный уровень, макс +0.08.
        support_count_best = type_support_count.get(best_type, 1)
        agreement_adj = min(0.08, 0.04 * (support_count_best - 1))

        # margin_bonus: уменьшен с min(0.15, margin) до min(0.10, margin * 0.5)
        # чтобы компенсировать рост базового confidence от нормализации
        margin_bonus = min(0.10, margin * 0.5)

        final_confidence = self._clamp(
            normalized_confidence + agreement_adj + margin_bonus,
            0.0,
            1.0,
        )

        meta = type_meta.get(best_type, {})

        return {
            "type": best_type,
            "confidence": round(final_confidence, 4),
            "margin": round(margin, 4),
            "language": meta.get("language", "ru"),
            "jurisdiction": meta.get("jurisdiction", "RU"),
            "ranking": [
                {
                    "type": type_code,
                    "score": round(score, 4),
                    "support_count": type_support_count.get(type_code, 0),
                }
                for type_code, score in ranked[:5]
            ],
        }
    

    
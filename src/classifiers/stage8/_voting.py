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
            "signal_quality": 0.75,        # optional
            "negative_hits": 1,            # optional
            "ambiguity_penalty": 0.10,     # optional
        },
        ...
    ]

    И возвращает победителя или None.
    """

    def __init__(self, level_weights: dict[str, float]) -> None:
        self.level_weights = level_weights

    @staticmethod
    def _safe_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
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
        - если ambiguity_penalty не передан, берём 0.0.
        """
        if not candidates:
            return None

        type_scores: dict[str, float] = {}
        type_meta: dict[str, dict[str, Any]] = {}
        type_support_count: dict[str, int] = {}

        for c in candidates:
            type_code = c.get("type_code")
            if not type_code:
                continue

            level = c.get("level", "L1")
            level_weight = self._safe_float(self.level_weights.get(level, 0.20), 0.20)

            confidence = self._clamp(self._safe_float(c.get("confidence", 0.0), 0.0), 0.0, 1.0)
            signal_quality = self._clamp(self._safe_float(c.get("signal_quality", 1.0), 1.0), 0.0, 1.0)

            negative_hits = max(0, self._safe_int(c.get("negative_hits", 0), 0))
            ambiguity_penalty = self._clamp(
                self._safe_float(c.get("ambiguity_penalty", 0.0), 0.0),
                0.0,
                0.5,
            )

            # Штраф за отрицательные признаки:
            # 1 hit = -0.12, 2+ hits режем сильнее, но ограничиваем потолок.
            negative_penalty = min(0.36, 0.12 * negative_hits)

            base_score = confidence * level_weight * signal_quality
            effective_score = max(0.0, base_score - negative_penalty - ambiguity_penalty)

            type_scores[type_code] = type_scores.get(type_code, 0.0) + effective_score
            type_support_count[type_code] = type_support_count.get(type_code, 0) + 1

            prev = type_meta.get(type_code)
            if prev is None or effective_score > prev.get("best_component_score", 0.0):
                type_meta[type_code] = {
                    "language": c.get("language", "ru"),
                    "jurisdiction": c.get("jurisdiction", "RU"),
                    "best_component_score": effective_score,
                    "best_level": level,
                }

        if not type_scores:
            return None

        # Agreement bonus:
        # если тип поддержан >= 2 независимыми кандидатами, немного усиливаем его.
        for type_code, support_count in type_support_count.items():
            if support_count >= 2:
                agreement_bonus = min(0.12, 0.05 * (support_count - 1))
                type_scores[type_code] += agreement_bonus

        ranked = sorted(type_scores.items(), key=lambda item: item[1], reverse=True)
        best_type, best_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = max(0.0, best_score - second_score)

        # Калибровка итогового confidence:
        # - сам score уже агрегированный;
        # - добавляем небольшой бонус за хороший margin;
        # - ограничиваем 1.0.
        final_confidence = best_score + min(0.15, margin)
        final_confidence = self._clamp(final_confidence, 0.0, 1.0)

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
    

    
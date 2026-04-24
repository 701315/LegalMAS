# src/classifiers/stage8/_voting.py
"""
Взвешенное голосование по кандидатам L1–L3.
Изолировано от HybridClassifier, чтобы можно было тестировать отдельно.
"""
from __future__ import annotations

from typing import Optional


class WeightedVoter:
    """
    Принимает список кандидатов [{type_code, confidence, level, ...}]
    и возвращает победителя или None.
    """

    def __init__(self, level_weights: dict[str, float]) -> None:
        self.level_weights = level_weights

    def vote(self, candidates: list[dict]) -> dict | None:
        """
        Для каждого кандидата:
          score(type) += confidence * weight(level)

        Возвращает:
          {type, confidence, language, jurisdiction} или None.
        """
        if not candidates:
            return None

        type_scores: dict[str, float] = {}
        type_meta: dict[str, dict] = {}
        total_weight = 0.0

        for c in candidates:
            level = c.get("level", "L1")
            w = self.level_weights.get(level, 0.20)
            type_code = c["type_code"]
            score = float(c["confidence"]) * w

            type_scores[type_code] = type_scores.get(type_code, 0.0) + score
            total_weight += w

            prev = type_meta.get(type_code)
            if prev is None or score > prev.get("score", 0.0):
                type_meta[type_code] = {
                    "language": c.get("language", "ru"),
                    "jurisdiction": c.get("jurisdiction", "RU"),
                    "score": score,
                }

        if not type_scores or total_weight <= 0.0:
            return None

        best_type = max(type_scores, key=type_scores.__getitem__)
        confidence = type_scores[best_type] / total_weight
        meta = type_meta.get(best_type, {})

        return {
            "type": best_type,
            "confidence": round(confidence, 4),
            "language": meta.get("language", "ru"),
            "jurisdiction": meta.get("jurisdiction", "RU"),
        }
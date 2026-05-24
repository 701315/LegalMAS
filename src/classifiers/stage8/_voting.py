# src/classifiers/stage8/_voting.py

"""
Взвешенное голосование по кандидатам L1–L3.

Production-версия:
- учитывает confidence и вес уровня;
- поддерживает legacy/preferred negative-сигналы;
- не делает повторный penalty по signal_quality, если он уже учтён в confidence;
- считает agreement по уникальным уровням, а не по количеству записей;
- нормализует score по ПОЛНОЙ сумме весов всех сконфигурированных уровней
  (а не только активных), что гарантирует монотонность поддержки:
  добавление любого неотрицательного согласованного сигнала не уменьшает итоговый score;
- считает margin по нормализованной шкале;
- ограничивает single-source результат сверху (single-source cap);
- учитывает dominant component floor для сильного multi-level сигнала;
- отдельно возвращает voting_score и decision confidence;
- возвращает ranking для HybridClassifier;
- остаётся обратно совместимой по ключам:
  type / confidence / margin / language / jurisdiction / ranking.

UPDATED FINAL:
- bounded aggregation внутри одного уровня: вклад type_code на уровне
  не суммируется бесконтрольно по всем rows, а берётся как best-per-level score;
- dominant floor стал более score-driven и не опирается на raw confidence;
- dominant floor uplift не применяется для single-source;
- agreement bonus применяется более консервативно для слабых normalized scores;
- active weight sum считается по уникальным support levels;
- ranking/debug payload дополнен per-level contribution breakdown.

REFACTOR (monotonicity fix):
- нормализация теперь делится на _total_weight_sum (сумма весов ВСЕХ уровней),
  а не на active_weight_sum (сумма весов только уровней с ненулевым вкладом);
- это устраняет эффект "размывания score" при добавлении слабого уровня:
  general_sale (L1 only, conf=0.65) больше не побеждает real_estate (L1+L2+L3);
- _ranking_key: active_weight_sum заменён на raw_score как tie-breaker —
  тип с большим суммарным сигналом предпочтительнее при равном voting_score;
- ranking payload дополнен полем total_weight_sum для самодостаточных логов.
"""

from __future__ import annotations

from typing import Any

from core.config import settings


class WeightedVoter:
    """
    Принимает список кандидатов вида:
    [
        {
            "type_code": "contract_1.3_supply",
            "confidence": 0.82,
            "level": "L2",
            "language": "ru",
            "jurisdiction": "RU",
            "signal_quality": 0.75,
            "negative_hits": 1,
            "soft_negative_hits": 1,
            "hard_negative_hits": 0,
            "ambiguity_penalty": 0.10,
            "signal_quality_in_confidence": True,
            "parent": "class_1_transfer_of_ownership",
            "group": "group_1_ownership",
        },
        ...
    ]

    И возвращает победителя или None.

    Основная логика:
    - каждый кандидат получает effective_score;
    - внутри каждого уровня вклад type_code ограничивается best-per-level score;
    - score типа нормализуется по _total_weight_sum — сумме весов ВСЕХ
      сконфигурированных уровней (инвариант монотонности поддержки);
    - agreement bonus добавляется после нормализации;
    - dominant floor не даёт сильному лучшему multi-level сигналу слишком "просесть",
      но не должен искусственно переоценивать raw-confidence spike;
    - для single-source типа применяется upper cap;
    - ranking строится по финальной нормализованной шкале;
    - decision confidence считается отдельно через margin bonus.
    """

    def __init__(self, level_weights: dict[str, float]) -> None:
        self.level_weights = level_weights

        # Знаменатель нормализации — сумма весов ВСЕХ уровней (не только активных).
        # Гарантирует INV-1 (монотонность): добавление любого уровня
        # с effective_score >= 0 не уменьшает normalized_score.
        self._total_weight_sum: float = max(
            sum(
                self._clamp(self._safe_float(w, 0.0), 0.0, 1.0)
                for w in level_weights.values()
            ),
            1e-9,
        )

        self.single_source_cap: float = settings.CLASSIFICATION_SINGLE_SOURCE_CAP
        self.single_source_high_quality_cap: float = settings.CLASSIFICATION_SINGLE_SOURCE_HIGH_QUALITY_CAP
        self.dominant_floor_factor: float = settings.CLASSIFICATION_DOMINANT_FLOOR_FACTOR
        self.max_agreement_bonus: float = settings.CLASSIFICATION_MAX_AGREEMENT_BONUS
        self.agreement_bonus_step: float = settings.CLASSIFICATION_AGREEMENT_BONUS_STEP
        self.multi_level_floor_uplift: float = settings.CLASSIFICATION_MULTI_LEVEL_FLOOR_UPLIFT
        self.single_source_high_conf_min: float = settings.CLASSIFICATION_SINGLE_SOURCE_HIGH_CONF_MIN
        self.margin_bonus_strong_score_min = settings.CLASSIFICATION_MARGIN_BONUS_STRONG_SCORE_MIN
        self.margin_bonus_medium_score_min = settings.CLASSIFICATION_MARGIN_BONUS_MEDIUM_SCORE_MIN
        self.margin_bonus_strong_cap = settings.CLASSIFICATION_MARGIN_BONUS_STRONG_CAP
        self.margin_bonus_strong_factor = settings.CLASSIFICATION_MARGIN_BONUS_STRONG_FACTOR
        self.margin_bonus_medium_cap = settings.CLASSIFICATION_MARGIN_BONUS_MEDIUM_CAP
        self.margin_bonus_medium_factor = settings.CLASSIFICATION_MARGIN_BONUS_MEDIUM_FACTOR
        self.agreement_bonus_min_score = settings.CLASSIFICATION_AGREEMENT_BONUS_MIN_SCORE
        self.agreement_bonus_full_score = settings.CLASSIFICATION_AGREEMENT_BONUS_FULL_SCORE
        self.agreement_bonus_weak_factor = settings.CLASSIFICATION_AGREEMENT_BONUS_WEAK_FACTOR
        self.ambiguity_penalty_max = settings.CLASSIFICATION_AMBIGUITY_PENALTY_MAX
        self.ambiguity_factor_min = settings.CLASSIFICATION_AMBIGUITY_FACTOR_MIN
        self.soft_negative_max_penalty = settings.CLASSIFICATION_SOFT_NEGATIVE_MAX_PENALTY
        self.soft_negative_step = settings.CLASSIFICATION_SOFT_NEGATIVE_STEP
        self.default_level_weight: float = settings.CLASSIFICATION_DEFAULT_LEVEL_WEIGHT


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

    @staticmethod
    def _normalize_type_code(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def _choose_single_source_cap(
        best_component_confidence: float,
        strict_cap: float,
        high_quality_cap: float,
        high_conf_min: float,
    ) -> float:
        if best_component_confidence >= high_conf_min:
            return max(strict_cap, high_quality_cap)
        return strict_cap

    def _compute_margin_bonus(
        self,
        best_voting_score: float,
        margin: float,
        support_level_count: int,
    ) -> float:
        if support_level_count < 2:
            return 0.0
        if best_voting_score >= self.margin_bonus_strong_score_min:
            return min(self.margin_bonus_strong_cap, margin * self.margin_bonus_strong_factor)
        if best_voting_score >= self.margin_bonus_medium_score_min:
            return min(self.margin_bonus_medium_cap, margin * self.margin_bonus_medium_factor)
        return 0.0

    def _compute_agreement_bonus(
        self,
        *,
        normalized_score: float,
        support_level_count: int,
    ) -> float:
        """
        Agreement bonus зависит от количества уникальных уровней,
        но ослабляется для слабого normalized score, чтобы не усиливать
        искусственно слабый consensus.
        """
        raw_bonus = min(
            self.max_agreement_bonus,
            self.agreement_bonus_step * max(0, support_level_count - 1),
        )

        if raw_bonus <= 0.0:
            return 0.0
        if normalized_score < self.agreement_bonus_min_score:
            return 0.0
        if normalized_score < self.agreement_bonus_full_score:
            return raw_bonus * self.agreement_bonus_weak_factor
        return raw_bonus

    def _compute_dominant_floor(
        self,
        *,
        best_component_score: float,
        normalized_score: float,
        support_level_count: int,
    ) -> float:
        """
        Dominant floor должен быть score-driven.
        Для single-source uplift не применяется.
        Для multi-level разрешён только небольшой controlled uplift.
        """
        best_component_score = self._clamp(best_component_score, 0.0, 1.0)
        normalized_score = self._clamp(normalized_score, 0.0, 1.0)

        if support_level_count <= 1:
            return best_component_score

        anchor = max(best_component_score, normalized_score)
        uplift_cap = best_component_score + self.multi_level_floor_uplift
        factor_cap = best_component_score * max(1.0, self.dominant_floor_factor)
        floor = min(max(anchor, best_component_score), uplift_cap, factor_cap)

        return self._clamp(max(best_component_score, floor), 0.0, 1.0)

    def vote(self, candidates: list[dict]) -> dict | None:
        if not candidates:
            return None

        type_meta: dict[str, dict[str, Any]] = {}
        type_support_levels: dict[str, set[str]] = {}
        type_best_component_confidence: dict[str, float] = {}
        type_best_component_score: dict[str, float] = {}
        type_component_count: dict[str, int] = {}
        type_active_component_count: dict[str, int] = {}
        type_candidate_breakdown: dict[str, list[dict[str, Any]]] = {}
        type_parent_values: dict[str, set[str]] = {}
        type_group_values: dict[str, set[str]] = {}

        # bounded aggregation per level
        type_level_scores: dict[str, dict[str, float]] = {}
        type_level_best_component: dict[str, dict[str, dict[str, Any]]] = {}

        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue

            type_code = self._normalize_type_code(candidate.get("type_code"))
            if not type_code:
                continue

            level = str(candidate.get("level", "L1") or "L1").strip()
            level_weight = self._safe_float(
                self.level_weights.get(level, self.default_level_weight),
                self.default_level_weight,
            )
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
                self.ambiguity_penalty_max,
            )

            sq_already_applied = bool(candidate.get("signal_quality_in_confidence", False))
            effective_signal_quality = 1.0 if sq_already_applied else signal_quality

            base_score = confidence * level_weight * effective_signal_quality

            if hard_negative_hits > 0:
                negative_factor = 0.0
                ambiguity_factor = 1.0
                effective_score = 0.0
            else:
                negative_penalty = min(
                    self.soft_negative_max_penalty,
                    self.soft_negative_step * soft_negative_hits,
                )
                negative_factor = 1.0 - negative_penalty
                negative_factor = self._clamp(negative_factor, 0.0, 1.0)

                ambiguity_factor = 1.0 - ambiguity_penalty
                ambiguity_factor = self._clamp(ambiguity_factor, self.ambiguity_factor_min, 1.0)

                effective_score = base_score * negative_factor * ambiguity_factor
                effective_score = self._clamp(effective_score, 0.0, 1.0)

            type_component_count[type_code] = type_component_count.get(type_code, 0) + 1

            if effective_score > 0.0:
                type_support_levels.setdefault(type_code, set()).add(level)
                type_active_component_count[type_code] = (
                    type_active_component_count.get(type_code, 0) + 1
                )

                prev_level_score = type_level_scores.setdefault(type_code, {}).get(level, 0.0)
                if effective_score > prev_level_score:
                    type_level_scores[type_code][level] = effective_score
                    type_level_best_component.setdefault(type_code, {})[level] = {
                        "effective_score": effective_score,
                        "confidence": confidence,
                        "signal_quality": signal_quality,
                        "signal_quality_in_confidence": sq_already_applied,
                        "effective_signal_quality": effective_signal_quality,
                        "level_weight": level_weight,
                        "soft_negative_hits": soft_negative_hits,
                        "hard_negative_hits": hard_negative_hits,
                        "negative_factor": negative_factor,
                        "ambiguity_penalty": ambiguity_penalty,
                        "ambiguity_factor": ambiguity_factor,
                        "base_score": base_score,
                    }

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

            parent = self._normalize_type_code(candidate.get("parent"))
            group = self._normalize_type_code(candidate.get("group"))
            if parent:
                type_parent_values.setdefault(type_code, set()).add(parent)
            if group:
                type_group_values.setdefault(type_code, set()).add(group)

            if hard_negative_hits > 0:
                type_candidate_breakdown.setdefault(type_code, []).append(
                    {
                        "level": level,
                        "confidence": round(confidence, 4),
                        "signal_quality": round(signal_quality, 4),
                        "signal_quality_in_confidence": sq_already_applied,
                        "effective_signal_quality": round(effective_signal_quality, 4),
                        "level_weight": round(level_weight, 4),
                        "soft_negative_hits": soft_negative_hits,
                        "hard_negative_hits": hard_negative_hits,
                        "negative_factor": 0.0,
                        "ambiguity_penalty": round(ambiguity_penalty, 4),
                        "ambiguity_factor": 1.0,
                        "base_score": round(base_score, 4),
                        "effective_score": 0.0,
                        "hard_suppressed": True,
                    }
                )
            else:
                type_candidate_breakdown.setdefault(type_code, []).append(
                    {
                        "level": level,
                        "confidence": round(confidence, 4),
                        "signal_quality": round(signal_quality, 4),
                        "signal_quality_in_confidence": sq_already_applied,
                        "effective_signal_quality": round(effective_signal_quality, 4),
                        "level_weight": round(level_weight, 4),
                        "soft_negative_hits": soft_negative_hits,
                        "hard_negative_hits": hard_negative_hits,
                        "negative_factor": round(negative_factor, 4),
                        "ambiguity_penalty": round(ambiguity_penalty, 4),
                        "ambiguity_factor": round(ambiguity_factor, 4),
                        "base_score": round(base_score, 4),
                        "effective_score": round(effective_score, 4),
                        "hard_suppressed": False,
                    }
                )

        if not type_level_scores:
            return None

        type_raw_scores: dict[str, float] = {
            type_code: sum(level_scores.values())
            for type_code, level_scores in type_level_scores.items()
        }

        type_active_weight_sum: dict[str, float] = {}
        for type_code, support_levels in type_support_levels.items():
            type_active_weight_sum[type_code] = sum(
                self._clamp(
                    self._safe_float(
                        self.level_weights.get(level, self.default_level_weight),
                        self.default_level_weight,
                    ),
                    0.0,
                    1.0,
                )
                for level in support_levels
            )

        type_normalized_scores: dict[str, float] = {}
        type_voting_scores: dict[str, float] = {}
        type_agreement_bonus: dict[str, float] = {}
        type_single_source_capped: dict[str, bool] = {}
        type_dominant_floor: dict[str, float] = {}
        type_cap_used: dict[str, float] = {}

        for type_code, raw_score in type_raw_scores.items():
            # ─── FIX: делим на _total_weight_sum (сумма весов ВСЕХ уровней),
            # а не на active_weight_sum (только активных).
            # Это устраняет нарушение монотонности: тип L1+L2+L3 с суммарным
            # raw_score > raw_score типа L1-only теперь гарантированно выигрывает.
            normalized_score = raw_score / self._total_weight_sum
            normalized_score = self._clamp(normalized_score, 0.0, 1.0)
            type_normalized_scores[type_code] = normalized_score

            support_level_count = len(type_support_levels.get(type_code, set()))
            agreement_adj = self._compute_agreement_bonus(
                normalized_score=normalized_score,
                support_level_count=support_level_count,
            )
            type_agreement_bonus[type_code] = agreement_adj

            score_after_agreement = self._clamp(normalized_score + agreement_adj, 0.0, 1.0)

            best_component_conf = type_best_component_confidence.get(type_code, 0.0)
            best_component_score = type_best_component_score.get(type_code, 0.0)

            dominant_floor = self._compute_dominant_floor(
                best_component_score=best_component_score,
                normalized_score=normalized_score,
                support_level_count=support_level_count,
            )
            type_dominant_floor[type_code] = dominant_floor

            voting_score = max(score_after_agreement, dominant_floor)
            voting_score = self._clamp(voting_score, 0.0, 1.0)

            single_source_capped = False
            cap_used = 1.0
            if support_level_count == 1:
                cap_used = self._choose_single_source_cap(
                    best_component_confidence=best_component_conf,
                    strict_cap=self.single_source_cap,
                    high_quality_cap=self.single_source_high_quality_cap,
                    high_conf_min=self.single_source_high_conf_min,
                )
                if voting_score > cap_used:
                    voting_score = cap_used
                    single_source_capped = True

            type_cap_used[type_code] = cap_used
            type_single_source_capped[type_code] = single_source_capped
            type_voting_scores[type_code] = voting_score

        def _ranking_key(item: tuple[str, float]) -> tuple[float, int, float, float, str]:
            type_code, voting_score = item
            support_level_count = len(type_support_levels.get(type_code, set()))
            # ─── FIX: raw_score вместо active_weight_sum.
            # Тип с большим суммарным взвешенным сигналом предпочтительнее
            # при равном voting_score. active_weight_sum не несёт этой семантики
            # после перехода на total_weight_sum нормализацию.
            raw_score = type_raw_scores.get(type_code, 0.0)
            best_component_score = type_best_component_score.get(type_code, 0.0)
            return (
                voting_score,
                support_level_count,
                raw_score,
                best_component_score,
                type_code,
            )

        ranked = sorted(type_voting_scores.items(), key=_ranking_key, reverse=True)

        best_type, best_voting_score = ranked[0]
        second_type = ranked[1][0] if len(ranked) > 1 else None
        second_voting_score = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = max(0.0, best_voting_score - second_voting_score)

        best_parents = type_parent_values.get(best_type, set())
        second_parents = type_parent_values.get(second_type, set()) if second_type else set()
        best_groups = type_group_values.get(best_type, set())
        second_groups = type_group_values.get(second_type, set()) if second_type else set()

        parent_conflict = bool(
            best_parents and second_parents and best_parents.isdisjoint(second_parents)
        )
        group_conflict = bool(
            best_groups and second_groups and best_groups.isdisjoint(second_groups)
        )
        domain_conflict = parent_conflict or group_conflict

        best_support_level_count = len(type_support_levels.get(best_type, set()))
        margin_bonus = self._compute_margin_bonus(
            best_voting_score=best_voting_score,
            margin=margin,
            support_level_count=best_support_level_count,
        )
        decision_confidence = self._clamp(
            best_voting_score + margin_bonus,
            0.0,
            1.0,
        )

        meta = type_meta.get(best_type, {})

        ranking = []
        for type_code, voting_score in ranked[:5]:
            per_level_contributions = []
            for level, level_score in sorted(type_level_scores.get(type_code, {}).items()):
                level_meta = type_level_best_component.get(type_code, {}).get(level, {})
                per_level_contributions.append(
                    {
                        "level": level,
                        "score": round(level_score, 4),
                        "confidence": round(level_meta.get("confidence", 0.0), 4),
                        "base_score": round(level_meta.get("base_score", 0.0), 4),
                        "effective_score": round(level_meta.get("effective_score", 0.0), 4),
                        "signal_quality": round(level_meta.get("signal_quality", 1.0), 4),
                        "signal_quality_in_confidence": bool(
                            level_meta.get("signal_quality_in_confidence", False)
                        ),
                        "effective_signal_quality": round(
                            level_meta.get("effective_signal_quality", 1.0), 4
                        ),
                        "level_weight": round(level_meta.get("level_weight", 0.0), 4),
                        "soft_negative_hits": int(level_meta.get("soft_negative_hits", 0)),
                        "hard_negative_hits": int(level_meta.get("hard_negative_hits", 0)),
                        "negative_factor": round(level_meta.get("negative_factor", 1.0), 4),
                        "ambiguity_penalty": round(
                            level_meta.get("ambiguity_penalty", 0.0), 4
                        ),
                        "ambiguity_factor": round(level_meta.get("ambiguity_factor", 1.0), 4),
                    }
                )

            ranking.append(
                {
                    "type": type_code,
                    "score": round(voting_score, 4),
                    "raw_score": round(type_raw_scores.get(type_code, 0.0), 4),
                    "normalized_score": round(type_normalized_scores.get(type_code, 0.0), 4),
                    "agreement_bonus": round(type_agreement_bonus.get(type_code, 0.0), 4),
                    "dominant_floor": round(type_dominant_floor.get(type_code, 0.0), 4),
                    "support_count": len(type_support_levels.get(type_code, set())),
                    "support_levels": sorted(type_support_levels.get(type_code, set())),
                    "active_weight_sum": round(type_active_weight_sum.get(type_code, 0.0), 4),
                    # ─── NEW: total_weight_sum в каждой строке ranking —
                    # делает лог самодостаточным при разборе без контекста вызова.
                    "total_weight_sum": round(self._total_weight_sum, 4),
                    "best_component_score": round(
                        type_best_component_score.get(type_code, 0.0), 4
                    ),
                    "best_component_confidence": round(
                        type_best_component_confidence.get(type_code, 0.0), 4
                    ),
                    "single_source_capped": bool(
                        type_single_source_capped.get(type_code, False)
                    ),
                    "single_source_cap_used": round(type_cap_used.get(type_code, 1.0), 4),
                    "component_count": type_component_count.get(type_code, 0),
                    "active_component_count": type_active_component_count.get(type_code, 0),
                    "selected_component_count": len(type_level_scores.get(type_code, {})),
                    "parent_values": sorted(type_parent_values.get(type_code, set())),
                    "group_values": sorted(type_group_values.get(type_code, set())),
                    "level_contributions": per_level_contributions,
                    "components": type_candidate_breakdown.get(type_code, []),
                }
            )

        return {
            "type": best_type,
            "voting_score": round(best_voting_score, 4),
            "confidence": round(decision_confidence, 4),
            "margin": round(margin, 4),
            "language": meta.get("language", "ru"),
            "jurisdiction": meta.get("jurisdiction", "RU"),
            "single_source_cap_applied": bool(
                type_single_source_capped.get(best_type, False)
            ),
            "single_source_cap_used": round(type_cap_used.get(best_type, 1.0), 4),
            "support_count": best_support_level_count,
            "support_levels": sorted(type_support_levels.get(best_type, set())),
            "best_level": meta.get("best_level", "L1"),
            "best_component_confidence": round(
                type_best_component_confidence.get(best_type, 0.0), 4
            ),
            "dominant_floor": round(type_dominant_floor.get(best_type, 0.0), 4),
            "domain_conflict": domain_conflict,
            "parent_conflict": parent_conflict,
            "group_conflict": group_conflict,
            "top2_types": [best_type] + ([second_type] if second_type else []),
            "ranking": ranking,
        }
    
    

    
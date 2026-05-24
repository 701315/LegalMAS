# tests/unit/test_voting_monotonicity.py
"""
Инвариантные тесты для WeightedVoter.
Проверяют монотонность, специфичность и edge-cases.
"""

import pytest
from src.classifiers.stage8._voting import WeightedVoter


class TestMonotonicityInvariant:
    """INV-1: Добавление неотрицательного согласованного сигнала не уменьшает score."""

    def test_adding_weak_level_does_not_reduce_score(self) -> None:
        voter = WeightedVoter(level_weights={"L1": 0.2, "L2": 0.4, "L3": 0.4})
        
        # Базовый кандидат: только L1
        candidates_l1_only = [
            {
                "type_code": "contract_1.1_general_sale",
                "confidence": 0.65,
                "level": "L1",
                "signal_quality": 1.0,
                "ambiguity_penalty": 0.0,
                "hard_negative_hits": 0,
                "soft_negative_hits": 0,
            }
        ]
        
        result_l1 = voter.vote(candidates_l1_only)
        assert result_l1 is not None
        score_l1 = result_l1["voting_score"]
        
        # Тот же кандидат + слабый, но согласованный L3
        candidates_l1_l3 = candidates_l1_only + [
            {
                "type_code": "contract_1.1_general_sale",
                "confidence": 0.03,  # слабый сигнал
                "level": "L3",
                "signal_quality": 0.77,
                "ambiguity_penalty": 0.15,
                "hard_negative_hits": 0,
                "soft_negative_hits": 0,
            }
        ]
        
        result_l1_l3 = voter.vote(candidates_l1_l3)
        assert result_l1_l3 is not None
        score_l1_l3 = result_l1_l3["voting_score"]
        
        # INV-1: score не должен уменьшиться
        assert score_l1_l3 >= score_l1, (
            f"Monotonicity violated: {score_l1_l3:.4f} < {score_l1:.4f}"
        )

    def test_multi_level_beats_single_level_with_same_l1(self) -> None:
        voter = WeightedVoter(level_weights={"L1": 0.2, "L2": 0.4, "L3": 0.4})
        
        # generic_sale: только L1, conf=0.65
        generic = [
            {
                "type_code": "contract_1.1_general_sale",
                "confidence": 0.65,
                "level": "L1",
                "signal_quality": 1.0,
                "ambiguity_penalty": 0.0,
                "hard_negative_hits": 0,
                "soft_negative_hits": 0,
            }
        ]
        
        # real_estate: L1+L2+L3, L1=0.66, L2=0.67, L3=0.03
        specific = [
            {
                "type_code": "contract_1.6_real_estate",
                "confidence": 0.66,
                "level": "L1",
                "signal_quality": 1.0,
                "ambiguity_penalty": 0.0,
                "hard_negative_hits": 0,
                "soft_negative_hits": 0,
            },
            {
                "type_code": "contract_1.6_real_estate",
                "confidence": 0.67,
                "level": "L2",
                "signal_quality": 0.33,
                "ambiguity_penalty": 0.0,
                "hard_negative_hits": 0,
                "soft_negative_hits": 0,
            },
            {
                "type_code": "contract_1.6_real_estate",
                "confidence": 0.03,
                "level": "L3",
                "signal_quality": 0.77,
                "ambiguity_penalty": 0.15,
                "hard_negative_hits": 0,
                "soft_negative_hits": 0,
            },
        ]
        
        result = voter.vote(generic + specific)
        assert result is not None
        
        # real_estate должен выиграть за счёт multi-level support
        assert result["type"] == "contract_1.6_real_estate", (
            f"Expected real_estate, got {result['type']}. "
            f"Scores: real_estate={result['ranking'][0]['score']:.4f}, "
            f"general_sale={result['ranking'][1]['score']:.4f}"
        )


class TestSpecificityPreference:
    """INV-2: Специфичный подтип с text-level признаками предпочтительнее generic."""

    def test_l2_text_signal_boosts_specific_type(self) -> None:
        voter = WeightedVoter(level_weights={"L1": 0.2, "L2": 0.4, "L3": 0.4})
        
        candidates = [
            # generic: только L1
            {
                "type_code": "contract_1.1_general_sale",
                "confidence": 0.65,
                "level": "L1",
                "signal_quality": 1.0,
                "ambiguity_penalty": 0.0,
                "hard_negative_hits": 0,
                "soft_negative_hits": 0,
            },
            # specific: L1 + L2 с текст-сигналом
            {
                "type_code": "contract_1.6_real_estate",
                "confidence": 0.66,
                "level": "L1",
                "signal_quality": 1.0,
                "ambiguity_penalty": 0.0,
                "hard_negative_hits": 0,
                "soft_negative_hits": 0,
            },
            {
                "type_code": "contract_1.6_real_estate",
                "confidence": 0.67,
                "level": "L2",
                "signal_quality": 0.33,  # L2 дал слабый, но специфичный сигнал
                "ambiguity_penalty": 0.0,
                "hard_negative_hits": 0,
                "soft_negative_hits": 0,
            },
        ]
        
        result = voter.vote(candidates)
        assert result is not None
        
        assert result["type"] == "contract_1.6_real_estate"
        assert result["support_count"] >= 2  # multi-level support


class TestEdgeCases:
    """Edge-cases и защитные инварианты."""

    def test_single_source_cap_selection_logic(self) -> None:
        """
        Проверяет логику выбора cap в зависимости от confidence.
        Примечание: при монотонной нормализации (_total_weight_sum)
        одиночный L1-сигнал с весом 0.2 физически не может превысить
        порог cap (0.80/0.88), поэтому тестируется сам алгоритм выбора порога.
        """
        voter = WeightedVoter(level_weights={"L1": 0.2, "L2": 0.4, "L3": 0.4})
        
        # Высокий confidence (>= 0.90) → выбирается high_quality_cap (0.88)
        cap_high = voter._choose_single_source_cap(
            best_component_confidence=0.95,
            strict_cap=voter.single_source_cap,           # 0.80
            high_quality_cap=voter.single_source_high_quality_cap,  # 0.88
            high_conf_min=voter.single_source_high_conf_min,        # 0.90
        )
        assert cap_high == 0.88
        
        # Низкий confidence (< 0.90) → выбирается strict_cap (0.80)
        cap_low = voter._choose_single_source_cap(
            best_component_confidence=0.70,
            strict_cap=voter.single_source_cap,
            high_quality_cap=voter.single_source_high_quality_cap,
            high_conf_min=voter.single_source_high_conf_min,
        )
        assert cap_low == 0.80

    def test_empty_candidates_returns_none(self) -> None:
        voter = WeightedVoter(level_weights={"L1": 0.2, "L2": 0.4, "L3": 0.4})
        assert voter.vote([]) is None

    def test_hard_negative_suppresses_completely(self) -> None:
        voter = WeightedVoter(level_weights={"L1": 0.2, "L2": 0.4, "L3": 0.4})
        
        candidates = [
            {
                "type_code": "contract_1.1_general_sale",
                "confidence": 0.9,
                "level": "L1",
                "signal_quality": 1.0,
                "ambiguity_penalty": 0.0,
                "hard_negative_hits": 1,  # hard suppression
                "soft_negative_hits": 0,
            }
        ]
        
        result = voter.vote(candidates)
        
        # hard_negative должен полностью подавить вклад → voter вернёт None
        # или voting_score == 0.0, если fallback логика сработает иначе
        if result is not None:
            assert result["voting_score"] == 0.0
        else:
            assert result is None



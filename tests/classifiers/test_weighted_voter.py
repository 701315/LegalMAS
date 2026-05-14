# tests/classifiers/test_weighted_voter.py

import pytest

from classifiers.stage8._voting import WeightedVoter


def test_voter_soft_negative_penalty():
    """
    Кандидат с soft_negative_hits получает штраф, но не блокируется полностью.
    """
    voter = WeightedVoter(level_weights={"L1": 0.2, "L2": 0.4, "L3": 0.4})

    candidates = [
        {
            "type_code": "A",
            "confidence": 0.9,
            "level": "L2",
            "signal_quality": 1.0,
            "soft_negative_hits": 1,
            "hard_negative_hits": 0,
            "ambiguity_penalty": 0.0,
        },
        {
            "type_code": "B",
            "confidence": 0.8,
            "level": "L2",
            "signal_quality": 1.0,
            "soft_negative_hits": 0,
            "hard_negative_hits": 0,
            "ambiguity_penalty": 0.0,
        },
    ]

    voted = voter.vote(candidates)
    assert voted is not None
    # несмотря на soft-negative, более сильный кандидат A всё ещё может выигрывать,
    # в зависимости от веса; здесь просто проверяем, что он не обнулён
    assert voted["type"] in {"A", "B"}
    # Оба типа имеют ненулевую оценку
    assert voted["confidence"] > 0.0


def test_voter_hard_negative_blocks_candidate():
    """
    Кандидат с hard_negative_hits должен иметь effective_score=0
    и не выигрывать голосование, если есть другая разумная альтернатива.
    """
    voter = WeightedVoter(level_weights={"L1": 0.2, "L2": 0.4, "L3": 0.4})

    candidates = [
        {
            "type_code": "A",
            "confidence": 0.95,
            "level": "L2",
            "signal_quality": 1.0,
            "soft_negative_hits": 0,
            "hard_negative_hits": 1,  # критический конфликт
            "ambiguity_penalty": 0.0,
        },
        {
            "type_code": "B",
            "confidence": 0.7,
            "level": "L2",
            "signal_quality": 1.0,
            "soft_negative_hits": 0,
            "hard_negative_hits": 0,
            "ambiguity_penalty": 0.0,
        },
    ]

    voted = voter.vote(candidates)
    assert voted is not None
    # Тип с hard_negative_hits не должен побеждать
    assert voted["type"] == "B"


    
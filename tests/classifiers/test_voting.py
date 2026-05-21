import pytest

from classifiers.stage8._voting import WeightedVoter


@pytest.fixture
def voter():
    return WeightedVoter(
        {
            "L1": 0.20,
            "L2": 0.40,
            "L3": 0.40,
        }
    )


def _by_type(result: dict) -> dict:
    return {item["type"]: item for item in result["ranking"]}


def test_vote_returns_none_for_empty_candidates(voter):
    assert voter.vote([]) is None


def test_single_source_cap_applied_for_single_source_candidate(voter):
    candidates = [
        {
            "type_code": "contract_1.6_real_estate",
            "confidence": 0.97,
            "level": "L2",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
            "language": "ru",
            "jurisdiction": "RU",
        }
    ]

    result = voter.vote(candidates)

    assert result is not None
    assert result["type"] == "contract_1.6_real_estate"
    assert result["support_count"] == 1
    assert result["support_levels"] == ["L2"]
    assert result["single_source_cap_applied"] is True
    assert result["single_source_cap_used"] >= 0.80
    assert result["voting_score"] <= result["single_source_cap_used"]


def test_multi_source_support_recorded_and_ranked(voter):
    candidates = [
        {
            "type_code": "contract_1.6_real_estate",
            "confidence": 0.74,
            "level": "L2",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
            "language": "ru",
            "jurisdiction": "RU",
        },
        {
            "type_code": "contract_1.6_real_estate",
            "confidence": 0.76,
            "level": "L3",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
            "language": "ru",
            "jurisdiction": "RU",
        },
        {
            "type_code": "contract_1.1_general_sale",
            "confidence": 0.90,
            "level": "L2",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
            "language": "ru",
            "jurisdiction": "RU",
        },
    ]

    result = voter.vote(candidates)

    assert result is not None
    ranking = _by_type(result)

    assert "contract_1.6_real_estate" in ranking
    assert ranking["contract_1.6_real_estate"]["support_count"] == 2
    assert ranking["contract_1.6_real_estate"]["agreement_bonus"] >= 0.0
    assert set(ranking["contract_1.6_real_estate"]["support_levels"]) == {"L2", "L3"}


def test_dominant_floor_is_exposed_for_supported_type(voter):
    candidates = [
        {
            "type_code": "contract_5.1_loan",
            "confidence": 0.92,
            "level": "L3",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
            "language": "ru",
            "jurisdiction": "RU",
        },
        {
            "type_code": "contract_5.1_loan",
            "confidence": 0.30,
            "level": "L2",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
            "language": "ru",
            "jurisdiction": "RU",
        },
    ]

    result = voter.vote(candidates)

    assert result is not None
    ranking = _by_type(result)
    loan = ranking["contract_5.1_loan"]

    assert loan["support_count"] == 2
    assert loan["dominant_floor"] >= 0.0
    assert loan["score"] >= 0.0


def test_soft_negative_and_ambiguity_reduce_raw_score(voter):
    candidates = [
        {
            "type_code": "contract_1.5_services",
            "confidence": 0.90,
            "level": "L2",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
            "soft_negative_hits": 2,
            "ambiguity_penalty": 0.20,
            "language": "ru",
            "jurisdiction": "RU",
        },
        {
            "type_code": "contract_1.1_general_sale",
            "confidence": 0.65,
            "level": "L3",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
            "language": "ru",
            "jurisdiction": "RU",
        },
    ]

    result = voter.vote(candidates)

    assert result is not None
    ranking = _by_type(result)
    services = ranking["contract_1.5_services"]

    assert services["raw_score"] < 0.90 * 0.40


def test_signal_quality_applied_only_when_not_included_in_confidence(voter):
    candidates = [
        {
            "type_code": "contract_1.6_real_estate",
            "confidence": 0.80,
            "level": "L2",
            "signal_quality": 0.50,
            "signal_quality_in_confidence": False,
            "language": "ru",
            "jurisdiction": "RU",
        },
        {
            "type_code": "contract_5.1_loan",
            "confidence": 0.80,
            "level": "L2",
            "signal_quality": 0.50,
            "signal_quality_in_confidence": True,
            "language": "ru",
            "jurisdiction": "RU",
        },
    ]

    result = voter.vote(candidates)

    assert result is not None
    ranking = _by_type(result)

    real_estate = ranking["contract_1.6_real_estate"]
    loan = ranking["contract_5.1_loan"]

    assert real_estate["raw_score"] < loan["raw_score"]


def test_hard_negative_candidate_is_still_traced_in_ranking(voter):
    candidates = [
        {
            "type_code": "contract_1.6_real_estate",
            "confidence": 0.90,
            "level": "L2",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
            "hard_negative_hits": 1,
            "language": "ru",
            "jurisdiction": "RU",
        },
        {
            "type_code": "contract_1.1_general_sale",
            "confidence": 0.70,
            "level": "L3",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
            "language": "ru",
            "jurisdiction": "RU",
        },
    ]

    result = voter.vote(candidates)

    assert result is not None
    ranking = _by_type(result)

    assert "contract_1.6_real_estate" in ranking
    assert "contract_1.1_general_sale" in ranking


def test_domain_conflict_detected_from_top2_parent_values(voter):
    candidates = [
        {
            "type_code": "contract_1.6_real_estate",
            "confidence": 0.86,
            "level": "L2",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
            "parent": "class_1_transfer_of_ownership",
            "group": "group_1_ownership",
            "language": "ru",
            "jurisdiction": "RU",
        },
        {
            "type_code": "contract_5.1_loan",
            "confidence": 0.84,
            "level": "L3",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
            "parent": "class_5_financial_security",
            "group": "group_5_finance",
            "language": "ru",
            "jurisdiction": "RU",
        },
    ]

    result = voter.vote(candidates)

    assert result is not None
    assert result["domain_conflict"] is True
    assert result["parent_conflict"] is True
    assert result["top2_types"] == [
        result["ranking"][0]["type"],
        result["ranking"][1]["type"],
    ]


def test_group_conflict_detected_when_groups_differ(voter):
    candidates = [
        {
            "type_code": "contract_a",
            "confidence": 0.81,
            "level": "L2",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
            "group": "group_a",
            "language": "ru",
            "jurisdiction": "RU",
        },
        {
            "type_code": "contract_b",
            "confidence": 0.79,
            "level": "L3",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
            "group": "group_b",
            "language": "ru",
            "jurisdiction": "RU",
        },
    ]

    result = voter.vote(candidates)

    assert result is not None
    assert result["domain_conflict"] is True
    assert result["group_conflict"] is True


def test_no_domain_conflict_when_top2_same_parent_and_group(voter):
    candidates = [
        {
            "type_code": "contract_1.6_real_estate",
            "confidence": 0.84,
            "level": "L2",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
            "parent": "class_1_transfer_of_ownership",
            "group": "group_1_ownership",
            "language": "ru",
            "jurisdiction": "RU",
        },
        {
            "type_code": "contract_1.1_general_sale",
            "confidence": 0.82,
            "level": "L3",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
            "parent": "class_1_transfer_of_ownership",
            "group": "group_1_ownership",
            "language": "ru",
            "jurisdiction": "RU",
        },
    ]

    result = voter.vote(candidates)

    assert result is not None
    assert result["domain_conflict"] is False
    assert result["parent_conflict"] is False
    assert result["group_conflict"] is False


def test_ranking_sorted_desc_by_score(voter):
    candidates = [
        {
            "type_code": "type_a",
            "confidence": 0.80,
            "level": "L2",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
            "language": "ru",
            "jurisdiction": "RU",
        },
        {
            "type_code": "type_a",
            "confidence": 0.80,
            "level": "L3",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
            "language": "ru",
            "jurisdiction": "RU",
        },
        {
            "type_code": "type_b",
            "confidence": 0.84,
            "level": "L2",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
            "language": "ru",
            "jurisdiction": "RU",
        },
    ]

    result = voter.vote(candidates)

    assert result is not None
    scores = [row["score"] for row in result["ranking"]]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.parametrize(
    "candidates,expected_type",
    [
        (
            [
                {
                    "type_code": "a",
                    "confidence": 0.95,
                    "level": "L2",
                    "signal_quality": 1.0,
                    "signal_quality_in_confidence": True,
                },
                {
                    "type_code": "b",
                    "confidence": 0.50,
                    "level": "L1",
                    "signal_quality": 1.0,
                    "signal_quality_in_confidence": True,
                },
            ],
            "a",
        ),
        (
            [
                {
                    "type_code": "a",
                    "confidence": 0.50,
                    "level": "L1",
                    "signal_quality": 1.0,
                    "signal_quality_in_confidence": True,
                },
                {
                    "type_code": "b",
                    "confidence": 0.90,
                    "level": "L3",
                    "signal_quality": 1.0,
                    "signal_quality_in_confidence": True,
                },
            ],
            "b",
        ),
    ],
)
def test_clear_level_weight_cases_have_expected_winner(voter, candidates, expected_type):
    result = voter.vote(candidates)
    assert result is not None
    assert result["type"] == expected_type


def test_result_exposes_margin_language_and_jurisdiction(voter):
    candidates = [
        {
            "type_code": "contract_1.6_real_estate",
            "confidence": 0.91,
            "level": "L2",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
            "language": "ru",
            "jurisdiction": "RU",
        },
        {
            "type_code": "contract_1.1_general_sale",
            "confidence": 0.72,
            "level": "L3",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
            "language": "ru",
            "jurisdiction": "RU",
        },
    ]

    result = voter.vote(candidates)

    assert result is not None
    assert isinstance(result["margin"], float)
    assert result["margin"] >= 0.0
    assert result["language"] == "ru"
    assert result["jurisdiction"] == "RU"


def test_support_levels_are_unique_per_type(voter):
    candidates = [
        {
            "type_code": "contract_1.6_real_estate",
            "confidence": 0.70,
            "level": "L2",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
        },
        {
            "type_code": "contract_1.6_real_estate",
            "confidence": 0.72,
            "level": "L2",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
        },
        {
            "type_code": "contract_1.6_real_estate",
            "confidence": 0.75,
            "level": "L3",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
        },
    ]

    result = voter.vote(candidates)

    assert result is not None
    ranking = _by_type(result)
    real_estate = ranking["contract_1.6_real_estate"]

    assert real_estate["support_count"] == 2
    assert set(real_estate["support_levels"]) == {"L2", "L3"}

    
import pytest

from classifiers.stage8._decision_support import apply_voting
from classifiers.stage8._l4_policy import should_run_l4
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


def test_smoke_consensus_winner_skips_l4(voter):
    candidates = [
        {
            "type_code": "contract_1.6_real_estate",
            "confidence": 0.91,
            "level": "L2",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
            "language": "ru",
            "jurisdiction": "RU",
            "parent": "class_1_transfer_of_ownership",
            "group": "group_1_ownership",
        },
        {
            "type_code": "contract_1.6_real_estate",
            "confidence": 0.87,
            "level": "L3",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
            "language": "ru",
            "jurisdiction": "RU",
            "parent": "class_1_transfer_of_ownership",
            "group": "group_1_ownership",
        },
        {
            "type_code": "contract_1.1_general_sale",
            "confidence": 0.62,
            "level": "L2",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
            "language": "ru",
            "jurisdiction": "RU",
            "parent": "class_1_transfer_of_ownership",
            "group": "group_1_ownership",
        },
    ]

    voted = voter.vote(candidates)
    assert voted is not None
    assert voted["type"] == "contract_1.6_real_estate"

    details = {}
    final_type, final_conf, language, jurisdiction, details = apply_voting(
        doc_id="doc-consensus-1",
        voted=voted,
        top_l1={"type_code": "contract_1.6_real_estate", "confidence": 0.93},
        top_l3=None,
        language=None,
        jurisdiction=None,
        details=details,
    )

    assert final_type == "contract_1.6_real_estate"
    assert final_conf == voted["confidence"]
    assert language == "ru"
    assert jurisdiction == "RU"
    assert details["voting"]["type"] == "contract_1.6_real_estate"
    assert details["domain_conflict"] is False

    gate = should_run_l4(
        l4_enabled=True,
        llm_available=True,
        hybrid_accept=0.65,
        is_segment=False,
        llm_source_text="Договор купли-продажи квартиры",
        allowed_types=["contract_1.6_real_estate", "contract_1.1_general_sale"],
        final_conf_after_voting=final_conf,
        voted_margin=voted["margin"],
        details={
            **details,
            "contradiction_detected": False,
            "input_quality": 0.92,
            "domain_conflict": False,
            "L2_top": {"confidence": 0.91},
            "L3_top": {"confidence": 0.87},
        },
    )

    assert gate.has_source_and_types is True
    assert gate.need_adjudication is False
    assert gate.skip_l4 is True
    assert gate.strong_final is True


def test_smoke_low_margin_domain_conflict_routes_to_l4(voter):
    candidates = [
        {
            "type_code": "contract_1.6_real_estate",
            "confidence": 0.86,
            "level": "L2",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
            "language": "ru",
            "jurisdiction": "RU",
            "parent": "class_1_transfer_of_ownership",
            "group": "group_1_ownership",
        },
        {
            "type_code": "contract_5.1_loan",
            "confidence": 0.84,
            "level": "L3",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
            "language": "ru",
            "jurisdiction": "RU",
            "parent": "class_5_financial_security",
            "group": "group_5_finance",
        },
    ]

    voted = voter.vote(candidates)
    assert voted is not None
    assert voted["domain_conflict"] is True

    details = {}
    final_type, final_conf, language, jurisdiction, details = apply_voting(
        doc_id="doc-conflict-1",
        voted=voted,
        top_l1=None,
        top_l3=None,
        language=None,
        jurisdiction=None,
        details=details,
    )

    assert final_type == voted["type"]
    assert final_conf == voted["confidence"]
    assert language == "ru"
    assert jurisdiction == "RU"
    assert details["domain_conflict"] is True
    assert details["top2_types"] == [
        voted["ranking"][0]["type"],
        voted["ranking"][1]["type"],
    ]

    gate = should_run_l4(
        l4_enabled=True,
        llm_available=True,
        hybrid_accept=0.65,
        is_segment=False,
        llm_source_text="Документ со смешанными признаками недвижимости и займа",
        allowed_types=["contract_1.6_real_estate", "contract_5.1_loan"],
        final_conf_after_voting=final_conf,
        voted_margin=voted["margin"],
        details={
            **details,
            "contradiction_detected": True,
            "input_quality": 0.90,
            "domain_conflict": True,
            "L2_top": {"confidence": 0.86},
            "L3_top": {"confidence": 0.84},
        },
    )

    assert gate.has_source_and_types is True
    assert gate.need_adjudication is True
    assert gate.skip_l4 is False


def test_smoke_low_confidence_routes_to_adjudication(voter):
    candidates = [
        {
            "type_code": "contract_1.5_services",
            "confidence": 0.58,
            "level": "L2",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
            "language": "ru",
            "jurisdiction": "RU",
            "parent": "class_1_commercial_services",
            "group": "group_1_services",
        },
        {
            "type_code": "contract_1.1_general_sale",
            "confidence": 0.55,
            "level": "L3",
            "signal_quality": 1.0,
            "signal_quality_in_confidence": True,
            "language": "ru",
            "jurisdiction": "RU",
            "parent": "class_1_transfer_of_ownership",
            "group": "group_1_ownership",
        },
    ]

    voted = voter.vote(candidates)
    assert voted is not None

    details = {}
    final_type, final_conf, language, jurisdiction, details = apply_voting(
        doc_id="doc-lowconf-1",
        voted=voted,
        top_l1=None,
        top_l3=None,
        language=None,
        jurisdiction=None,
        details=details,
    )

    assert final_type == voted["type"]
    assert final_conf == voted["confidence"]
    assert language == "ru"
    assert jurisdiction == "RU"

    gate = should_run_l4(
        l4_enabled=True,
        llm_available=True,
        hybrid_accept=0.65,
        is_segment=False,
        llm_source_text="Короткий некачественный фрагмент документа",
        allowed_types=["contract_1.5_services", "contract_1.1_general_sale"],
        final_conf_after_voting=final_conf,
        voted_margin=voted["margin"],
        details={
            **details,
            "contradiction_detected": False,
            "input_quality": 0.72,
            "domain_conflict": True,
            "L2_top": {"confidence": 0.58},
            "L3_top": {"confidence": 0.55},
        },
    )

    assert gate.need_adjudication is True
    assert gate.skip_l4 is False


def test_smoke_segment_strong_single_signal_can_skip_l4():
    voted = {
        "type": "contract_1.5_services",
        "voting_score": 0.69,
        "confidence": 0.69,
        "margin": 0.18,
        "language": "ru",
        "jurisdiction": "RU",
        "support_count": 1,
        "support_levels": ["L3"],
        "single_source_cap_applied": False,
        "single_source_cap_used": 0.88,
        "dominant_floor": 0.0,
        "domain_conflict": False,
        "parent_conflict": False,
        "group_conflict": False,
        "top2_types": ["contract_1.5_services", "unknown"],
        "ranking": [
            {
                "type": "contract_1.5_services",
                "score": 0.69,
                "raw_score": 0.69,
                "support_count": 1,
                "support_levels": ["L3"],
                "agreement_bonus": 0.0,
                "single_source_cap_applied": False,
                "single_source_cap_used": 0.88,
                "dominant_floor": 0.0,
            },
            {
                "type": "unknown",
                "score": 0.51,
                "raw_score": 0.51,
                "support_count": 1,
                "support_levels": ["L2"],
                "agreement_bonus": 0.0,
                "single_source_cap_applied": False,
                "single_source_cap_used": 0.88,
                "dominant_floor": 0.0,
            },
        ],
    }

    details = {}
    final_type, final_conf, language, jurisdiction, details = apply_voting(
        doc_id="doc-segment-1",
        voted=voted,
        top_l1=None,
        top_l3=None,
        language=None,
        jurisdiction=None,
        details=details,
    )

    assert final_type == "contract_1.5_services"
    assert final_conf == 0.69
    assert language == "ru"
    assert jurisdiction == "RU"

    gate = should_run_l4(
        l4_enabled=True,
        llm_available=True,
        hybrid_accept=0.65,
        is_segment=True,
        llm_source_text="fragment",
        allowed_types=["contract_1.5_services"],
        final_conf_after_voting=final_conf,
        voted_margin=voted["margin"],
        details={
            **details,
            "contradiction_detected": False,
            "input_quality": 0.89,
            "domain_conflict": False,
            "L3_top": {"confidence": 0.87},
        },
    )

    assert gate.need_adjudication is True
    assert gate.strong_single_no_conflict is True
    assert gate.skip_l4 is True



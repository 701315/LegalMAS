# tests/classifiers/stage8/test_l4_policy.py

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.classifiers.stage8 import _l4_policy as p


class DummyRegistry:
    def __init__(self):
        self._cfg = {
            "contract_1.6_real_estate": SimpleNamespace(
                parent="class_1_transfer_of_ownership",
                group="group_1_ownership",
                category="contract",
                subcategory="ownership_transfer",
                raw={"metadata": {"subcategory": "ownership_transfer"}},
            ),
            "contract_1.1_general_sale": SimpleNamespace(
                parent="class_1_transfer_of_ownership",
                group="group_1_ownership",
                category="contract",
                subcategory="ownership_transfer",
                raw={"metadata": {"subcategory": "ownership_transfer"}},
            ),
            "contract_1.5_services": SimpleNamespace(
                parent="class_3_services",
                group="group_3_services",
                category="contract",
                subcategory="services",
                raw={"metadata": {"subcategory": "services"}},
            ),
            "contract_5.1_loan": SimpleNamespace(
                parent="class_5_financial_security",
                group="group_5_financial_security",
                category="contract",
                subcategory="financial_security",
                raw={"metadata": {"subcategory": "financial_security"}},
            ),
        }

    def list_types(self):
        return list(self._cfg.keys())

    def get_config(self, type_code: str):
        return self._cfg.get(type_code)


@pytest.fixture
def registry():
    return DummyRegistry()


@pytest.fixture(autouse=True)
def patch_settings(monkeypatch):
    monkeypatch.setattr(
        p,
        "settings",
        SimpleNamespace(
            CLASSIFICATION_L2_STRONG=0.90,
            CLASSIFICATION_L3_STRONG=0.85,
            CLASSIFICATION_L4_MARGIN_MIN=0.25,
            CLASSIFICATION_L4_INPUT_QUALITY_MIN=0.60,
            CLASSIFICATION_L4_GLOBAL_FALLBACK_TYPES=[
                "contract_1.1_general_sale",
                "contract_1.5_services",
                "contract_5.1_loan",
            ],
        ),
    )


def test_build_llm_shortlist_deduplicates_by_best_confidence():
    candidates = [
        {"type_code": "contract_1.6_real_estate", "confidence": 0.81},
        {"type_code": "contract_1.6_real_estate", "confidence": 0.77},
        {"type_code": "contract_1.5_services", "confidence": 0.83},
    ]
    result = p.build_llm_shortlist(candidates, top_k=5)
    assert result == ["contract_1.5_services", "contract_1.6_real_estate"]


def test_expand_llm_types_by_family_prefers_related_family(registry):
    result = p.expand_llm_types_by_family(
        registry,
        ["contract_1.6_real_estate"],
        limit=5,
    )
    assert "contract_1.1_general_sale" in result
    assert "contract_5.1_loan" not in result


def test_build_llm_allowed_types_uses_top2_seeds_on_contradiction(registry):
    candidates = [
        {"type_code": "contract_1.6_real_estate", "confidence": 0.84},
        {"type_code": "contract_5.1_loan", "confidence": 0.79},
        {"type_code": "contract_1.5_services", "confidence": 0.50},
    ]
    allowed, source_map = p.build_llm_allowed_types(
        registry,
        candidates,
        base_top_k=3,
        max_total=8,
        details={
            "contradiction_detected": True,
            "domain_conflict": True,
        },
    )
    assert "contract_1.6_real_estate" in allowed
    assert "contract_5.1_loan" in allowed
    assert source_map["family_seed_types"] == [
        "contract_1.6_real_estate",
        "contract_5.1_loan",
    ]


def test_should_run_l4_strong_final_skips_l4():
    decision = p.should_run_l4(
        l4_enabled=True,
        llm_available=True,
        hybrid_accept=0.65,
        is_segment=False,
        llm_source_text="some text",
        allowed_types=["contract_1.6_real_estate"],
        final_conf_after_voting=0.78,
        voted_margin=0.31,
        details={
            "input_quality": 0.92,
            "contradiction_detected": False,
            "domain_conflict": False,
            "L2_top": {"confidence": 0.88},
        },
    )
    assert decision.need_adjudication is False
    assert decision.strong_final is True
    assert decision.skip_l4 is True


def test_should_run_l4_low_margin_needs_adjudication_even_if_conf_is_ok():
    decision = p.should_run_l4(
        l4_enabled=True,
        llm_available=True,
        hybrid_accept=0.65,
        is_segment=False,
        llm_source_text="some text",
        allowed_types=["contract_1.6_real_estate", "contract_1.1_general_sale"],
        final_conf_after_voting=0.72,
        voted_margin=0.10,
        details={
            "input_quality": 0.95,
            "contradiction_detected": False,
            "domain_conflict": False,
            "L2_top": {"confidence": 0.91},
        },
    )
    assert decision.need_adjudication is True
    assert decision.strong_final is False
    assert decision.skip_l4 is False


def test_should_run_l4_contradiction_blocks_strong_single_skip():
    decision = p.should_run_l4(
        l4_enabled=True,
        llm_available=True,
        hybrid_accept=0.65,
        is_segment=False,
        llm_source_text="some text",
        allowed_types=["contract_1.6_real_estate", "contract_1.5_services"],
        final_conf_after_voting=0.69,
        voted_margin=0.19,
        details={
            "input_quality": 0.90,
            "contradiction_detected": True,
            "domain_conflict": False,
            "L2_top": {"confidence": 0.93},
            "L3_top": {"confidence": 0.74},
        },
    )
    assert decision.need_adjudication is True
    assert decision.strong_single_no_conflict is False
    assert decision.skip_l4 is False


def test_should_run_l4_domain_conflict_forces_adjudication():
    decision = p.should_run_l4(
        l4_enabled=True,
        llm_available=True,
        hybrid_accept=0.65,
        is_segment=False,
        llm_source_text="some text",
        allowed_types=["contract_1.6_real_estate", "contract_5.1_loan"],
        final_conf_after_voting=0.74,
        voted_margin=0.27,
        details={
            "input_quality": 0.91,
            "contradiction_detected": False,
            "domain_conflict": True,
            "L2_top": {"confidence": 0.92},
            "L3_top": {"confidence": 0.70},
        },
    )
    assert decision.need_adjudication is True
    assert decision.strong_final is False
    assert decision.skip_l4 is False


def test_should_run_l4_segment_uses_only_l3_for_strong_single():
    decision = p.should_run_l4(
        l4_enabled=True,
        llm_available=True,
        hybrid_accept=0.65,
        is_segment=True,
        llm_source_text="segment text",
        allowed_types=["contract_1.5_services"],
        final_conf_after_voting=0.70,
        voted_margin=0.20,
        details={
            "input_quality": 0.95,
            "contradiction_detected": False,
            "domain_conflict": False,
            "L2_top": {"confidence": 0.99},
            "L3_top": {"confidence": 0.88},
        },
    )
    assert decision.strong_single_no_conflict is True
    assert decision.skip_l4 is True


def test_should_run_l4_low_input_quality_needs_adjudication():
    decision = p.should_run_l4(
        l4_enabled=True,
        llm_available=True,
        hybrid_accept=0.65,
        is_segment=False,
        llm_source_text="weak ocr text",
        allowed_types=["contract_1.1_general_sale"],
        final_conf_after_voting=0.79,
        voted_margin=0.28,
        details={
            "input_quality": 0.42,
            "contradiction_detected": False,
            "domain_conflict": False,
            "L2_top": {"confidence": 0.91},
        },
    )
    assert decision.need_adjudication is True


def test_should_run_l4_has_source_and_types_false_when_empty_inputs():
    decision = p.should_run_l4(
        l4_enabled=True,
        llm_available=True,
        hybrid_accept=0.65,
        is_segment=False,
        llm_source_text="   ",
        allowed_types=[],
        final_conf_after_voting=0.40,
        voted_margin=0.05,
        details={},
    )
    assert decision.has_source_and_types is False
    assert decision.need_adjudication is True


    
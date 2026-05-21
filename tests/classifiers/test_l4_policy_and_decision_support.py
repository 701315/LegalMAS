import types

import pytest

from classifiers.stage8 import _decision_support as ds
from classifiers.stage8 import _l4_policy as lp


class DummyRegistry:
    def __init__(self, configs: dict[str, object]):
        self._configs = configs

    def get_config(self, type_code: str):
        return self._configs.get(type_code)

    def list_types(self):
        return list(self._configs.keys())


def make_cfg(
    *,
    parent: str = "",
    group: str = "",
    category: str = "",
    subcategory: str = "",
):
    return types.SimpleNamespace(
        parent=parent,
        group=group,
        category=category,
        subcategory=subcategory,
        raw={
            "metadata": {
                "subcategory": subcategory,
            }
        },
    )


@pytest.fixture
def registry():
    return DummyRegistry(
        {
            "contract_1.1_general_sale": make_cfg(
                parent="class_1_transfer_of_ownership",
                group="group_1_ownership",
                category="contract",
                subcategory="ownership_transfer",
            ),
            "contract_1.6_real_estate": make_cfg(
                parent="class_1_transfer_of_ownership",
                group="group_1_ownership",
                category="contract",
                subcategory="ownership_transfer",
            ),
            "contract_1.5_services": make_cfg(
                parent="class_1_commercial_services",
                group="group_1_services",
                category="contract",
                subcategory="services",
            ),
            "contract_5.1_loan": make_cfg(
                parent="class_5_financial_security",
                group="group_5_finance",
                category="contract",
                subcategory="financial_security",
            ),
            "act_1.1_acceptance": make_cfg(
                parent="class_1_performance_closure",
                group="group_1_acceptance",
                category="act",
                subcategory="acceptance",
            ),
        }
    )


# ============================================================================
# _l4_policy.build_llm_shortlist
# ============================================================================


def test_build_llm_shortlist_takes_best_conf_per_type():
    candidates = [
        {"type_code": "contract_1.1_general_sale", "confidence": 0.71},
        {"type_code": "contract_1.6_real_estate", "confidence": 0.82},
        {"type_code": "contract_1.1_general_sale", "confidence": 0.91},
        {"type_code": "contract_5.1_loan", "confidence": 0.77},
        {"type_code": "", "confidence": 0.99},
        {},
        None,
    ]

    result = lp.build_llm_shortlist(candidates, top_k=3)

    assert result == [
        "contract_1.1_general_sale",
        "contract_1.6_real_estate",
        "contract_5.1_loan",
    ]


# ============================================================================
# _l4_policy.expand_llm_types_by_family / build_llm_allowed_types
# ============================================================================


def test_expand_llm_types_by_family_returns_related_types(registry):
    result = lp.expand_llm_types_by_family(
        registry,
        ["contract_1.6_real_estate"],
        limit=5,
    )

    assert "contract_1.1_general_sale" in result
    assert "contract_1.6_real_estate" not in result


def test_build_llm_allowed_types_regular_flow(registry):
    candidates = [
        {"type_code": "contract_1.6_real_estate", "confidence": 0.88},
        {"type_code": "contract_1.1_general_sale", "confidence": 0.81},
    ]
    details = {
        "contradiction_detected": False,
        "domain_conflict": False,
    }

    allowed, source_map = lp.build_llm_allowed_types(
        registry,
        candidates,
        base_top_k=2,
        max_total=5,
        details=details,
    )

    assert allowed[0] == "contract_1.6_real_estate"
    assert allowed[1] == "contract_1.1_general_sale"
    assert source_map["shortlist"] == [
        "contract_1.6_real_estate",
        "contract_1.1_general_sale",
    ]
    assert source_map["domain_conflict"] is False


def test_build_llm_allowed_types_domain_conflict_symmetric_expansion(registry):
    candidates = [
        {"type_code": "contract_1.6_real_estate", "confidence": 0.87},
        {"type_code": "contract_5.1_loan", "confidence": 0.84},
        {"type_code": "contract_1.1_general_sale", "confidence": 0.70},
    ]
    details = {
        "contradiction_detected": False,
        "domain_conflict": True,
    }

    allowed, source_map = lp.build_llm_allowed_types(
        registry,
        candidates,
        base_top_k=3,
        max_total=6,
        details=details,
    )

    assert "contract_1.6_real_estate" in allowed
    assert "contract_5.1_loan" in allowed
    assert source_map["family_seed_types"] == [
        "contract_1.6_real_estate",
        "contract_5.1_loan",
    ]
    assert source_map["domain_conflict"] is True


def test_build_llm_allowed_types_uses_global_fallback_when_needed(registry):
    allowed, source_map = lp.build_llm_allowed_types(
        registry,
        candidates=[],
        base_top_k=5,
        max_total=3,
        details={},
    )

    # Проверяем, что fallback хотя бы непустой и соответствует встроенному списку
    assert allowed
    assert source_map["shortlist"] == []
    assert source_map["family"] == []
    assert set(allowed).issubset(set(lp.global_l4_fallback_types()))


# ============================================================================
# _l4_policy.should_run_l4
# ============================================================================


@pytest.mark.parametrize(
    "name,kwargs,expected",
    [
        (
            "strong_final_no_conflict_skips_l4",
            {
                "l4_enabled": True,
                "llm_available": True,
                "hybrid_accept": 0.65,
                "is_segment": False,
                "llm_source_text": "Документ текста достаточно",
                "allowed_types": ["contract_1.6_real_estate"],
                "final_conf_after_voting": 0.78,
                "voted_margin": 0.31,
                "details": {
                    "contradiction_detected": False,
                    "domain_conflict": False,
                    "input_quality": 0.92,
                    "L2_top": {"confidence": 0.88},
                    "L3_top": {"confidence": 0.74},
                },
            },
            {
                "need_adjudication": False,
                "skip_l4": True,
                "strong_final": True,
                "strong_single_no_conflict": True,
            },
        ),
        (
            "low_margin_requires_l4",
            {
                "l4_enabled": True,
                "llm_available": True,
                "hybrid_accept": 0.65,
                "is_segment": False,
                "llm_source_text": "Документ текста достаточно",
                "allowed_types": ["contract_1.6_real_estate", "contract_1.1_general_sale"],
                "final_conf_after_voting": 0.73,
                "voted_margin": 0.09,
                "details": {
                    "contradiction_detected": False,
                    "domain_conflict": False,
                    "input_quality": 0.91,
                    "L2_top": {"confidence": 0.86},
                    "L3_top": {"confidence": 0.77},
                },
            },
            {
                "need_adjudication": True,
                "skip_l4": False,
                "strong_final": False,
            },
        ),
        (
            "domain_conflict_requires_l4",
            {
                "l4_enabled": True,
                "llm_available": True,
                "hybrid_accept": 0.65,
                "is_segment": False,
                "llm_source_text": "Есть текст",
                "allowed_types": ["contract_1.6_real_estate", "contract_5.1_loan"],
                "final_conf_after_voting": 0.81,
                "voted_margin": 0.28,
                "details": {
                    "contradiction_detected": False,
                    "domain_conflict": True,
                    "input_quality": 0.95,
                    "L2_top": {"confidence": 0.90},
                    "L3_top": {"confidence": 0.83},
                },
            },
            {
                "need_adjudication": True,
                "skip_l4": False,
                "strong_final": False,
            },
        ),
        (
            "segment_strong_l3_no_conflict_skips_l4",
            {
                "l4_enabled": True,
                "llm_available": True,
                "hybrid_accept": 0.65,
                "is_segment": True,
                "llm_source_text": "segment text",
                "allowed_types": ["contract_1.5_services"],
                "final_conf_after_voting": 0.69,
                "voted_margin": 0.18,
                "details": {
                    "contradiction_detected": False,
                    "domain_conflict": False,
                    "input_quality": 0.89,
                    "L3_top": {"confidence": 0.87},
                },
            },
            {
                "need_adjudication": True,
                "skip_l4": True,
                "strong_single_no_conflict": True,
            },
        ),
        (
            "low_input_quality_requires_l4",
            {
                "l4_enabled": True,
                "llm_available": True,
                "hybrid_accept": 0.65,
                "is_segment": False,
                "llm_source_text": "Текст есть",
                "allowed_types": ["contract_1.1_general_sale"],
                "final_conf_after_voting": 0.79,
                "voted_margin": 0.29,
                "details": {
                    "contradiction_detected": False,
                    "domain_conflict": False,
                    "input_quality": 0.41,
                    "L2_top": {"confidence": 0.89},
                    "L3_top": {"confidence": 0.82},
                },
            },
            {
                "need_adjudication": True,
                "skip_l4": True,
            },
        ),
        (
            "missing_text_prevents_source_and_types",
            {
                "l4_enabled": True,
                "llm_available": True,
                "hybrid_accept": 0.65,
                "is_segment": False,
                "llm_source_text": "   ",
                "allowed_types": ["contract_1.1_general_sale"],
                "final_conf_after_voting": 0.40,
                "voted_margin": 0.05,
                "details": {
                    "contradiction_detected": True,
                    "domain_conflict": False,
                    "input_quality": 0.70,
                    "L2_top": {"confidence": 0.55},
                    "L3_top": {"confidence": 0.58},
                },
            },
            {
                "has_source_and_types": False,
                "need_adjudication": True,
            },
        ),
    ],
)
def test_should_run_l4_table(monkeypatch, name, kwargs, expected):
    decision = lp.should_run_l4(**kwargs)

    for key, value in expected.items():
        assert getattr(decision, key) == value, f"{name}: expected {key}={value}, got {getattr(decision, key)}"


# ============================================================================
# _decision_support.build_voting_details
# ============================================================================


def test_build_voting_details_includes_new_top_level_fields():
    voted = {
        "type": "contract_1.6_real_estate",
        "voting_score": 0.79,
        "confidence": 0.84,
        "margin": 0.22,
        "support_count": 2,
        "support_levels": ["L2", "L3"],
        "single_source_cap_applied": False,
        "single_source_cap_used": 0.88,
        "dominant_floor": 0.748,
        "domain_conflict": True,
        "parent_conflict": True,
        "group_conflict": True,
        "top2_types": ["contract_1.6_real_estate", "contract_5.1_loan"],
        "ranking": [{"type": "contract_1.6_real_estate", "score": 0.79}],
    }

    payload = ds.build_voting_details(
        strategy="WEIGHTED_VOTING",
        reason="test",
        voted=voted,
    )

    assert payload["type"] == "contract_1.6_real_estate"
    assert payload["score"] == 0.79
    assert payload["single_source_cap_used"] == 0.88
    assert payload["dominant_floor"] == 0.748
    assert payload["domain_conflict"] is True
    assert payload["parent_conflict"] is True
    assert payload["group_conflict"] is True
    assert payload["top2_types"] == ["contract_1.6_real_estate", "contract_5.1_loan"]


# ============================================================================
# _decision_support.apply_voting
# ============================================================================


def test_apply_voting_preserves_and_promotes_conflict_fields(monkeypatch):
    monkeypatch.setattr(ds.settings, "CLASSIFICATION_TRACE_INCLUDE_RANKING", True, raising=False)

    voted = {
        "type": "contract_1.6_real_estate",
        "voting_score": 0.78,
        "confidence": 0.83,
        "margin": 0.12,
        "language": "ru",
        "jurisdiction": "RU",
        "support_count": 2,
        "support_levels": ["L2", "L3"],
        "single_source_cap_applied": False,
        "single_source_cap_used": 0.88,
        "dominant_floor": 0.74,
        "domain_conflict": True,
        "parent_conflict": True,
        "group_conflict": True,
        "top2_types": ["contract_1.6_real_estate", "contract_5.1_loan"],
        "ranking": [
            {"type": "contract_1.6_real_estate", "score": 0.78},
            {"type": "contract_5.1_loan", "score": 0.66},
        ],
    }

    details = {
        "voting": {
            "strategy": "PRESET",
            "reason": "preset value",
            "extra_marker": "keep_me",
        }
    }

    final_type, final_conf, language, jurisdiction, details = ds.apply_voting(
        doc_id="doc-1",
        voted=voted,
        top_l1={"type_code": "contract_1.6_real_estate", "confidence": 0.91},
        top_l3=None,
        language=None,
        jurisdiction=None,
        details=details,
    )

    assert final_type == "contract_1.6_real_estate"
    assert final_conf == 0.83
    assert language == "ru"
    assert jurisdiction == "RU"

    assert details["domain_conflict"] is True
    assert details["parent_conflict"] is True
    assert details["group_conflict"] is True
    assert details["top2_types"] == ["contract_1.6_real_estate", "contract_5.1_loan"]

    assert details["voting"]["domain_conflict"] is True
    assert details["voting"]["single_source_cap_used"] == 0.88
    assert details["voting"]["dominant_floor"] == 0.74
    assert details["voting_margin"] == 0.12
    assert details["voting_ranking"] == voted["ranking"][:3]

    assert details["l1_support"]["applied_as"] == "explainability_only"


def test_apply_voting_handles_none_voted(monkeypatch):
    monkeypatch.setattr(ds.settings, "CLASSIFICATION_TRACE_INCLUDE_RANKING", True, raising=False)

    details = {
        "voting": {
            "strategy": "OLD",
            "reason": "existing",
        }
    }

    final_type, final_conf, language, jurisdiction, details = ds.apply_voting(
        doc_id="doc-2",
        voted=None,
        top_l1=None,
        top_l3=None,
        language="ru",
        jurisdiction="RU",
        details=details,
    )

    assert final_type == "UNKNOWN"
    assert final_conf == 0.0
    assert language == "ru"
    assert jurisdiction == "RU"
    assert details["voting"]["strategy"] == "NO_VOTED_RESULT"
    assert details["voting_raw"] is None
    assert details["voting_margin"] == 0.0


# ============================================================================
# _decision_support.best_pre_l4_signal
# ============================================================================


def test_best_pre_l4_signal_prefers_voted():
    voted = {
        "type": "contract_1.6_real_estate",
        "confidence": 0.81,
        "language": "ru",
        "jurisdiction": "RU",
    }

    result = ds.best_pre_l4_signal(
        voted=voted,
        top_l1={"type_code": "contract_1.1_general_sale", "confidence": 0.91},
        top_l2=types.SimpleNamespace(doctype="contract_1.5_services", confidence=0.88),
        top_l3=types.SimpleNamespace(
            doctype="contract_5.1_loan",
            confidence=0.77,
            language="ru",
            jurisdiction="RU",
        ),
        language=None,
        jurisdiction=None,
    )

    assert result == ("contract_1.6_real_estate", 0.81, "ru", "RU", "VOTED")


    
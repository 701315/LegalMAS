"""
Tests for semantic enrichment flags in result_normalizer.
"""
from engine.checks.result_normalizer import normalize_check_result


def _base_exec_result(**raw_overrides) -> dict:
    """Build a minimal valid exec_result with optional raw overrides."""
    raw = {
        "source": "rules_confident_positive",
        **raw_overrides,
    }
    return {
        "check_id": "test_001",
        "check_name": "Test Check",
        "result": "pass",
        "severity": "medium",
        "evidence": "Some meaningful evidence text that is long enough",
        "confidence": 0.8,
        "detector_method": "hybrid",
        "reason": "rules_confident_positive",
        "sources": [],
        "location": None,
        "raw": raw,
        "structured_data": None,
        "page": None,
        "clause_uid": None,
        "element_id": None,
        "bbox": None,
        "llm_error_type": None,
        "llm_required": False,
        "llm_degraded": False,
        "rules_llm_decision": "rules_confident_positive",
        "llm_attempts": None,
        "llm_error_message": None,
    }


def test_no_semantic_flags_when_not_present():
    """When executor didn't pass semantic signals, quality_flags has no enrichment keys."""
    result = normalize_check_result(_base_exec_result(), check=None)
    qf = result.get("quality_flags") or {}
    assert "enrichment_used" not in qf
    assert "enrichment_clause_functions" not in qf
    assert "enrichment_clause_match" not in qf


def test_enrichment_used_false_recorded():
    result = normalize_check_result(
        _base_exec_result(semantic_enrichment_used=False),
        check=None,
    )
    qf = result.get("quality_flags") or {}
    assert qf.get("enrichment_used") is False


def test_enrichment_flags_full_match():
    result = normalize_check_result(
        _base_exec_result(
            semantic_enrichment_used=True,
            semantic_segment_type="contract",
            semantic_clause_functions=["confidentiality", "assignment"],
        ),
        check=None,
    )
    qf = result.get("quality_flags") or {}

    assert qf.get("enrichment_used") is True
    assert qf.get("enrichment_segment_type") == "contract"
    assert "confidentiality" in qf.get("enrichment_clause_functions", [])
    assert "assignment" in qf.get("enrichment_clause_functions", [])
    assert qf.get("enrichment_clause_match") is True


def test_enrichment_segment_type_without_clause_functions():
    result = normalize_check_result(
        _base_exec_result(
            semantic_enrichment_used=True,
            semantic_segment_type="appendix",
            semantic_clause_functions=[],
        ),
        check=None,
    )
    qf = result.get("quality_flags") or {}

    assert qf.get("enrichment_used") is True
    assert qf.get("enrichment_segment_type") == "appendix"
    # No clause match when list is empty
    assert "enrichment_clause_match" not in qf


def test_legacy_ui_keys_not_in_quality_flags():
    """Legacy keys must not leak into quality_flags regardless of semantic flags."""
    result = normalize_check_result(
        _base_exec_result(
            semantic_enrichment_used=True,
            user_status="some_legacy_value",
            user_message="some message",
        ),
        check=None,
    )
    qf = result.get("quality_flags") or {}
    assert "user_status" not in qf
    assert "user_message" not in qf



    
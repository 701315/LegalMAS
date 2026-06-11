"""
Tests for EnrichmentHints model and its integration into CheckDefinition.
"""
import pytest
from pydantic import ValidationError

from engine.playbook.models import CheckDefinition, EnrichmentHints


def test_enrichment_hints_all_defaults():
    hints = EnrichmentHints()
    assert hints.preferred_segment_types == []
    assert hints.excluded_segment_types == []
    assert hints.preferred_clause_functions == []
    assert hints.confidence_bonus_on_match == 0.0
    assert hints.confidence_penalty_on_excluded_segment == 0.0


def test_enrichment_hints_full_config():
    hints = EnrichmentHints(
        preferred_segment_types=["contract", "amendment"],
        excluded_segment_types=["technical_specification", "price_list"],
        preferred_clause_functions=["confidentiality", "data_protection"],
        confidence_bonus_on_match=0.10,
        confidence_penalty_on_excluded_segment=0.15,
    )
    assert "contract" in hints.preferred_segment_types
    assert "technical_specification" in hints.excluded_segment_types
    assert "confidentiality" in hints.preferred_clause_functions
    assert hints.confidence_bonus_on_match == 0.10
    assert hints.confidence_penalty_on_excluded_segment == 0.15


def test_enrichment_hints_bonus_upper_bound():
    with pytest.raises(ValidationError):
        EnrichmentHints(confidence_bonus_on_match=1.5)


def test_enrichment_hints_bonus_lower_bound():
    with pytest.raises(ValidationError):
        EnrichmentHints(confidence_bonus_on_match=-0.1)


def test_enrichment_hints_penalty_upper_bound():
    with pytest.raises(ValidationError):
        EnrichmentHints(confidence_penalty_on_excluded_segment=1.1)


def test_check_definition_no_hints_by_default():
    check = CheckDefinition(id="c1", name="Test Check")
    assert check.enrichment_hints is None


def test_check_definition_with_hints():
    hints = EnrichmentHints(
        preferred_clause_functions=["confidentiality"],
        confidence_bonus_on_match=0.10,
    )
    check = CheckDefinition(id="c1", name="Test Check", enrichment_hints=hints)
    assert check.enrichment_hints is not None
    assert "confidentiality" in check.enrichment_hints.preferred_clause_functions
    assert check.enrichment_hints.confidence_bonus_on_match == 0.10


def test_old_check_without_hints_loads_fine():
    """Backward compatibility: existing checks without enrichment_hints work."""
    raw = {
        "id": "legacy_001",
        "name": "Legacy Check",
        "severity": "medium",
        "detector_type": "rules",
        "rules": {"keywords": ["term1"]},
    }
    check = CheckDefinition(**raw)
    assert check.enrichment_hints is None
    assert check.id == "legacy_001"


def test_hints_zero_bonus_is_valid():
    hints = EnrichmentHints(confidence_bonus_on_match=0.0)
    assert hints.confidence_bonus_on_match == 0.0


def test_hints_max_bonus_is_valid():
    hints = EnrichmentHints(confidence_bonus_on_match=1.0)
    assert hints.confidence_bonus_on_match == 1.0


    
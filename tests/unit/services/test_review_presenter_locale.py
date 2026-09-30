# tests/unit/services/test_review_presenter_locale.py

"""
Unit tests for review presenter localization awareness (Sprint 5.2).

Verifies that build_dd_requests, build_conditional_checks, and build_extracted_values
respect localized check_name from check_results after presentation overlay.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from engine.playbook.models import CheckDefinition, ExtractionConfig, ExtractionFieldConfig
from services.review_presenter import (
    build_conditional_checks,
    build_dd_requests,
    build_extracted_values,
)


def _make_check_def(check_id: str = "chk_1", check_name: str = "Canonical Name") -> CheckDefinition:
    field = ExtractionFieldConfig(
        name="target_field",
        description="test field",
        type="string",
        required=True,
        label="Target Field Label",  # Required by Pydantic validator
    )
    extraction = ExtractionConfig(enabled=True, fields=[field])
    return CheckDefinition(
        id=check_id,
        name=check_name,
        severity="high",
        extraction=extraction,
    )


def test_build_dd_requests_uses_localized_check_name() -> None:
    """build_dd_requests should use check_name from check_results (localized overlay)."""
    check_id = "chk_1"
    check_def = _make_check_def(check_id=check_id, check_name="Canonical Check Name")
    
    # check_result with localized check_name overlay.
    # Trigger is rule-based (v3 semantics): review_status must be one of
    # DD_REQUEST_DEFAULT_REVIEW_STATUSES =
    # {clause_missing, clause_partially_defined, unclear}.
    check_results = [
        {
            "check_id": check_id,
            "check_name": "Localized Check Name (RU)",
            "document_id": "doc_1",
            "review_status": "clause_missing",  # triggers DD request
            "structured_data": {},
            "segment_id": None,
            "segment_type": None,
            "segment_title": None,
            "segment_order": 0,
            "is_primary_segment": True,
            "chunk_id": None,
            "chunk_index": None,
        }
    ]
    documents = {"doc_1": {"name": "contract.pdf", "doc_type": "contract"}}
    checks_by_id = {check_id: check_def}

    requests = build_dd_requests(check_results, documents, checks_by_id)

    assert len(requests) == 1
    assert requests[0].check_id == check_id
    assert requests[0].check_name == "Localized Check Name (RU)"


def test_build_conditional_checks_uses_localized_check_name() -> None:
    """build_conditional_checks should propagate localized check_name from check_results."""
    check_results = [
        {
            "check_id": "cond_1",
            "check_name": "Localized Conditional Name",
            "document_id": "doc_1",
            "conditional_check_triggered": True,
            "trigger_name": "trigger_annex",
            "result": "fail",
            "severity": "high",
            "display_text": "Evidence snippet",
        }
    ]
    documents = {"doc_1": {"name": "annex.pdf", "doc_type": "annex"}}

    checks = build_conditional_checks(check_results, documents)

    assert len(checks) == 1
    assert checks[0].check_name == "Localized Conditional Name"
    assert checks[0].trigger_name == "trigger_annex"


def test_build_extracted_values_uses_localized_check_name() -> None:
    """build_extracted_values should propagate localized check_name from check_results."""
    check_results = [
        {
            "check_id": "ext_1",
            "check_name": "Localized Extracted Name",
            "document_id": "doc_1",
            "structured_data": {"amount": "1000000"},
        }
    ]
    documents = {"doc_1": {"name": "contract.pdf", "doc_type": "contract"}}

    values = build_extracted_values(check_results, documents)

    assert len(values) == 1
    assert values[0].check_name == "Localized Extracted Name"
    assert values[0].field_name == "amount"
    assert values[0].field_value == "1000000"

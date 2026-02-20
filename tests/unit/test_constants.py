"""Tests for enumerations and constants."""

import json

from src.core.constants import (
    BundleSourceType,
    CheckResultStatus,
    DealStatus,
    DetectorType,
    DocumentStatus,
    ExportType,
    JobStatus,
    PIIMode,
    PlaybookStatus,
    QCStatus,
    RelationType,
    Severity,
)


def test_all_enums_are_string_serializable():
    """Every Enum must serialize to a string for JSON and PostgreSQL."""
    all_enums = [
        DocumentStatus,
        Severity,
        CheckResultStatus,
        PlaybookStatus,
        RelationType,
        JobStatus,
        BundleSourceType,
        PIIMode,
        ExportType,
        DealStatus,
        QCStatus,
        DetectorType,
    ]

    for enum_class in all_enums:
        for member in enum_class:
            # Must be a string
            assert isinstance(member.value, str), (
                f"{enum_class.__name__}.{member.name} value is not a string: "
                f"{member.value!r}"
            )

            # Must be JSON-serializable
            json_str = json.dumps({"status": member.value})
            assert member.value in json_str

            # str() must return the value
            assert str(member) == f"{enum_class.__name__}.{member.name}"

            # .value must be lowercase
            assert member.value == member.value.lower(), (
                f"{enum_class.__name__}.{member.name} value must be lowercase: "
                f"{member.value!r}"
            )


def test_severity_has_all_required_levels():
    """Severity must have exactly the levels from the specification."""
    expected = {"critical", "high", "medium", "pass", "unclear"}
    actual = {s.value for s in Severity}
    assert actual == expected


def test_document_status_has_pipeline_stages():
    """DocumentStatus must include all pipeline processing stages."""
    required = {"pending", "extracting", "extracted", "sanitized",
                "structured", "classified", "analyzing", "completed", "quarantine"}
    actual = {s.value for s in DocumentStatus}
    assert required.issubset(actual)


def test_relation_type_has_mvp_types():
    """RelationType must include all MVP relation types from spec."""
    required = {"master", "appendix", "amendment", "disclosure",
                "version", "draft", "counterpart"}
    actual = {r.value for r in RelationType}
    assert required.issubset(actual)

"""
Focused tests for initial heading detection with record recovery.
"""

from __future__ import annotations

from services.structure._pipeline import _core_builder
from services.structure._pipeline._record_heading_recovery import (
    RecordHeadingRecoveryResult,
)


def _el(text: str, *, recovered: bool = False) -> dict:
    metadata = {}
    if recovered:
        metadata["record_heading_recovery"] = True
    return {
        "text": text,
        "page": 1,
        "element_type": "body_text",
        "scope": "appendix_1",
        "segment_id": "seg-1",
        "segment_type": "appendix",
        "segment_order": 1,
        "metadata": metadata,
    }


def test_initial_heading_detection_uses_record_recovery(monkeypatch) -> None:
    elements = [_el("17 Name"), _el("17.1 Value"), _el("18 Name"), _el("18.1 Value")]

    def fake_build_heading_candidates(input_elements, *, document_id, toc_match_index=None):
        recovered = any(
            bool((el.get("metadata") or {}).get("record_heading_recovery"))
            for el in input_elements
        )
        return ["heading-1"] if recovered else []

    def fake_attempt_record_heading_recovery(*, document_id, elements):
        recovered_elements = [_el(el["text"], recovered=True) for el in elements]
        return RecordHeadingRecoveryResult(
            applied=True,
            elements=recovered_elements,
            diagnostics={
                "attempted": True,
                "applied": True,
                "mode": "numbered_record",
                "reason": "numbered_record_topology_detected",
            },
        )

    monkeypatch.setattr(_core_builder, "build_heading_candidates", fake_build_heading_candidates)
    monkeypatch.setattr(
        _core_builder,
        "attempt_record_heading_recovery",
        fake_attempt_record_heading_recovery,
    )

    headings, effective_elements, diag = _core_builder._build_initial_headings_with_record_recovery(
        document_id="doc-1",
        elements=elements,
    )

    assert headings == ["heading-1"]
    assert any(
        bool((el.get("metadata") or {}).get("record_heading_recovery"))
        for el in effective_elements
    )
    assert diag["applied"] is True
    assert diag["headings_pre_count_after_recovery"] == 1


def test_initial_heading_detection_returns_empty_when_recovery_not_applied(monkeypatch) -> None:
    elements = [_el("plain text"), _el("more text")]

    def fake_build_heading_candidates(input_elements, *, document_id, toc_match_index=None):
        return []

    def fake_attempt_record_heading_recovery(*, document_id, elements):
        return RecordHeadingRecoveryResult(
            applied=False,
            elements=elements,
            diagnostics={
                "attempted": True,
                "applied": False,
                "mode": "numbered_record",
                "reason": "insufficient_numeric_record_lines",
            },
        )

    monkeypatch.setattr(_core_builder, "build_heading_candidates", fake_build_heading_candidates)
    monkeypatch.setattr(
        _core_builder,
        "attempt_record_heading_recovery",
        fake_attempt_record_heading_recovery,
    )

    headings, effective_elements, diag = _core_builder._build_initial_headings_with_record_recovery(
        document_id="doc-2",
        elements=elements,
    )

    assert headings == []
    assert effective_elements == elements
    assert diag["applied"] is False
    assert diag["headings_pre_count_after_recovery"] == 0

"""
B3.1c — ExtractionExecutor builds CheckAnchor list from per-field location.quote.

Covers:
- anchors empty when no field carries quote
- anchor collected from LLM-branch quote (exact span vs base_text)
- anchor collected from rules-branch quote
- anchor skipped when location is None
- ExtractionExecutionResult.anchors defaults to empty list
- run() wrapper unchanged (returns dict, no anchors surface)
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.anchors.models import CheckAnchorMethod
from engine.checks.extraction import ExtractionExecutor, ExtractionExecutionResult
from engine.playbook.models import (
    CheckDefinition,
    DetectorType,
    ExtractionConfig,
    ExtractionFieldConfig,
    ExtractionFieldType,
)


# ── fixtures (mirror test_extraction_executor_location_v1) ──────────────────


def _make_check() -> CheckDefinition:
    return CheckDefinition(
        id="governing_law_and_forum",
        name="Применимое право и юрисдикция",
        ui_mode="field_extraction",
        detector_type=DetectorType.LLM,
        extraction=ExtractionConfig(
            enabled=True,
            mode="llm",
            fields=[
                ExtractionFieldConfig(
                    name="governing_law_value",
                    type=ExtractionFieldType.STRING,
                    label="Применимое право",
                ),
            ],
        ),
    )


def _make_doc() -> SimpleNamespace:
    return SimpleNamespace(id="doc-1")


def _make_contexts() -> list[dict]:
    return [
        {
            "id": "chunk-1",
            "text": "Согласно п. 12.1 настоящий договор регулируется правом РФ.",
            "metadata": {
                "page": 7,
                "start_page": 7,
                "end_page": 7,
                "effective_uid": "main_contract:12.1",
                "element_ids": ["el-1"],
            },
        }
    ]


def _make_detection() -> dict:
    return {
        "evidence": "Согласно п. 12.1 настоящий договор регулируется правом РФ.",
        "location": {
            "page": 7,
            "clause_uid": "main_contract:12.1",
            "element_id": "el-1",
            "start_page": 7,
            "end_page": 7,
        },
    }


def _make_llm_client() -> MagicMock:
    client = MagicMock()
    client.is_available.return_value = True
    return client


def _llm_response(fields: dict) -> SimpleNamespace:
    return SimpleNamespace(fields=fields, telemetry=None)


# ── 1. dataclass default ────────────────────────────────────────────────────


def test_extraction_execution_result_anchors_default_empty():
    result = ExtractionExecutionResult(structured_data=None)
    assert result.anchors == []


# ── 2. LLM branch ───────────────────────────────────────────────────────────


def test_anchor_collected_from_llm_quote():
    executor = ExtractionExecutor(_make_llm_client())
    executor.llm_detector.extract_with_telemetry = MagicMock(
        return_value=_llm_response(
            {
                "governing_law_value": {
                    "value": "РФ",
                    "confidence": 0.9,
                    "location": {
                        "clause_ref": "п. 12.1",
                        "page": 7,
                        "quote": "Согласно п. 12.1 настоящий договор регулируется правом РФ.",
                    },
                }
            }
        )
    )

    with patch.object(executor, "_extract_field", return_value=None):
        result = executor.run_with_telemetry(
            doc=_make_doc(),
            check=_make_check(),
            contexts=_make_contexts(),
            detection=_make_detection(),
        )

    assert result.structured_data is not None
    assert len(result.anchors) == 1
    anchor = result.anchors[0]
    assert anchor.anchor_method == CheckAnchorMethod.EXACT_SPAN
    assert (
        anchor.quoted_text
        == "Согласно п. 12.1 настоящий договор регулируется правом РФ."
    )


def test_no_anchor_when_llm_location_has_no_quote():
    executor = ExtractionExecutor(_make_llm_client())
    executor.llm_detector.extract_with_telemetry = MagicMock(
        return_value=_llm_response(
            {
                "governing_law_value": {
                    "value": "РФ",
                    "confidence": 0.9,
                    "location": {"clause_ref": "п. 12.1", "page": 7},
                }
            }
        )
    )

    with patch.object(executor, "_extract_field", return_value=None):
        result = executor.run_with_telemetry(
            doc=_make_doc(),
            check=_make_check(),
            contexts=_make_contexts(),
            detection=_make_detection(),
        )

    assert result.structured_data is not None
    assert result.anchors == []


def test_no_anchor_when_llm_location_is_none():
    executor = ExtractionExecutor(_make_llm_client())
    executor.llm_detector.extract_with_telemetry = MagicMock(
        return_value=_llm_response(
            {
                "governing_law_value": {
                    "value": "РФ",
                    "confidence": 0.9,
                    "location": None,
                }
            }
        )
    )

    with patch.object(executor, "_extract_field", return_value=None):
        result = executor.run_with_telemetry(
            doc=_make_doc(),
            check=_make_check(),
            contexts=_make_contexts(),
            detection=_make_detection(),
        )

    assert result.structured_data is not None
    assert result.anchors == []


# ── 3. rules branch ─────────────────────────────────────────────────────────


def test_anchor_collected_from_rules_branch_quote():
    executor = ExtractionExecutor(_make_llm_client())
    # LLM unavailable → only rules branch runs.
    executor.llm_client.is_available.return_value = False

    with patch.object(
        executor,
        "_extract_field",
        return_value={
            "value": "РФ",
            "unit": None,
            "source": "rules",
            "confidence": 0.8,
            "found": True,
            "location": {
                "clause_ref": "п. 12.1",
                "page": 7,
                "quote": "Согласно п. 12.1 настоящий договор регулируется правом РФ.",
            },
        },
    ):
        result = executor.run_with_telemetry(
            doc=_make_doc(),
            check=_make_check(),
            contexts=_make_contexts(),
            detection=_make_detection(),
        )

    assert result.structured_data is not None
    assert len(result.anchors) == 1
    assert result.anchors[0].anchor_method == CheckAnchorMethod.EXACT_SPAN


# ── 4. run() wrapper backward compat ────────────────────────────────────────


def test_run_wrapper_returns_structured_data_only():
    executor = ExtractionExecutor(_make_llm_client())
    executor.llm_detector.extract_with_telemetry = MagicMock(
        return_value=_llm_response(
            {
                "governing_law_value": {
                    "value": "РФ",
                    "confidence": 0.9,
                    "location": {
                        "clause_ref": "п. 12.1",
                        "page": 7,
                        "quote": "Согласно п. 12.1 настоящий договор регулируется правом РФ.",
                    },
                }
            }
        )
    )

    with patch.object(executor, "_extract_field", return_value=None):
        out = executor.run(
            doc=_make_doc(),
            check=_make_check(),
            contexts=_make_contexts(),
            detection=_make_detection(),
        )

    # run() returns structured_data dict (not the dataclass).
    assert isinstance(out, dict)
    assert "governing_law_value" in out
    assert "anchors" not in out

    
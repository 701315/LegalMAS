"""
Tests for ExtractionExecutor field-level location fallback semantics (V1.3).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from engine.checks.extraction import ExtractionExecutor
from engine.detectors.extraction_llm_detector import ExtractionLLMExtractionResult
from engine.playbook.models import (
    CheckDefinition,
    DetectorType,
    ExtractionConfig,
    ExtractionFieldConfig,
    ExtractionFieldType,
)


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


class TestExtractionExecutorLocationFallback:
    def test_run_adds_location_fallback_when_llm_has_no_exact_location(self) -> None:
        llm_client = MagicMock()
        llm_client.is_available.return_value = True

        executor = ExtractionExecutor(llm_client)
        executor.llm_detector.extract_with_telemetry = MagicMock(
            return_value=ExtractionLLMExtractionResult(
                fields={
                "governing_law_value": {
                    "value": "РФ",
                    "confidence": 0.9,
                    "location": None,
                    "location_fallback": {
                        "reason": "LLM не указал точную ссылку для поля",
                    },
                }
            },
                telemetry={"llm_invoked": True},
            )
        )

        with patch.object(executor, "_extract_field", return_value=None):
            result = executor.run(
                doc=_make_doc(),
                check=_make_check(),
                contexts=_make_contexts(),
                detection=_make_detection(),
            )

        assert result is not None
        payload = result["governing_law_value"]
        assert payload["location"] is None
        assert payload["location_fallback"]["check_page"] == 7
        assert payload["location_fallback"]["check_clause_uid"] == "main_contract:12.1"

        call_kwargs = executor.llm_detector.extract_with_telemetry.call_args.kwargs
        assert call_kwargs["context_pages"] == [7]

    def test_run_preserves_exact_location_when_llm_provided_it(self) -> None:
        llm_client = MagicMock()
        llm_client.is_available.return_value = True

        executor = ExtractionExecutor(llm_client)
        executor.llm_detector.extract_with_telemetry = MagicMock(
            return_value=ExtractionLLMExtractionResult(
                fields={
                "governing_law_value": {
                    "value": "РФ",
                    "confidence": 0.9,
                    "location": {
                        "clause_ref": "п. 12.1",
                        "page": 7,
                        "location_confidence": "high",
                    },
                }
            },
                telemetry={"llm_invoked": True},
            )
        )

        with patch.object(executor, "_extract_field", return_value=None):
            result = executor.run(
                doc=_make_doc(),
                check=_make_check(),
                contexts=_make_contexts(),
                detection=_make_detection(),
            )

        assert result is not None
        payload = result["governing_law_value"]
        assert payload["location"]["clause_ref"] == "п. 12.1"
        assert payload["location"]["page"] == 7
        assert "location_fallback" not in payload or payload["location_fallback"] is None


    def test_run_drops_page_when_base_location_is_scoped_preamble(self) -> None:
        """B7.9.1: scoped structural-marker base_location must not leak into fallback."""
        llm_client = MagicMock()
        llm_client.is_available.return_value = True

        executor = ExtractionExecutor(llm_client)
        executor.llm_detector.extract_with_telemetry = MagicMock(
            return_value=ExtractionLLMExtractionResult(
                fields={
                "governing_law_value": {
                    "value": "РФ",
                    "confidence": 0.9,
                    "location": None,
                    "location_fallback": {
                        "reason": "Exact location in the document is not defined",
                    },
                }
            },
                telemetry={"llm_invoked": True},
            )
        )

        detection = _make_detection()
        detection["location"]["clause_uid"] = "main_contract:__preamble__"

        with patch.object(executor, "_extract_field", return_value=None):
            result = executor.run(
                doc=_make_doc(),
                check=_make_check(),
                contexts=_make_contexts(),
                detection=detection,
            )

        assert result is not None
        payload = result["governing_law_value"]
        assert payload["location"] is None
        assert payload["location_fallback"] == {
            "reason": "Exact location in the document is not defined"
        }
        assert "check_page" not in payload["location_fallback"]
        assert "check_clause_uid" not in payload["location_fallback"]

    def test_run_drops_page_when_base_location_is_bare_preamble(self) -> None:
        """B7.9.1: bare __preamble__ base_location must also drop page/uid."""
        llm_client = MagicMock()
        llm_client.is_available.return_value = True

        executor = ExtractionExecutor(llm_client)
        executor.llm_detector.extract_with_telemetry = MagicMock(
            return_value=ExtractionLLMExtractionResult(
                fields={
                "governing_law_value": {
                    "value": "РФ",
                    "confidence": 0.9,
                    "location": None,
                    "location_fallback": {
                        "reason": "Exact location in the document is not defined",
                    },
                }
            },
                telemetry={"llm_invoked": True},
            )
        )

        detection = _make_detection()
        detection["location"]["clause_uid"] = "__preamble__"

        with patch.object(executor, "_extract_field", return_value=None):
            result = executor.run(
                doc=_make_doc(),
                check=_make_check(),
                contexts=_make_contexts(),
                detection=detection,
            )

        assert result is not None
        payload = result["governing_law_value"]
        assert payload["location"] is None
        assert payload["location_fallback"] == {
            "reason": "Exact location in the document is not defined"
        }
        assert "check_page" not in payload["location_fallback"]
        assert "check_clause_uid" not in payload["location_fallback"]


class TestStructuralMarkerUid:
    """Unit tests for _is_structural_marker_uid helper (B7.9.1)."""

    @pytest.mark.parametrize(
        "value, expected",
        [
            ("__preamble__", True),
            ("main_contract:__preamble__", True),
            ("appendix_1:__header__", True),
            ("some_scope_2:__metadata__", True),
            ("  __preamble__  ", True),
            ("main_contract:12.1", False),
            ("main_contract:S", False),
            ("п. 5.1", False),
            (None, False),
            ("", False),
            ("__PREAMBLE__", False),
        ],
    )
    def test_is_structural_marker_uid(self, value, expected) -> None:
        from engine.checks.extraction import _is_structural_marker_uid

        assert _is_structural_marker_uid(value) is expected

"""
Tests for ExtractionExecutor field-level location fallback semantics (V1.3).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from engine.checks.extraction import ExtractionExecutor
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
        executor.llm_detector.extract = MagicMock(
            return_value={
                "governing_law_value": {
                    "value": "РФ",
                    "confidence": 0.9,
                    "location": None,
                    "location_fallback": {
                        "reason": "LLM не указал точную ссылку для поля",
                    },
                }
            }
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

        call_kwargs = executor.llm_detector.extract.call_args.kwargs
        assert call_kwargs["context_pages"] == [7]

    def test_run_preserves_exact_location_when_llm_provided_it(self) -> None:
        llm_client = MagicMock()
        llm_client.is_available.return_value = True

        executor = ExtractionExecutor(llm_client)
        executor.llm_detector.extract = MagicMock(
            return_value={
                "governing_law_value": {
                    "value": "РФ",
                    "confidence": 0.9,
                    "location": {
                        "clause_ref": "п. 12.1",
                        "page": 7,
                        "location_confidence": "high",
                    },
                }
            }
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


        
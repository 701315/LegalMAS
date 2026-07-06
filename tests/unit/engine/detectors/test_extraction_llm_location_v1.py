"""
Tests for ExtractionLLMDetector per-field location support (V1.3).

Covers:
- _parse_response reads location payloads
- _build_example_json includes location contract
- AllowedValueSpec works in normalization
- EVIDENCE_LIST is preserved as-is
- extract() validates location against context text/pages
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from engine.detectors.extraction_llm_detector import ExtractionLLMDetector
from engine.playbook.models import (
    AllowedValueSpec,
    CheckDefinition,
    DetectorType,
    ExtractionConfig,
    ExtractionFieldConfig,
    ExtractionFieldType,
)


def _make_detector() -> tuple[ExtractionLLMDetector, MagicMock]:
    client = MagicMock()
    client.is_available.return_value = True
    detector = ExtractionLLMDetector(client=client)
    return detector, client


def _make_check(fields: list[ExtractionFieldConfig]) -> CheckDefinition:
    return CheckDefinition(
        id="location_test_check",
        name="Location Test Check",
        ui_mode="field_extraction",
        detector_type=DetectorType.LLM,
        extraction=ExtractionConfig(
            enabled=True,
            mode="llm",
            fields=fields,
        ),
    )


class TestParseResponseLocation:
    def test_parse_response_reads_location_when_present(self) -> None:
        detector, _ = _make_detector()
        raw = json.dumps(
            {
                "fields": {
                    "governing_law_value": {
                        "value": "РФ",
                        "confidence": 0.91,
                        "location": {
                            "clause_ref": "п. 12.1",
                            "page": 7,
                        },
                    }
                }
            },
            ensure_ascii=False,
        )

        result = detector._parse_response(raw)
        assert result["governing_law_value"]["value"] == "РФ"
        assert result["governing_law_value"]["location"] == {
            "clause_ref": "п. 12.1",
            "page": 7,
        }

    def test_parse_response_accepts_null_location(self) -> None:
        detector, _ = _make_detector()
        raw = json.dumps(
            {
                "fields": {
                    "governing_law_status": {
                        "value": "present",
                        "confidence": 0.95,
                        "location": None,
                    }
                }
            },
            ensure_ascii=False,
        )

        result = detector._parse_response(raw)
        assert result["governing_law_status"]["location"] is None


class TestExampleJsonLocationContract:
    def test_build_example_json_includes_location_key(self) -> None:
        detector, _ = _make_detector()
        cfg = ExtractionConfig(
            enabled=True,
            mode="llm",
            fields=[
                ExtractionFieldConfig(
                    name="governing_law_value",
                    type=ExtractionFieldType.STRING,
                    label="Применимое право",
                ),
            ],
        )

        example = detector._build_example_json(cfg)
        parsed = json.loads(example)
        payload = parsed["fields"]["governing_law_value"]

        assert "location" in payload
        assert payload["location"] == {"clause_ref": "п. 1.1", "page": 1}


class TestAllowedValueSpecNormalization:
    def test_normalize_fields_supports_allowed_value_spec(self) -> None:
        detector, _ = _make_detector()
        cfg = ExtractionConfig(
            enabled=True,
            mode="llm",
            fields=[
                ExtractionFieldConfig(
                    name="status",
                    type=ExtractionFieldType.STRING,
                    label="Статус",
                    allowed_values=[
                        AllowedValueSpec(value="present", label="Указано"),
                        AllowedValueSpec(value="missing", label="Не указано"),
                    ],
                ),
            ],
        )

        result = detector._normalize_fields(
            {
                "status": {
                    "value": "present",
                    "confidence": 0.9,
                    "location": None,
                }
            },
            cfg,
        )

        assert result["status"]["value"] == "present"


class TestEvidenceListHandling:
    def test_cast_to_type_evidence_list_returns_value_as_is(self) -> None:
        detector, _ = _make_detector()
        field = ExtractionFieldConfig(
            name="evidence",
            type=ExtractionFieldType.EVIDENCE_LIST,
            presentation="diagnostic",
            role="subgroup_metadata",
        )

        raw_value = [
            {"field_name": "governing_law_value", "clause_ref": "п. 12.1", "page": 7}
        ]
        result = detector._cast_to_type(field, raw_value)

        assert result == raw_value


class TestExtractLocationValidation:
    def test_extract_validates_location_and_sets_high_confidence(self) -> None:
        detector, client = _make_detector()

        fields = [
            ExtractionFieldConfig(
                name="governing_law_value",
                type=ExtractionFieldType.STRING,
                label="Применимое право",
            ),
        ]
        check = _make_check(fields)

        response = SimpleNamespace(
            text=json.dumps(
                {
                    "fields": {
                        "governing_law_value": {
                            "value": "РФ",
                            "confidence": 0.92,
                            "location": {
                                "clause_ref": "п. 12.1",
                                "page": 7,
                            },
                        }
                    }
                },
                ensure_ascii=False,
            )
        )
        client.call_with_retries.return_value = (response, {})

        with patch.object(detector, "_build_prompt", return_value="prompt"):
            result = detector.extract(
                check,
                "Стороны согласовали, что по п. 12.1 договор регулируется правом РФ.",
                context_pages=[7],
            )

        payload = result["governing_law_value"]
        assert payload["location"]["clause_ref"] == "п. 12.1"
        assert payload["location"]["page"] == 7
        assert payload["location"]["location_confidence"] == "high"
        assert "location_fallback" not in payload

    def test_extract_page_as_string_results_in_location_fallback(self) -> None:
        detector, client = _make_detector()

        fields = [
            ExtractionFieldConfig(
                name="governing_law_value",
                type=ExtractionFieldType.STRING,
                label="Применимое право",
            ),
        ]
        check = _make_check(fields)

        response = SimpleNamespace(
            text=json.dumps(
                {
                    "fields": {
                        "governing_law_value": {
                            "value": "РФ",
                            "confidence": 0.92,
                            "location": {
                                "clause_ref": "п. 12.1",
                                "page": "7",
                            },
                        }
                    }
                },
                ensure_ascii=False,
            )
        )
        client.call_with_retries.return_value = (response, {})

        with patch.object(detector, "_build_prompt", return_value="prompt"):
            result = detector.extract(
                check,
                "Стороны согласовали, что по п. 12.1 договор регулируется правом РФ.",
                context_pages=[7],
            )

        payload = result["governing_law_value"]
        assert payload["location"] is None
        assert "location_fallback" in payload
        assert "не подтверждена" in payload["location_fallback"]["reason"] or "не указал" in payload["location_fallback"]["reason"]


        
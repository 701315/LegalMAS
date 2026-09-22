"""
B3.1ab — quote passthrough through extraction LLM output pipeline.

Проверяет, что quote из ответа LLM:
1. появляется в example JSON, который уходит в промпт;
2. сохраняется в _normalize_fields;
3. переживает validate_location (не теряется в LocationInfo);
4. не ломает валидацию, когда quote отсутствует.
"""

from __future__ import annotations

import json

import pytest

from engine.detectors.extraction_llm_detector import ExtractionLLMDetector
from engine.detectors.location_validator import validate_location
from engine.playbook.models import LocationInfo


# ── 1. example JSON ──────────────────────────────────────────────────────────


class _FakeField:
    def __init__(
        self,
        name,
        allowed_values=None,
        type=None,
        presentation="fact",
        role=None,
    ):
        self.name = name
        self.allowed_values = allowed_values or []
        self.type = type
        self.presentation = presentation
        self.role = role


class _FakeExtractionCfg:
    def __init__(self, fields):
        self.fields = fields


def test_build_example_json_includes_quote():
    detector = ExtractionLLMDetector.__new__(ExtractionLLMDetector)
    cfg = _FakeExtractionCfg([_FakeField("governing_law")])

    raw = detector._build_example_json(cfg)
    parsed = json.loads(raw)

    assert "fields" in parsed
    loc = parsed["fields"]["governing_law"]["location"]
    assert loc is not None
    assert "quote" in loc
    assert isinstance(loc["quote"], str)
    assert loc["quote"]


def test_build_example_json_omits_quote_for_diagnostic():
    detector = ExtractionLLMDetector.__new__(ExtractionLLMDetector)
    cfg = _FakeExtractionCfg([_FakeField("summary", presentation="diagnostic")])

    parsed = json.loads(detector._build_example_json(cfg))
    assert parsed["fields"]["summary"]["location"] is None


# ── 2. LocationInfo accepts quote ────────────────────────────────────────────


def test_location_info_accepts_quote():
    info = LocationInfo(
        clause_ref="п. 7.1",
        page=3,
        location_confidence="high",
        quote="Стороны применяют право РФ.",
    )
    dumped = info.model_dump(exclude_none=True)
    assert dumped["quote"] == "Стороны применяют право РФ."


def test_location_info_quote_optional():
    info = LocationInfo(clause_ref="п. 7.1", page=3, location_confidence="high")
    dumped = info.model_dump(exclude_none=True)
    assert "quote" not in dumped


# ── 3. validate_location preserves quote ─────────────────────────────────────


def test_validate_location_preserves_quote_when_clause_matches():
    raw = {
        "clause_ref": "п. 7.1",
        "page": 3,
        "quote": "Стороны применяют право Российской Федерации.",
    }
    context_text = "7.1 Стороны применяют право Российской Федерации.\n"
    context_pages = [3]

    info, fallback = validate_location(raw, context_text, context_pages)

    assert info is not None
    assert info.quote == "Стороны применяют право Российской Федерации."
    assert fallback is None


def test_validate_location_keeps_quote_even_if_no_clause_ref_match():
    raw = {
        "clause_ref": "п. 99",
        "page": 42,
        "quote": "какой-то текст",
    }
    context_text = "нет такого пункта"
    context_pages = [1]

    info, fallback = validate_location(raw, context_text, context_pages)

    assert info is not None
    assert info.quote == "какой-то текст"
    assert info.location_confidence == "low"
    assert fallback is None


def test_validate_location_accepts_quote_only():
    raw = {"quote": "Стороны применяют право РФ."}
    info, fallback = validate_location(raw, "...", [1])

    assert info is not None
    assert info.quote == "Стороны применяют право РФ."
    assert info.location_confidence == "low"
    assert fallback is None


def test_validate_location_truncates_long_quote():
    long_quote = "слово " * 500
    raw = {"quote": long_quote}
    info, _ = validate_location(raw, "...", [1])

    assert info is not None
    assert info.quote is not None
    assert len(info.quote) <= 500


def test_validate_location_all_empty_returns_fallback():
    info, fallback = validate_location({}, "...", [1])
    assert info is None
    assert fallback is not None


# ── 4. _normalize_fields preserves quote ─────────────────────────────────────


def test_normalize_fields_preserves_quote():
    detector = ExtractionLLMDetector.__new__(ExtractionLLMDetector)
    cfg = _FakeExtractionCfg([_FakeField("governing_law")])

    raw = {
        "governing_law": {
            "value": "РФ",
            "confidence": 0.9,
            "location": {
                "clause_ref": "п. 7.1",
                "page": 3,
                "quote": "Стороны применяют право РФ.",
            },
        }
    }
    out = detector._normalize_fields(raw, cfg)

    loc = out["governing_law"]["location"]
    assert loc["quote"] == "Стороны применяют право РФ."
    assert loc["clause_ref"] == "п. 7.1"
    assert loc["page"] == 3


def test_normalize_fields_accepts_quote_only_location():
    detector = ExtractionLLMDetector.__new__(ExtractionLLMDetector)
    cfg = _FakeExtractionCfg([_FakeField("governing_law")])

    raw = {
        "governing_law": {
            "value": "РФ",
            "confidence": 0.9,
            "location": {"quote": "цитата из договора"},
        }
    }
    out = detector._normalize_fields(raw, cfg)

    loc = out["governing_law"]["location"]
    assert loc is not None
    assert loc["quote"] == "цитата из договора"
    assert "clause_ref" not in loc
    assert "page" not in loc


def test_normalize_fields_drops_empty_location():
    detector = ExtractionLLMDetector.__new__(ExtractionLLMDetector)
    cfg = _FakeExtractionCfg([_FakeField("governing_law")])

    raw = {
        "governing_law": {
            "value": "РФ",
            "confidence": 0.9,
            "location": {"quote": ""},
        }
    }
    out = detector._normalize_fields(raw, cfg)

    assert out["governing_law"]["location"] is None


def test_normalize_fields_truncates_long_quote():
    detector = ExtractionLLMDetector.__new__(ExtractionLLMDetector)
    cfg = _FakeExtractionCfg([_FakeField("governing_law")])

    raw = {
        "governing_law": {
            "value": "РФ",
            "confidence": 0.9,
            "location": {"quote": "слово " * 500},
        }
    }
    out = detector._normalize_fields(raw, cfg)

    loc = out["governing_law"]["location"]
    assert loc is not None
    assert len(loc["quote"]) <= 500

# tests/unit/engine/checks/test_executor_field_extraction.py

from __future__ import annotations

from types import SimpleNamespace

import engine.checks.executor as executor_module
from engine.checks.executor import CheckExecutor
from engine.playbook.models import (
    CheckDefinition,
    DetectorType,
    ExtractionConfig,
    ExtractionFieldConfig,
    ExtractionFieldType,
)


def _make_check(
    *,
    check_id: str = "check_001",
    name: str = "Test Check",
    ui_mode: str | None = None,
    severity: str = "high",
    severity_if_fail: str | None = "critical",
    severity_if_pass: str | None = "pass",
    severity_if_unclear: str | None = "medium",
    extraction_enabled: bool = False,
    extraction_fields: list[dict] | None = None,
) -> CheckDefinition:
    extraction = None
    if extraction_enabled or extraction_fields is not None:
        fields = [
            ExtractionFieldConfig(
                name=f["name"],
                type=ExtractionFieldType(f.get("type", "string")),
                description=f.get("description", ""),
                unit=f.get("unit"),
            )
            for f in (extraction_fields or [{"name": "sample_field"}])
        ]
        extraction = ExtractionConfig(enabled=True, fields=fields)

    return CheckDefinition(
        id=check_id,
        name=name,
        ui_mode=ui_mode,
        severity=severity,
        severity_if_fail=severity_if_fail,
        severity_if_pass=severity_if_pass,
        severity_if_unclear=severity_if_unclear,
        detector_type=DetectorType.RULES,
        extraction=extraction,
    )


def _make_doc() -> SimpleNamespace:
    return SimpleNamespace(
        id="doc-1",
        doc_type="contract",
        classification_confidence=0.95,
    )


def _make_chunks() -> list[dict]:
    return [
        {
            "id": "chunk-1",
            "text": "This Agreement is governed by the laws of the Russian Federation.",
            "score": 0.9,
            "metadata": {
                "element_ids": ["chunk-1"],
                "effective_uid": "1.1",
                "start_page": 1,
                "end_page": 1,
                "page": 1,
                "path_titles": ["Governing law"],
            },
        }
    ]


class _MetricStub:
    def labels(self, **kwargs):
        return self

    def observe(self, value):
        return None

    def inc(self):
        return None


class _FakeRetrievalEngine:
    def __init__(self, chunks, important_terms=None):
        self.chunks = chunks
        self.important_terms = important_terms or []

    def search(self, query, top_k):
        return list(self.chunks)[:top_k]


class _FakeDetector:
    def __init__(self, result=None, error: Exception | None = None):
        self.result = result or {
            "found": False,
            "evidence": "",
            "confidence": 0.0,
            "method": "rules",
            "reason": "rules_unclear",
            "sources": [],
            "location": None,
            "raw": {},
        }
        self.error = error
        self.calls: list[dict] = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


class _FakeExtractor:
    def __init__(self, result=None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls: list[dict] = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


def _make_executor(detector, extractor) -> CheckExecutor:
    executor = object.__new__(CheckExecutor)
    executor.detector = detector
    executor.extractor = extractor
    return executor


def _patch_common(monkeypatch):
    monkeypatch.setattr(executor_module, "RetrievalEngine", _FakeRetrievalEngine)
    metric = _MetricStub()
    monkeypatch.setattr(
        executor_module,
        "METRICS",
        SimpleNamespace(
            check_duration=metric,
            checks_executed=metric,
        ),
    )


class TestIsFieldExtractionCheck:
    def test_explicit_field_extraction(self):
        check = _make_check(ui_mode="field_extraction")
        assert CheckExecutor._is_field_extraction_check(check) is True

    def test_explicit_clause_presence(self):
        check = _make_check(ui_mode="clause_presence", extraction_enabled=True)
        assert CheckExecutor._is_field_extraction_check(check) is False

    def test_explicit_risk_detection(self):
        check = _make_check(ui_mode="risk_detection", extraction_enabled=True)
        assert CheckExecutor._is_field_extraction_check(check) is False

    def test_fallback_to_extraction_enabled_when_ui_mode_none(self):
        check = _make_check(ui_mode=None, extraction_enabled=True)
        assert CheckExecutor._is_field_extraction_check(check) is True

    def test_blank_ui_mode_with_extraction_enabled(self):
        check = _make_check(ui_mode="", extraction_enabled=True)
        assert CheckExecutor._is_field_extraction_check(check) is True

    def test_none_when_no_ui_mode_and_no_extraction(self):
        check = _make_check(ui_mode=None, extraction_enabled=False)
        assert CheckExecutor._is_field_extraction_check(check) is False


class TestHasMeaningfulExtraction:
    def test_none_input(self):
        assert CheckExecutor._has_meaningful_extraction(None) is False

    def test_empty_dict(self):
        assert CheckExecutor._has_meaningful_extraction({}) is False

    def test_meaningful_value(self):
        sd = {"governing_law": {"value": "РФ"}}
        assert CheckExecutor._has_meaningful_extraction(sd) is True

    def test_not_found_only(self):
        sd = {
            "governing_law": {"value": "not_found"},
            "forum": {"value": "Данные не определены"},
        }
        assert CheckExecutor._has_meaningful_extraction(sd) is False

    def test_metadata_only(self):
        sd = {
            "reason": {"value": "partial"},
            "evidence": {"value": "some snippet"},
        }
        assert CheckExecutor._has_meaningful_extraction(sd) is False

    def test_metadata_and_fact(self):
        sd = {
            "reason": {"value": "partial"},
            "governing_law": {"value": "РФ"},
        }
        assert CheckExecutor._has_meaningful_extraction(sd) is True


class TestExecuteFieldExtraction:
    def test_execute_skips_presence_for_field_extraction(self, monkeypatch):
        _patch_common(monkeypatch)

        detector = _FakeDetector(error=AssertionError("detector must not be called"))
        extractor = _FakeExtractor(
            result={"governing_law": {"value": "РФ"}}
        )
        executor = _make_executor(detector, extractor)

        check = _make_check(
            ui_mode="field_extraction",
            extraction_fields=[
                {"name": "governing_law", "description": "Применимое право"},
            ],
        )

        result = executor.execute(_make_doc(), check, _make_chunks())

        assert detector.calls == []
        assert len(extractor.calls) == 1
        assert extractor.calls[0]["detection"]["method"] == "extraction_only"
        assert extractor.calls[0]["detection"]["reason"] == "field_extraction_skip_presence"
        assert result["detector_method"] == "extraction_only"
        assert result["result"] == "pass"
        assert result["severity"] == "pass"
        assert result["evidence"] == ""
        assert result["raw"]["llm_invoked"] is False
        assert result["raw"]["rules_llm_decision"] == "skip_presence_for_extraction"

    def test_execute_skips_presence_by_convention_when_ui_mode_none(self, monkeypatch):
        _patch_common(monkeypatch)

        detector = _FakeDetector(error=AssertionError("detector must not be called"))
        extractor = _FakeExtractor(
            result={"forum_display": {"value": "Применимое право: РФ; Форум: АС г. Москвы"}}
        )
        executor = _make_executor(detector, extractor)

        check = _make_check(
            ui_mode=None,
            extraction_enabled=True,
            extraction_fields=[
                {"name": "forum_display", "description": "Форум"},
            ],
        )

        result = executor.execute(_make_doc(), check, _make_chunks())

        assert detector.calls == []
        assert len(extractor.calls) == 1
        assert result["result"] == "pass"
        assert result["detector_method"] == "extraction_only"

    def test_execute_field_extraction_empty_results_in_unclear(self, monkeypatch):
        _patch_common(monkeypatch)

        detector = _FakeDetector(error=AssertionError("detector must not be called"))
        extractor = _FakeExtractor(result=None)
        executor = _make_executor(detector, extractor)

        check = _make_check(
            ui_mode="field_extraction",
            extraction_fields=[
                {"name": "governing_law", "description": "Применимое право"},
            ],
        )

        result = executor.execute(_make_doc(), check, _make_chunks())

        assert result["result"] == "unclear"
        assert result["severity"] == "medium"
        assert result["raw"]["extraction_empty"] is True

    def test_execute_field_extraction_not_found_only_results_in_unclear(self, monkeypatch):
        _patch_common(monkeypatch)

        detector = _FakeDetector(error=AssertionError("detector must not be called"))
        extractor = _FakeExtractor(
            result={
                "governing_law": {"value": "not_found"},
                "forum": {"value": "Данные не определены"},
            }
        )
        executor = _make_executor(detector, extractor)

        check = _make_check(
            ui_mode="field_extraction",
            extraction_fields=[
                {"name": "governing_law", "description": "Применимое право"},
                {"name": "forum", "description": "Форум"},
            ],
        )

        result = executor.execute(_make_doc(), check, _make_chunks())

        assert result["result"] == "unclear"
        assert result["severity"] == "medium"
        assert result["raw"]["extraction_empty"] is True

    def test_execute_field_extraction_metadata_only_results_in_unclear(self, monkeypatch):
        _patch_common(monkeypatch)

        detector = _FakeDetector(error=AssertionError("detector must not be called"))
        extractor = _FakeExtractor(
            result={
                "reason": {"value": "partial"},
                "evidence": {"value": "some snippet"},
            }
        )
        executor = _make_executor(detector, extractor)

        check = _make_check(
            ui_mode="field_extraction",
            extraction_fields=[
                {"name": "governing_law", "description": "Применимое право"},
            ],
        )

        result = executor.execute(_make_doc(), check, _make_chunks())

        assert result["result"] == "unclear"
        assert result["severity"] == "medium"
        assert result["raw"]["extraction_empty"] is True


class TestExecuteRegressionNonFieldExtraction:
    def test_execute_clause_presence_keeps_presence_detection(self, monkeypatch):
        _patch_common(monkeypatch)

        detector = _FakeDetector(
            result={
                "found": False,
                "evidence": "",
                "confidence": 0.95,
                "method": "rules",
                "reason": "rules_clean_negative",
                "sources": [],
                "location": None,
                "raw": {"source": "rules_clean_negative"},
            }
        )
        extractor = _FakeExtractor(result=None)
        executor = _make_executor(detector, extractor)

        check = _make_check(
            ui_mode="clause_presence",
            extraction_enabled=False,
        )

        result = executor.execute(_make_doc(), check, _make_chunks())

        assert len(detector.calls) == 1
        assert result["detector_method"] == "rules"
        assert result["result"] == "missing_required_clause"

    def test_execute_risk_detection_keeps_presence_detection(self, monkeypatch):
        _patch_common(monkeypatch)

        detector = _FakeDetector(
            result={
                "found": True,
                "evidence": "Risky clause found in section 5.",
                "confidence": 0.92,
                "method": "rules",
                "reason": "rules_confident_positive",
                "sources": [],
                "location": None,
                "raw": {"source": "rules_confident_positive"},
            }
        )
        extractor = _FakeExtractor(result=None)
        executor = _make_executor(detector, extractor)

        check = _make_check(
            ui_mode="risk_detection",
            extraction_enabled=False,
        )

        result = executor.execute(_make_doc(), check, _make_chunks())

        assert len(detector.calls) == 1
        assert result["result"] == "fail"
        assert result["severity"] == "critical"

    def test_execute_rules_only_check_keeps_confidence_mapping(self, monkeypatch):
        _patch_common(monkeypatch)

        detector = _FakeDetector(
            result={
                "found": False,
                "evidence": "",
                "confidence": 0.75,
                "method": "rules",
                "reason": "rules_clean_negative",
                "sources": [],
                "location": None,
                "raw": {"source": "rules_clean_negative"},
            }
        )
        extractor = _FakeExtractor(result=None)
        executor = _make_executor(detector, extractor)

        check = _make_check(
            ui_mode=None,
            extraction_enabled=False,
        )

        result = executor.execute(_make_doc(), check, _make_chunks())

        assert len(detector.calls) == 1
        assert result["result"] == "pass"
        assert result["severity"] == "pass"

    def test_execute_non_field_extraction_llm_error_override_is_preserved(self, monkeypatch):
        _patch_common(monkeypatch)

        detector = _FakeDetector(
            result={
                "found": False,
                "evidence": "",
                "confidence": 0.95,
                "method": "hybrid",
                "reason": "rules_unclear",
                "sources": [],
                "location": None,
                "raw": {
                    "source": "llm_timeout",
                    "llm_error_type": "timeout",
                    "llm_error_message": "timeout",
                    "llm_attempts": 1,
                },
            }
        )
        extractor = _FakeExtractor(result=None)
        executor = _make_executor(detector, extractor)

        check = _make_check(
            ui_mode="risk_detection",
            extraction_enabled=False,
        )

        result = executor.execute(_make_doc(), check, _make_chunks())

        assert len(detector.calls) == 1
        assert result["result"] == "unclear"
        assert result["severity"] == "medium"
        assert result["llm_required"] is True
        assert result["llm_error_type"] == "timeout"



        
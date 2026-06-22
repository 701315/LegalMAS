# tests/unit/engine/checks/test_ui_mode_infrastructure.py
"""
Tests for ui_mode semantic contract infrastructure.

Verifies that ui_mode flows correctly through all materialization paths:
1. GlobalCheckConfig (compiler schema) carries ui_mode.
2. load_playbook_from_dict (global playbook loader) passes ui_mode to CheckDefinition.
3. DocTypeCheckLoader passes ui_mode from YAML to CheckDefinition.
4. PlaybookConverter passes ui_mode from raw YAML to CheckDefinition.
5. CheckExecutor business-result mapping respects clause_presence semantics.

These tests protect the invariant:
    ui_mode declared in playbook YAML
    → arrives at CheckDefinition in runtime
    → influences business-result mapping in executor.

Universal: not specific to any document type, language, or check.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from engine.checks.executor import CheckExecutor
from engine.playbook.models import (
    CheckDefinition,
    DetectorType,
    LLMConfig,
    RetrievalConfig,
    RulesConfig,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _make_doc() -> SimpleNamespace:
    return SimpleNamespace(
        id="doc-1",
        doc_type="test_type",
        classification_confidence=0.95,
    )


def _make_chunks() -> list[dict]:
    return [
        {
            "id": "chunk-1",
            "text": "Кадастровый номер 78:36:0005503:4 земельного участка.",
            "score": 0.9,
            "metadata": {
                "element_ids": ["chunk-1"],
                "effective_uid": "main_contract:1.6",
                "start_page": 3,
                "end_page": 3,
                "page": 3,
                "path_titles": ["Предмет договора"],
            },
        }
    ]


def _make_presence_check(**overrides) -> CheckDefinition:
    defaults = dict(
        id="test_presence_check",
        name="Test Presence Check",
        description="Tests presence of required element",
        detector_type=DetectorType.RULES,
        ui_mode="clause_presence",
        severity="critical",
        severity_if_pass="pass",
        severity_if_fail="critical",
        severity_if_unclear="high",
        rules=RulesConfig(keywords=["кадастровый номер"]),
        llm=LLMConfig(),
        retrieval=RetrievalConfig(context_k=3),
    )
    defaults.update(overrides)
    return CheckDefinition(**defaults)


def _make_risk_check(**overrides) -> CheckDefinition:
    defaults = dict(
        id="test_risk_check",
        name="Test Risk Check",
        description="Tests presence of risk",
        detector_type=DetectorType.RULES,
        ui_mode="risk_detection",
        severity="high",
        severity_if_fail="high",
        rules=RulesConfig(keywords=["арест"]),
        llm=LLMConfig(),
        retrieval=RetrievalConfig(context_k=3),
    )
    defaults.update(overrides)
    return CheckDefinition(**defaults)


def _make_detector_result(
    *,
    found: bool,
    method: str = "rules",
    source: str = "rules_only_detector_type",
    llm_error_type: str | None = None,
) -> dict:
    return {
        "found": found,
        "evidence": "test evidence" if found else "",
        "confidence": 0.5 if found else 0.0,
        "method": method,
        "reason": "matched rules" if found else "no_keywords_or_patterns_matched",
        "sources": [],
        "location": None,
        "raw": {
            "source": source,
            "llm_invoked": method != "rules",
            "llm_error_type": llm_error_type,
            "rules_llm_decision": source,
        },
    }


# ─── 1. Compiler schema ──────────────────────────────────────────────────────


class TestCompilerSchemaUiMode:
    """GlobalCheckConfig must carry ui_mode field."""

    def test_accepts_clause_presence(self):
        from core.playbooks.compiler import GlobalCheckConfig

        cfg = GlobalCheckConfig(
            id="test",
            name="Test",
            detector_type="rules",
            ui_mode="clause_presence",
        )
        assert cfg.ui_mode == "clause_presence"

    def test_accepts_risk_detection(self):
        from core.playbooks.compiler import GlobalCheckConfig

        cfg = GlobalCheckConfig(
            id="test",
            name="Test",
            detector_type="rules",
            ui_mode="risk_detection",
        )
        assert cfg.ui_mode == "risk_detection"

    def test_accepts_field_extraction(self):
        from core.playbooks.compiler import GlobalCheckConfig

        cfg = GlobalCheckConfig(
            id="test",
            name="Test",
            detector_type="hybrid",
            ui_mode="field_extraction",
        )
        assert cfg.ui_mode == "field_extraction"

    def test_default_is_none(self):
        from core.playbooks.compiler import GlobalCheckConfig

        cfg = GlobalCheckConfig(
            id="test",
            name="Test",
            detector_type="rules",
        )
        assert cfg.ui_mode is None

    def test_serializes_ui_mode(self):
        from core.playbooks.compiler import GlobalCheckConfig

        cfg = GlobalCheckConfig(
            id="test",
            name="Test",
            detector_type="rules",
            ui_mode="clause_presence",
        )
        dumped = cfg.model_dump()
        assert "ui_mode" in dumped
        assert dumped["ui_mode"] == "clause_presence"

    def test_serializes_none_ui_mode(self):
        from core.playbooks.compiler import GlobalCheckConfig

        cfg = GlobalCheckConfig(
            id="test",
            name="Test",
            detector_type="rules",
        )
        dumped = cfg.model_dump()
        assert "ui_mode" in dumped
        assert dumped["ui_mode"] is None


# ─── 2. Global playbook loader ───────────────────────────────────────────────


class TestGlobalPlaybookLoaderUiMode:
    """load_playbook_from_dict must pass ui_mode to CheckDefinition."""

    def _make_raw_playbook(self, checks: list[dict]) -> dict:
        return {"checks": checks, "meta": {"version_schema": 1}}

    def test_clause_presence_passes_through(self):
        from engine.playbook.loader import load_playbook_from_dict

        raw = self._make_raw_playbook([
            {
                "id": "check_1",
                "name": "Presence",
                "detector_type": "rules",
                "ui_mode": "clause_presence",
                "severity": "critical",
            }
        ])
        playbook = load_playbook_from_dict(raw)
        assert playbook.checks[0].ui_mode == "clause_presence"

    def test_risk_detection_passes_through(self):
        from engine.playbook.loader import load_playbook_from_dict

        raw = self._make_raw_playbook([
            {
                "id": "check_2",
                "name": "Risk",
                "detector_type": "hybrid",
                "ui_mode": "risk_detection",
                "severity": "high",
            }
        ])
        playbook = load_playbook_from_dict(raw)
        assert playbook.checks[0].ui_mode == "risk_detection"

    def test_missing_ui_mode_becomes_none(self):
        from engine.playbook.loader import load_playbook_from_dict

        raw = self._make_raw_playbook([
            {
                "id": "check_3",
                "name": "Legacy",
                "detector_type": "rules",
                "severity": "medium",
            }
        ])
        playbook = load_playbook_from_dict(raw)
        assert playbook.checks[0].ui_mode is None

    def test_multiple_checks_each_get_correct_ui_mode(self):
        from engine.playbook.loader import load_playbook_from_dict

        raw = self._make_raw_playbook([
            {
                "id": "c1",
                "name": "C1",
                "detector_type": "rules",
                "ui_mode": "clause_presence",
                "severity": "critical",
            },
            {
                "id": "c2",
                "name": "C2",
                "detector_type": "hybrid",
                "ui_mode": "risk_detection",
                "severity": "high",
            },
            {
                "id": "c3",
                "name": "C3",
                "detector_type": "rules",
                "severity": "medium",
            },
        ])
        playbook = load_playbook_from_dict(raw)
        checks_by_id = {c.id: c for c in playbook.checks}

        assert checks_by_id["c1"].ui_mode == "clause_presence"
        assert checks_by_id["c2"].ui_mode == "risk_detection"
        assert checks_by_id["c3"].ui_mode is None


# ─── 3. DocTypeCheckLoader ───────────────────────────────────────────────────


class TestDocTypeCheckLoaderUiMode:
    """DocTypeCheckLoader must pass ui_mode from YAML to CheckDefinition."""

    def _make_loader(self):
        from engine.doc_type_checks.loader import DocTypeCheckLoader
        return DocTypeCheckLoader.__new__(DocTypeCheckLoader)

    def test_checks_v8_clause_presence(self):
        loader = self._make_loader()
        item = {
            "id": "test_check",
            "name": "Required",
            "ui_mode": "clause_presence",
            "severity": "critical",
            "severity_if_pass": "pass",
            "severity_if_fail": "critical",
            "detector_type": "rules",
            "rules": {"keywords": ["тест"]},
        }
        check = loader._build_check_from_v8(item, "test_type", {})
        assert check is not None
        assert check.ui_mode == "clause_presence"

    def test_checks_v8_risk_detection(self):
        loader = self._make_loader()
        item = {
            "id": "risk_check",
            "name": "Risk",
            "ui_mode": "risk_detection",
            "severity": "high",
            "detector_type": "rules",
            "rules": {"keywords": ["риск"]},
        }
        check = loader._build_check_from_v8(item, "test_type", {})
        assert check is not None
        assert check.ui_mode == "risk_detection"

    def test_checks_v8_no_ui_mode_gives_none(self):
        loader = self._make_loader()
        item = {
            "id": "legacy_check",
            "name": "Legacy",
            "severity": "medium",
            "detector_type": "rules",
            "rules": {"keywords": ["тест"]},
        }
        check = loader._build_check_from_v8(item, "test_type", {})
        assert check is not None
        assert check.ui_mode is None

    def test_checks_v8_severity_if_pass_passes_through(self):
        loader = self._make_loader()
        item = {
            "id": "test_check",
            "name": "Test",
            "ui_mode": "clause_presence",
            "severity": "critical",
            "severity_if_pass": "pass",
            "severity_if_fail": "critical",
            "severity_if_unclear": "high",
            "detector_type": "rules",
            "rules": {"keywords": ["тест"]},
        }
        check = loader._build_check_from_v8(item, "test_type", {})
        assert check.severity_if_pass == "pass"
        assert check.severity_if_fail == "critical"
        assert check.severity_if_unclear == "high"

    def test_doc_type_check_ui_mode_passes_through(self):
        loader = self._make_loader()
        item = {
            "id": "required_element",
            "name": "Required Element",
            "ui_mode": "clause_presence",
            "severity": "critical",
            "severity_if_pass": "pass",
            "severity_if_fail": "critical",
            "rules": {"keywords": ["обязательно"]},
        }
        check = loader._build_check_from_doc_type(item, "test_type", {})
        assert check is not None
        assert check.ui_mode == "clause_presence"
        assert check.severity_if_pass == "pass"

    def test_doc_type_check_no_ui_mode_gives_none(self):
        loader = self._make_loader()
        item = {
            "id": "legacy_required",
            "name": "Legacy Required",
            "severity": "medium",
            "rules": {"keywords": ["обязательно"]},
        }
        check = loader._build_check_from_doc_type(item, "test_type", {})
        assert check is not None
        assert check.ui_mode is None

    def test_compliance_check_ui_mode_passes_through(self):
        loader = self._make_loader()
        rule = {
            "id": "compliance_check",
            "name": "Compliance",
            "ui_mode": "clause_presence",
            "severity": "critical",
            "severity_if_fail": "critical",
            "rules": {"keywords": ["обязательно"]},
        }
        check = loader._build_compliance_check(rule, "test_type")
        assert check is not None
        assert check.ui_mode == "clause_presence"
        assert check.severity_if_fail == "critical"

    def test_compliance_check_no_ui_mode_gives_none(self):
        loader = self._make_loader()
        rule = {
            "id": "legacy_compliance",
            "name": "Legacy",
            "severity": "critical",
            "rules": {"keywords": ["обязательно"]},
        }
        check = loader._build_compliance_check(rule, "test_type")
        assert check is not None
        assert check.ui_mode is None


# ─── 4. PlaybookConverter ────────────────────────────────────────────────────


class TestPlaybookConverterUiMode:
    """PlaybookConverter must pass ui_mode from raw YAML to CheckDefinition."""

    def _make_converter(self):
        from engine.playbook.playbook_converter import PlaybookConverter
        return PlaybookConverter()

    def test_clause_presence_passes_through(self):
        converter = self._make_converter()
        raw_check = {
            "id": "test_check",
            "name": "Test",
            "ui_mode": "clause_presence",
            "severity": "critical",
        }
        check = converter._build_check_definition_from_yaml(raw_check)
        assert check.ui_mode == "clause_presence"

    def test_risk_detection_passes_through(self):
        converter = self._make_converter()
        raw_check = {
            "id": "test_check",
            "name": "Test",
            "ui_mode": "risk_detection",
            "severity": "high",
        }
        check = converter._build_check_definition_from_yaml(raw_check)
        assert check.ui_mode == "risk_detection"

    def test_no_ui_mode_gives_none(self):
        converter = self._make_converter()
        raw_check = {
            "id": "test_check",
            "name": "Test",
            "severity": "medium",
        }
        check = converter._build_check_definition_from_yaml(raw_check)
        assert check.ui_mode is None


# ─── 5. Executor: presence-aware business-result mapping ─────────────────────


class TestExecutorPresenceMapping:
    """
    CheckExecutor must use correct business logic per semantic class:

    clause_presence:
      found=True  → pass
      found=False + deterministic → missing_required_clause
      found=False + non-deterministic (LLM degraded) → unclear

    risk_detection / no ui_mode:
      found=True  → fail  (unchanged)
      found=False → pass/unclear (unchanged)
    """

    def test_presence_found_gives_pass(self):
        """clause_presence + found=True → pass."""
        check = _make_presence_check()
        doc = _make_doc()

        llm_client = MagicMock()
        executor = CheckExecutor(llm_client)

        with patch.object(executor, "detector") as mock_detector:
            mock_detector.run.return_value = _make_detector_result(found=True)
            result = executor.execute(doc=doc, check=check, chunks=_make_chunks())

        assert result["result"] == "pass", (
            f"clause_presence + found=True must give 'pass'. "
            f"Got: {result['result']!r}"
        )
        assert result["severity"] == "pass"

    def test_presence_not_found_deterministic_gives_missing(self):
        """clause_presence + rules not found → missing_required_clause."""
        check = _make_presence_check()
        doc = _make_doc()

        llm_client = MagicMock()
        executor = CheckExecutor(llm_client)

        with patch.object(executor, "detector") as mock_detector:
            mock_detector.run.return_value = _make_detector_result(
                found=False,
                method="rules",
                source="rules_only_detector_type",
            )
            result = executor.execute(doc=doc, check=check, chunks=_make_chunks())

        assert result["result"] == "missing_required_clause", (
            f"clause_presence + deterministic not found must give "
            f"'missing_required_clause'. Got: {result['result']!r}"
        )
        assert result["severity"] == "critical"

    def test_presence_not_found_llm_degraded_gives_unclear(self):
        """clause_presence + hybrid + LLM error → unclear (not missing_required_clause)."""
        check = _make_presence_check(detector_type=DetectorType.HYBRID)
        doc = _make_doc()

        llm_client = MagicMock()
        executor = CheckExecutor(llm_client)

        with patch.object(executor, "detector") as mock_detector:
            mock_detector.run.return_value = _make_detector_result(
                found=False,
                method="hybrid",
                source="rules_unclear_llm_transient_error",
                llm_error_type="transient_error",
            )
            result = executor.execute(doc=doc, check=check, chunks=_make_chunks())

        assert result["result"] == "unclear", (
            f"clause_presence + non-deterministic absence must give 'unclear'. "
            f"Got: {result['result']!r}"
        )

    def test_risk_detection_found_still_gives_fail(self):
        """Regression: risk_detection + found=True must still give fail."""
        check = _make_risk_check()
        doc = _make_doc()

        llm_client = MagicMock()
        executor = CheckExecutor(llm_client)

        with patch.object(executor, "detector") as mock_detector:
            mock_detector.run.return_value = _make_detector_result(found=True)
            result = executor.execute(doc=doc, check=check, chunks=_make_chunks())

        assert result["result"] == "fail", (
            f"risk_detection + found=True must still give 'fail'. "
            f"Got: {result['result']!r}"
        )

    def test_no_ui_mode_found_still_gives_fail(self):
        """Regression: no ui_mode + found=True must still give fail (legacy)."""
        check = _make_risk_check(ui_mode=None)
        doc = _make_doc()

        llm_client = MagicMock()
        executor = CheckExecutor(llm_client)

        with patch.object(executor, "detector") as mock_detector:
            mock_detector.run.return_value = _make_detector_result(found=True)
            result = executor.execute(doc=doc, check=check, chunks=_make_chunks())

        assert result["result"] == "fail", (
            f"Legacy check (ui_mode=None) + found=True must still give 'fail'. "
            f"Got: {result['result']!r}"
        )

    def test_presence_severity_if_pass_used_when_found(self):
        """clause_presence + found → severity comes from severity_if_pass."""
        check = _make_presence_check(
            severity_if_pass="pass",
            severity_if_fail="critical",
        )
        doc = _make_doc()

        llm_client = MagicMock()
        executor = CheckExecutor(llm_client)

        with patch.object(executor, "detector") as mock_detector:
            mock_detector.run.return_value = _make_detector_result(found=True)
            result = executor.execute(doc=doc, check=check, chunks=_make_chunks())

        assert result["severity"] == "pass"

    def test_presence_severity_if_fail_used_when_not_found(self):
        """clause_presence + not found → severity comes from severity_if_fail."""
        check = _make_presence_check(
            severity_if_pass="pass",
            severity_if_fail="critical",
        )
        doc = _make_doc()

        llm_client = MagicMock()
        executor = CheckExecutor(llm_client)

        with patch.object(executor, "detector") as mock_detector:
            mock_detector.run.return_value = _make_detector_result(
                found=False,
                source="rules_only_detector_type",
            )
            result = executor.execute(doc=doc, check=check, chunks=_make_chunks())

        assert result["severity"] == "critical"


# ─── 6. End-to-end semantic flow ─────────────────────────────────────────────


class TestSemanticFlowEndToEnd:
    """
    Verifies that ui_mode from YAML → CheckDefinition → executor is coherent.
    """

    def test_compiled_check_with_ui_mode_reaches_executor(self):
        """
        ui_mode in compiled playbook dict → CheckDefinition.ui_mode is set.
        Verifies the full path: compiled dict → loader → CheckDefinition.
        """
        from engine.playbook.loader import load_playbook_from_dict

        raw = {
            "checks": [
                {
                    "id": "cadastral_required",
                    "name": "Кадастровый номер (ст. 554 ГК РФ)",
                    "detector_type": "rules",
                    "ui_mode": "clause_presence",
                    "severity": "critical",
                    "severity_if_pass": "pass",
                    "severity_if_fail": "critical",
                }
            ],
            "meta": {"version_schema": 1},
        }

        playbook = load_playbook_from_dict(raw)
        check = playbook.checks[0]

        assert check.ui_mode == "clause_presence"
        assert check.severity_if_pass == "pass"
        assert check.severity_if_fail == "critical"

    def test_doc_type_check_with_ui_mode_reaches_executor(self):
        """
        ui_mode in doc-type YAML item → CheckDefinition.ui_mode is set.
        """
        from engine.doc_type_checks.loader import DocTypeCheckLoader

        loader = DocTypeCheckLoader.__new__(DocTypeCheckLoader)

        item = {
            "id": "cadastral_number_required_for_land_plot",
            "name": "Земля: обязательность кадастрового номера (ст. 554 ГК РФ)",
            "ui_mode": "clause_presence",
            "severity": "critical",
            "severity_if_pass": "pass",
            "severity_if_fail": "critical",
            "severity_if_unclear": "high",
            "detector_type": "rules",
            "rules": {
                "keywords": ["кадастровый номер"],
                "regex_patterns": [r"(?i)\b\d{2}:\d{2}:\d{6,7}:\d+\b"],
            },
        }

        check = loader._build_check_from_v8(
            item,
            "contract_1.6_real_estate",
            {},
        )

        assert check is not None
        assert check.ui_mode == "clause_presence"
        assert check.severity_if_pass == "pass"
        assert check.severity_if_fail == "critical"



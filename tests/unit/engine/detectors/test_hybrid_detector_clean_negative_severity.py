from __future__ import annotations

from unittest.mock import MagicMock, patch

from engine.detectors.hybrid_detector import HybridDetector
from engine.detectors.models import RetrievedChunk
from engine.playbook.models import (
    CheckDefinition,
    DetectorType,
    EvidenceConfig,
    LLMConfig,
    RetrievalConfig,
    RulesConfig,
)


def _make_chunk() -> RetrievedChunk:
    return RetrievedChunk(
        element_id="elem1",
        text="обычный текст договора без нужных keywords",
        page=1,
        clause_uid="main_contract:1.1",
        bbox=[],
        dense_score=0.8,
        sparse_score=0.5,
        metadata_score=0.2,
        combined_score=0.75,
    )


def _make_detector() -> HybridDetector:
    client = MagicMock()
    client.is_available.return_value = True
    return HybridDetector(llm_client=client)


def _make_check(
    *,
    severity: str = "medium",
    severity_if_fail: str | None = None,
) -> CheckDefinition:
    return CheckDefinition(
        id="clean_negative_check",
        name="Clean Negative Check",
        detector_type=DetectorType.HYBRID,
        severity=severity,
        severity_if_fail=severity_if_fail,
        rules=RulesConfig(
            keywords=["несуществующий термин"],
            regex_patterns=[],
        ),
        llm=LLMConfig(
            prompt_template="Найди {condition_name}. Контекст: {context}",
        ),
        retrieval=RetrievalConfig(),
        evidence=EvidenceConfig(),
    )


class TestHybridDetectorCleanNegativeSeverityRouting:
    def test_medium_severity_clean_negative_skips_llm_by_default(self) -> None:
        detector = _make_detector()
        check = _make_check(severity="medium", severity_if_fail="medium")
        chunks = [_make_chunk()]

        result = detector.run(
            text="обычный текст без совпадений",
            chunks=chunks,
            check=check,
        )

        assert result["raw"]["llm_invoked"] is False
        assert result["raw"]["rules_llm_decision"] == "rules_clean_negative"

    def test_high_severity_clean_negative_invokes_llm(self) -> None:
        detector = _make_detector()
        check = _make_check(severity="medium", severity_if_fail="high")
        chunks = [_make_chunk()]

        mock_llm_result = MagicMock()
        mock_llm_result.found = False
        mock_llm_result.confidence = 0.4
        mock_llm_result.evidence_chunks = []
        mock_llm_result.details = {}

        with patch.object(detector.llm, "detect_with_variables", return_value=mock_llm_result):
            result = detector.run(
                text="обычный текст без совпадений",
                chunks=chunks,
                check=check,
            )

        assert result["raw"]["llm_invoked"] is True
        assert result["raw"]["rules_llm_decision"] == "high_severity_clean_negative_requires_llm"

    def test_critical_severity_clean_negative_invokes_llm(self) -> None:
        detector = _make_detector()
        check = _make_check(severity="critical", severity_if_fail="critical")
        chunks = [_make_chunk()]

        mock_llm_result = MagicMock()
        mock_llm_result.found = False
        mock_llm_result.confidence = 0.4
        mock_llm_result.evidence_chunks = []
        mock_llm_result.details = {}

        with patch.object(detector.llm, "detect_with_variables", return_value=mock_llm_result):
            result = detector.run(
                text="обычный текст без совпадений",
                chunks=chunks,
                check=check,
            )

        assert result["raw"]["llm_invoked"] is True
        assert result["raw"]["rules_llm_decision"] == "high_severity_clean_negative_requires_llm"

        
"""
Tests for HybridDetector detector_type routing contract.

Covers:
- detector_type=rules: never invokes LLM, returns rules result directly
- detector_type=llm: skips rules routing, goes to LLM path
- detector_type=hybrid: unchanged behavior (rules → LLM fallback)

These tests verify the universal architectural invariant:
detector_type declared in playbook MUST be respected by HybridDetector.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

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


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _make_check(
    check_id: str = "test_check",
    detector_type: DetectorType = DetectorType.HYBRID,
    *,
    prompt_template: str = "",
    prompt_file: str | None = None,
    keywords: list[str] | None = None,
    regex_patterns: list[str] | None = None,
) -> CheckDefinition:
    return CheckDefinition(
        id=check_id,
        name=f"Test Check {check_id}",
        detector_type=detector_type,
        rules=RulesConfig(
            keywords=keywords or [],
            regex_patterns=regex_patterns or [],
        ),
        llm=LLMConfig(
            prompt_template=prompt_template,
            prompt_file=prompt_file,
        ),
        retrieval=RetrievalConfig(),
        evidence=EvidenceConfig(),
    )


def _make_chunk() -> RetrievedChunk:
    return RetrievedChunk(
        element_id="elem1",
        text="тестовый текст договора",
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


# ─── detector_type = RULES ────────────────────────────────────────────────────


class TestDetectorTypeRules:
    def test_rules_only_never_invokes_llm_when_found(self) -> None:
        """
        When detector_type=rules and rules found something,
        LLM must NOT be invoked regardless of confidence level.
        """
        detector = _make_detector()
        check = _make_check(
            detector_type=DetectorType.RULES,
            keywords=["кадастровый номер"],
        )
        text = "Земельный участок, кадастровый номер 78:36:0005503:4"
        chunks = [_make_chunk()]

        result = detector.run(text=text, chunks=chunks, check=check)

        assert result["raw"]["rules_llm_decision"] == "rules_only_detector_type"
        assert result["raw"]["llm_invoked"] is False
        assert result["method"] == "rules"

    def test_rules_only_never_invokes_llm_when_not_found(self) -> None:
        """
        When detector_type=rules and rules found nothing,
        LLM must NOT be invoked even when no prompt exists.
        """
        detector = _make_detector()
        check = _make_check(
            detector_type=DetectorType.RULES,
            keywords=["несуществующий термин"],
        )
        text = "Обычный текст без нужного термина."
        chunks = [_make_chunk()]

        result = detector.run(text=text, chunks=chunks, check=check)

        assert result["raw"]["rules_llm_decision"] == "rules_only_detector_type"
        assert result["raw"]["llm_invoked"] is False
        assert result["method"] == "rules"

    def test_rules_only_with_weak_confidence_does_not_require_llm(self) -> None:
        """
        When detector_type=rules, even a weak rules positive
        must NOT trigger llm_required=True.

        This was the original bug: weak positive + detector_type=rules
        incorrectly set llm_required=True.
        """
        detector = _make_detector()
        check = _make_check(
            detector_type=DetectorType.RULES,
            regex_patterns=[r"(?i)\b\d{2}:\d{2}:\d{6,7}:\d+\b"],
        )
        text = "78:36:0005503:4"  # кадастровый номер
        chunks = [_make_chunk()]

        result = detector.run(text=text, chunks=chunks, check=check)

        assert result["raw"]["rules_llm_decision"] == "rules_only_detector_type"
        assert result["raw"]["llm_invoked"] is False
        assert result["method"] == "rules"

        raw = result.get("raw", {})
        assert raw.get("llm_required") is not True

    def test_rules_only_source_is_correct(self) -> None:
        """The source field must clearly identify rules-only path."""
        detector = _make_detector()
        check = _make_check(detector_type=DetectorType.RULES)
        chunks = [_make_chunk()]

        result = detector.run(text="любой текст", chunks=chunks, check=check)

        assert result["raw"]["source"] == "rules_only_detector_type"


# ─── detector_type = LLM ─────────────────────────────────────────────────────


class TestDetectorTypeLlm:
    def test_llm_only_with_no_prompt_returns_no_llm_result(self) -> None:
        """
        When detector_type=llm but no prompt is configured,
        system should return gracefully without crashing.
        """
        detector = _make_detector()
        check = _make_check(
            detector_type=DetectorType.LLM,
            prompt_template="",
        )
        chunks = [_make_chunk()]

        result = detector.run(text="любой текст", chunks=chunks, check=check)

        assert result["raw"]["rules_llm_decision"] == "llm_only_no_llm_prompt"
        assert result["raw"]["llm_invoked"] is False

    def test_llm_only_with_prompt_invokes_llm(self) -> None:
        """
        When detector_type=llm and prompt exists, LLM must be invoked.
        """
        detector = _make_detector()
        check = _make_check(
            detector_type=DetectorType.LLM,
            prompt_template="Найди в тексте условие {condition_name}. Контекст: {context}",
        )
        chunks = [_make_chunk()]

        mock_llm_result = MagicMock()
        mock_llm_result.found = True
        mock_llm_result.confidence = 0.9
        mock_llm_result.evidence_chunks = []
        mock_llm_result.details = {}

        with patch.object(detector.llm, "detect_with_variables", return_value=mock_llm_result):
            result = detector.run(text="текст договора", chunks=chunks, check=check)

        assert result["raw"]["llm_invoked"] is True
        assert result["raw"]["source"] == "llm_only_detector_type"
        assert result["raw"]["rules_llm_decision"] == "llm_only_detector_type"
        assert result["method"] == "llm"


# ─── detector_type = HYBRID ──────────────────────────────────────────────────


class TestDetectorTypeHybrid:
    def test_hybrid_confident_positive_skips_llm(self) -> None:
        """
        When detector_type=hybrid and rules produce a confident positive
        (confidence >= RULES_CONFIDENCE_THRESHOLD=0.7), LLM must NOT be invoked.

        We use keyword_groups with level=high (confidence=0.85)
        which is above default threshold of 0.7.

        RulesDetector confidence formula:
        - keyword_groups high → 0.85
        - keyword_groups medium → 0.65
        - no groups → 0.4 + 0.1 * hits_count
        """
        detector = _make_detector()
        check = CheckDefinition(
            id="test_check",
            name="Test Check",
            detector_type=DetectorType.HYBRID,
            rules=RulesConfig(
                keyword_groups={
                    "high": ["ответственность", "стороны"],
                }
            ),
            llm=LLMConfig(
                prompt_template="Найди {condition_name}. {context}",
            ),
            retrieval=RetrievalConfig(),
            evidence=EvidenceConfig(),
        )
        # keyword_groups high hit → confidence=0.85 >= threshold=0.7
        text = "Стороны несут ответственность за нарушение условий договора."
        chunks = [_make_chunk()]

        result = detector.run(
            text=text,
            chunks=chunks,
            check=check,
            classification_confidence=1.0,
        )

        assert result["raw"]["llm_invoked"] is False
        assert result["raw"]["rules_llm_decision"] == "rules_confident_positive"

    def test_hybrid_weak_positive_attempts_llm(self) -> None:
        """
        When detector_type=hybrid and rules confidence is weak,
        LLM must be attempted.
        """
        detector = _make_detector()
        check = _make_check(
            detector_type=DetectorType.HYBRID,
            keywords=["ответственность"],
            prompt_template="Найди {condition_name}. {context}",
        )
        text = "ответственность"  # hit but likely low confidence
        chunks = [_make_chunk()]

        mock_llm_result = MagicMock()
        mock_llm_result.found = True
        mock_llm_result.confidence = 0.85
        mock_llm_result.evidence_chunks = []
        mock_llm_result.details = {}

        with patch.object(detector.llm, "detect_with_variables", return_value=mock_llm_result):
            result = detector.run(text=text, chunks=chunks, check=check)

        assert result["raw"]["llm_invoked"] is True

    def test_hybrid_with_no_prompt_stays_on_rules(self) -> None:
        """
        When detector_type=hybrid and no LLM prompt configured,
        system should gracefully stay on rules result.
        """
        detector = _make_detector()
        check = _make_check(
            detector_type=DetectorType.HYBRID,
            keywords=["ответственность"],
            prompt_template="",
        )
        text = "ответственность"
        chunks = [_make_chunk()]

        result = detector.run(text=text, chunks=chunks, check=check)

        assert result["raw"]["llm_invoked"] is False
        assert result["raw"]["source"] in (
            "rules_unclear_no_llm_prompt",
            "rules_confident_positive",
            "rules_clean_negative",
        )


# ─── Regression: hybrid path unchanged ───────────────────────────────────────


class TestHybridRegressionPath:
    def test_hybrid_clean_negative_does_not_call_llm_by_default(self) -> None:
        """
        When hybrid and rules found nothing clean,
        LLM is NOT called by default (RUN_LLM_ON_RULES_CLEAN_NEGATIVE=False).
        """
        detector = _make_detector()
        check = _make_check(
            detector_type=DetectorType.HYBRID,
            keywords=["термин которого нет"],
            prompt_template="Найди {condition_name}. {context}",
        )
        text = "Совершенно другой текст без нужного слова."
        chunks = [_make_chunk()]

        result = detector.run(text=text, chunks=chunks, check=check)

        assert result["raw"]["llm_invoked"] is False
        assert result["raw"]["rules_llm_decision"] == "rules_clean_negative"



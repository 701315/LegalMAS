# tests/services/structure/models/test_confidence.py

"""Tests for Phase 5 — Structural Confidence contracts."""

from __future__ import annotations

import pytest

from services.structure.models import (
    ConfidenceInput,
    DegradedModeConfig,
    RETRIEVAL_SAFE_THRESHOLD,
    StructuralConfidence,
)


def _make_inputs(**kwargs) -> ConfidenceInput:
    defaults = dict(
        heading_quality=0.9,
        grammar_consistency=0.9,
        recovery_confidence=0.8,
        numbering_stability=0.9,
        ocr_noise_ratio=0.0,
        rewrite_ratio=0.0,
        orphan_ratio=0.0,
        total_headings=10,
    )
    defaults.update(kwargs)
    return ConfidenceInput(**defaults)


class TestRetrievalSafeThreshold:
    def test_threshold_value(self):
        assert RETRIEVAL_SAFE_THRESHOLD == 0.7


class TestConfidenceInput:
    def test_basic_creation(self):
        inp = _make_inputs()
        assert inp.heading_quality == 0.9
        assert inp.total_headings == 10

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError, match="heading_quality"):
            _make_inputs(heading_quality=1.5)

    def test_negative_total_headings_raises(self):
        with pytest.raises(ValueError, match="total_headings"):
            _make_inputs(total_headings=-1)

    def test_zero_values_valid(self):
        inp = _make_inputs(
            heading_quality=0.0,
            grammar_consistency=0.0,
            recovery_confidence=0.0,
            numbering_stability=0.0,
        )
        assert inp.heading_quality == 0.0

    def test_to_dict(self):
        inp = _make_inputs()
        d = inp.to_dict()
        assert "heading_quality" in d
        assert "total_headings" in d


class TestDegradedModeConfig:
    def test_defaults(self):
        cfg = DegradedModeConfig()
        assert cfg.use_layout_fallback is True
        assert cfg.conservative_overlap is True
        assert cfg.skip_semantic_enrichment is True

    def test_custom(self):
        cfg = DegradedModeConfig(reason="low confidence")
        assert cfg.reason == "low confidence"

    def test_to_dict(self):
        cfg = DegradedModeConfig(reason="test")
        d = cfg.to_dict()
        assert d["use_layout_fallback"] is True
        assert d["reason"] == "test"


class TestStructuralConfidenceFromInputs:
    def test_high_quality_is_retrieval_safe(self):
        inp = _make_inputs()
        sc = StructuralConfidence.from_inputs(inp)
        assert sc.retrieval_safe is True
        assert sc.local_confidence >= RETRIEVAL_SAFE_THRESHOLD
        assert sc.degraded_mode is None

    def test_low_headings_triggers_degraded(self):
        inp = _make_inputs(total_headings=1)
        sc = StructuralConfidence.from_inputs(inp)
        assert sc.retrieval_safe is False
        assert sc.degraded_mode is not None

    def test_zero_headings_triggers_degraded(self):
        inp = _make_inputs(total_headings=0)
        sc = StructuralConfidence.from_inputs(inp)
        assert sc.retrieval_safe is False
        assert sc.degraded_mode is not None

    def test_low_grammar_consistency(self):
        inp = _make_inputs(grammar_consistency=0.1, numbering_stability=0.2)
        sc = StructuralConfidence.from_inputs(inp)
        assert sc.local_confidence < RETRIEVAL_SAFE_THRESHOLD

    def test_orphan_ratio_penalty(self):
        inp_clean = _make_inputs(orphan_ratio=0.0)
        inp_orphan = _make_inputs(orphan_ratio=0.5)
        sc_clean = StructuralConfidence.from_inputs(inp_clean)
        sc_orphan = StructuralConfidence.from_inputs(inp_orphan)
        assert sc_orphan.local_confidence < sc_clean.local_confidence

    def test_rewrite_ratio_penalty(self):
        inp_clean = _make_inputs(rewrite_ratio=0.0)
        inp_rewrite = _make_inputs(rewrite_ratio=0.5)
        sc_clean = StructuralConfidence.from_inputs(inp_clean)
        sc_rewrite = StructuralConfidence.from_inputs(inp_rewrite)
        assert sc_rewrite.local_confidence < sc_clean.local_confidence

    def test_ocr_noise_lowers_context_reliability(self):
        inp_clean = _make_inputs(ocr_noise_ratio=0.0)
        inp_noisy = _make_inputs(ocr_noise_ratio=0.7)
        sc_clean = StructuralConfidence.from_inputs(inp_clean)
        sc_noisy = StructuralConfidence.from_inputs(inp_noisy)
        assert sc_noisy.context_reliability < sc_clean.context_reliability

    def test_moderate_ocr_noise_penalty(self):
        inp_clean = _make_inputs(ocr_noise_ratio=0.0)
        inp_noisy = _make_inputs(ocr_noise_ratio=0.4)
        sc_clean = StructuralConfidence.from_inputs(inp_clean)
        sc_noisy = StructuralConfidence.from_inputs(inp_noisy)
        assert sc_noisy.context_reliability < sc_clean.context_reliability

    def test_degraded_mode_has_reason(self):
        inp = _make_inputs(total_headings=1)
        sc = StructuralConfidence.from_inputs(inp)
        assert sc.degraded_mode is not None
        assert sc.degraded_mode.reason != ""

    def test_degraded_mode_uses_layout_fallback(self):
        inp = _make_inputs(total_headings=0)
        sc = StructuralConfidence.from_inputs(inp)
        assert sc.degraded_mode is not None
        assert sc.degraded_mode.use_layout_fallback is True
        assert sc.degraded_mode.skip_semantic_enrichment is True

    def test_confidence_clamped_to_zero(self):
        inp = _make_inputs(
            heading_quality=0.0,
            grammar_consistency=0.0,
            recovery_confidence=0.0,
            numbering_stability=0.0,
            orphan_ratio=1.0,
            rewrite_ratio=1.0,
            total_headings=0,
        )
        sc = StructuralConfidence.from_inputs(inp)
        assert sc.local_confidence == 0.0
        assert sc.context_reliability == 0.0

    def test_deterministic(self):
        """same input → same output."""
        inp1 = _make_inputs(heading_quality=0.8, grammar_consistency=0.75)
        inp2 = _make_inputs(heading_quality=0.8, grammar_consistency=0.75)
        sc1 = StructuralConfidence.from_inputs(inp1)
        sc2 = StructuralConfidence.from_inputs(inp2)
        assert sc1.to_dict() == sc2.to_dict()


class TestStructuralConfidenceInvariants:
    def test_retrieval_safe_inconsistency_raises(self):
        inp = _make_inputs()
        with pytest.raises(ValueError, match="inconsistent"):
            StructuralConfidence(
                local_confidence=0.8,
                context_reliability=0.8,
                retrieval_safe=False,   # несоответствие: 0.8 >= 0.7
                degraded_mode=DegradedModeConfig(),
                inputs=inp,
            )

    def test_degraded_mode_present_when_retrieval_safe_raises(self):
        inp = _make_inputs()
        with pytest.raises(ValueError, match="degraded_mode must be None"):
            StructuralConfidence(
                local_confidence=0.8,
                context_reliability=0.8,
                retrieval_safe=True,
                degraded_mode=DegradedModeConfig(),  # не должно быть
                inputs=inp,
            )

    def test_degraded_mode_absent_when_not_retrieval_safe_raises(self):
        inp = _make_inputs()
        with pytest.raises(ValueError, match="degraded_mode must not be None"):
            StructuralConfidence(
                local_confidence=0.5,
                context_reliability=0.5,
                retrieval_safe=False,
                degraded_mode=None,   # должно быть
                inputs=inp,
            )

    def test_to_dict_structure(self):
        inp = _make_inputs()
        sc = StructuralConfidence.from_inputs(inp)
        d = sc.to_dict()
        assert "local_confidence" in d
        assert "context_reliability" in d
        assert "retrieval_safe" in d
        assert "degraded_mode" in d
        assert "inputs" in d


        
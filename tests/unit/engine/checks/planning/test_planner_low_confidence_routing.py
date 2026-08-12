from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from engine.checks.planning.planner import CheckPlanner


def _make_doc(
    *,
    doc_type: str = "SPA",
    classification_confidence: float = 0.42,
    classification_confidence_zone: str | None = None,
):
    doc = MagicMock()
    doc.id = uuid.uuid4()
    doc.doc_type = doc_type
    doc.applicable_triggers = []
    doc.classification_confidence = classification_confidence
    if classification_confidence_zone is not None:
        doc.classification_confidence_zone = classification_confidence_zone
    return doc


class _FakePlaybook:
    def get_conditional_checks(self, doc_type: str, triggers: list[str]):
        if doc_type == "":
            return [SimpleNamespace(id="generic_fallback_check")]
        return [SimpleNamespace(id=f"global_for_{doc_type}")]


class TestPlannerLowConfidenceRouting:
    def test_build_context_derives_low_zone_from_confidence(self):
        planner = CheckPlanner()
        doc = _make_doc(classification_confidence=0.42)  # between 0.40 and 0.45

        ctx = planner.build_context_for_document(doc, None)

        assert ctx.classification_confidence == 0.42
        assert ctx.classification_confidence_zone == "low"
        assert ctx.classification_requires_manual_review is True

    def test_confident_context_does_not_add_generic_fallback(self):
        playbook = _FakePlaybook()
        loader = MagicMock()
        loader.load_checks_for_doc.return_value = [SimpleNamespace(id="doc_type_check")]

        planner = CheckPlanner(doc_type_loader=loader)
        doc = _make_doc(classification_confidence=0.90)
        ctx = planner.build_context_for_document(doc, None)

        checks, *_ = planner.select_checks_for_context(ctx, playbook)
        ids = {c.id for c in checks}

        assert "global_for_SPA" in ids
        assert "doc_type_check" in ids
        assert "generic_fallback_check" not in ids

    def test_low_confidence_context_adds_generic_fallback(self):
        playbook = _FakePlaybook()
        loader = MagicMock()
        loader.load_checks_for_doc.return_value = [SimpleNamespace(id="doc_type_check")]

        planner = CheckPlanner(doc_type_loader=loader)
        doc = _make_doc(classification_confidence=0.42)  # low zone
        ctx = planner.build_context_for_document(doc, None)

        checks, *_ = planner.select_checks_for_context(ctx, playbook)
        ids = {c.id for c in checks}

        assert "global_for_SPA" in ids
        assert "doc_type_check" in ids
        assert "generic_fallback_check" in ids

    def test_explicit_confidence_zone_overrides_derived_value(self):
        planner = CheckPlanner()
        doc = _make_doc(
            classification_confidence=0.90,
            classification_confidence_zone="low",
        )

        ctx = planner.build_context_for_document(doc, None)

        assert ctx.classification_confidence_zone == "low"
        assert ctx.classification_requires_manual_review is True


        
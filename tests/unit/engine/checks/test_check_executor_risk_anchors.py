"""
B3.3 — CheckExecutor._collect_risk_anchors unit tests.

Проверяет:
- negative finding -> []
- empty evidence -> []
- exact span найден в одном из contexts
- нет совпадения в contexts, но есть fallback clause_uid/page -> clause_only/page_only
- все contexts пустые -> []
"""

from __future__ import annotations

from core.anchors.models import CheckAnchorMethod
from engine.checks.executor import CheckExecutor


def _collect(detection, contexts):
    return CheckExecutor._collect_risk_anchors(detection, contexts)


# ── guards ──────────────────────────────────────────────────────────────────


def test_returns_empty_for_negative_finding():
    detection = {"found": False, "evidence": "текст"}
    assert _collect(detection, []) == []


def test_returns_empty_for_empty_evidence():
    detection = {"found": True, "evidence": ""}
    assert _collect(detection, [{"text": "какой-то текст"}]) == []


def test_returns_empty_when_detection_not_dict():
    assert _collect(None, []) == []  # type: ignore[arg-type]


def test_returns_empty_when_contexts_empty():
    detection = {"found": True, "evidence": "цитата"}
    assert _collect(detection, []) == []


# ── exact span ──────────────────────────────────────────────────────────────


def test_collects_exact_span_from_contexts():
    detection = {
        "found": True,
        "evidence": "Стороны применяют право Российской Федерации.",
        "location": {"clause_uid": "main_contract:7.1", "page": 3},
    }
    contexts = [
        {"id": "chunk-1", "text": "Преамбула договора."},
        {
            "id": "chunk-2",
            "text": "7.1 Стороны применяют право Российской Федерации.",
        },
    ]
    anchors = _collect(detection, contexts)
    assert len(anchors) == 1
    assert anchors[0].anchor_method == CheckAnchorMethod.EXACT_SPAN
    assert anchors[0].quoted_text == "Стороны применяют право Российской Федерации."


# ── fallback clause_only / page_only ────────────────────────────────────────


def test_falls_back_to_clause_or_page_when_no_span_matches():
    detection = {
        "found": True,
        "evidence": "Эта цитата отсутствует в contexts дословно.",
        "location": {"clause_uid": "main_contract:99.9", "page": 42},
    }
    contexts = [{"id": "chunk-1", "text": "Какой-то совсем другой текст."}]
    anchors = _collect(detection, contexts)
    assert len(anchors) == 1
    assert anchors[0].anchor_method in (
        CheckAnchorMethod.CLAUSE_ONLY,
        CheckAnchorMethod.PAGE_ONLY,
    )


def test_returns_empty_when_no_fallback_and_no_span():
    detection = {
        "found": True,
        "evidence": "Цитата, которой нет ни в одном context.",
    }
    contexts = [{"id": "chunk-1", "text": "Совершенно нерелевантный текст."}]
    anchors = _collect(detection, contexts)
    assert anchors == []

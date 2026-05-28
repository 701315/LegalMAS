# src/services/structure/_heading_scoring/_logic.py

"""Логика вычисления бонусов и разрешения семантических типов."""

from __future__ import annotations
from typing import Any
from services.structure._models._constants import (
    SEMANTIC_ELEMENT_TYPE_SECTION_HEADING as SEMANTIC_TYPE_SECTION_HEADING,
    SEMANTIC_ELEMENT_TYPE_SUBSECTION_HEADING as SEMANTIC_TYPE_SUBSECTION_HEADING,
    SEMANTIC_ELEMENT_TYPE_DEFINITION_ITEM as SEMANTIC_TYPE_DEFINITION_ITEM,
    SEMANTIC_ELEMENT_TYPE_APPENDIX_HEADING as SEMANTIC_TYPE_APPENDIX_HEADING,
    SEMANTIC_ELEMENT_TYPE_SIGNATURE_BLOCK as SEMANTIC_TYPE_SIGNATURE_BLOCK,
    SEMANTIC_ELEMENT_TYPE_LIST_ITEM as SEMANTIC_TYPE_LIST_ITEM,
)
from services.structure.legal_heading_rules import (
    looks_like_definition_item, looks_like_appendix_heading,
    looks_like_signature_or_requisites_heading
)
from ._utils import _is_strict_numeric_uid, level_from_uid

def _resolve_semantic_type_in_scorer(
    *, uid: str, title: str, raw_text: str,
    element_type: str | None, classifier_semantic_type: str | None
) -> str:
    if classifier_semantic_type in {
        SEMANTIC_TYPE_DEFINITION_ITEM, SEMANTIC_TYPE_APPENDIX_HEADING,
        SEMANTIC_TYPE_SIGNATURE_BLOCK, SEMANTIC_TYPE_LIST_ITEM,
    }:
        return str(classifier_semantic_type)

    if looks_like_appendix_heading(raw_text) or looks_like_appendix_heading(title):
        return str(SEMANTIC_TYPE_APPENDIX_HEADING)
    if looks_like_definition_item(raw_text) or looks_like_definition_item(title):
        return str(SEMANTIC_TYPE_DEFINITION_ITEM)
    if looks_like_signature_or_requisites_heading(raw_text):
        return str(SEMANTIC_TYPE_SIGNATURE_BLOCK)

    if _is_strict_numeric_uid(uid):
        return str(SEMANTIC_TYPE_SECTION_HEADING) if level_from_uid(uid) == 1 else str(SEMANTIC_TYPE_SUBSECTION_HEADING)

    return str(classifier_semantic_type or SEMANTIC_TYPE_SECTION_HEADING)

def _compute_continuity_bonus(signals: dict[str, Any] | None) -> tuple[float, list[str]]:
    if not signals: return 0.0, []
    bonus, reasons = 0.0, []
    if signals.get("continuity_body_positive"):
        bonus += 0.03
        reasons.append("continuity_body_after_heading")
    if signals.get("continuity_heading_negative"):
        bonus -= 0.03
        reasons.append("continuity_next_is_heading")
    if signals.get("continuity_definition_negative"):
        bonus -= 0.04
        reasons.append("continuity_definition_negative")
    if signals.get("next_starts_with_lowercase"):
        bonus -= 0.02
        reasons.append("continuity_next_lowercase_start")
    if signals.get("next_has_substantive_verb"):
        bonus += 0.02
        reasons.append("continuity_next_has_substantive_verb")
    return round(max(-0.06, min(0.04, bonus)), 4), reasons

def _toc_match_bonus(toc_match: dict[str, Any] | None) -> tuple[float, str | None, list[str]]:
    if not toc_match: return 0.0, None, []
    m_type = str(toc_match.get("match_type") or "").strip() or None
    m_score = float(toc_match.get("match_score") or 0.0)
    if bool(toc_match.get("toc_missing_in_body")):
        return 0.0, m_type or "no_match", []
    if m_type == "exact": return 0.05, "exact", ["toc_exact_match"]
    if m_type == "fuzzy":
        if m_score >= 92: return 0.04, "fuzzy", ["toc_fuzzy_match_strong"]
        if m_score >= 87: return 0.03, "fuzzy", ["toc_fuzzy_match"]
        if m_score >= 82: return 0.02, "fuzzy", ["toc_fuzzy_match_weak"]
    return 0.0, m_type, []

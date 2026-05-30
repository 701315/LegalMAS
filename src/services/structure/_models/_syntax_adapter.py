# src/services/structure/_models/_syntax_adapter.py

"""
Адаптер: HeadingCandidateScored (legacy) → SyntaxHeadingCandidate (Phase 2).

Нужен для того чтобы Phase 3 FSM работал с новым контрактом
не ломая существующий scoring pipeline.

Будет удалён после полной миграции scoring на SyntaxHeadingCandidate.
"""

from __future__ import annotations

import re

from ._syntax import HierarchyTokenType, SyntaxHeadingCandidate

# Lazy import чтобы не создавать circular dependency
# HeadingCandidateScored находится в heading_candidates.py
_ROMAN_RE = re.compile(
    r"^(I{1,3}|IV|V?I{0,3}|IX|X{1,3}(?:IX|IV|V?I{0,3})?)$",
    re.IGNORECASE,
)
_ALPHA_RE = re.compile(r"^[A-Za-zА-Яа-яЁё]$")
_NUMERIC_RE = re.compile(r"^\d+(?:\.\d+)*$")
_KEYWORD_RE = re.compile(
    r"^(?:section|article|clause|annex|exhibit|schedule|appendix|sec\.?|art\.?)",
    re.IGNORECASE,
)


def _infer_token_type(raw_uid: str, raw_text: str) -> HierarchyTokenType:
    """
    Определить HierarchyTokenType по raw_uid и raw_text.
    Используется только адаптером — новый pipeline будет
    определять token_type напрямую в syntax detection.
    """
    uid = (raw_uid or "").strip()
    text = (raw_text or "").strip()

    if _KEYWORD_RE.match(text):
        return HierarchyTokenType.KEYWORD
    if _NUMERIC_RE.match(uid):
        return HierarchyTokenType.NUMERIC
    if _ROMAN_RE.match(uid):
        return HierarchyTokenType.ROMAN
    if _ALPHA_RE.match(uid):
        return HierarchyTokenType.ALPHA
    # bullet markers
    if uid in {"•", "–", "—", "-", "∙", "·", "*"}:
        return HierarchyTokenType.BULLET
    return HierarchyTokenType.UNKNOWN


def scored_to_syntax_candidate(scored: object) -> SyntaxHeadingCandidate:
    """
    Конвертировать HeadingCandidateScored → SyntaxHeadingCandidate.

    Принимает любой объект с нужными атрибутами (duck typing)
    чтобы не создавать hard import на heading_candidates.py.
    """
    raw = getattr(scored, "raw", scored)
    meta = getattr(scored, "metadata", {}) or {}

    element_index = int(getattr(raw, "element_index", 0))
    element_id = str(getattr(raw, "element_id", "") or "")
    raw_text = str(getattr(raw, "raw_text", "") or "")
    raw_uid = str(getattr(raw, "raw_uid", "") or "")
    title = str(getattr(raw, "title", "") or "")
    page = int(getattr(raw, "page", 1) or 1)
    scope = str(getattr(raw, "scope", "main_contract") or "main_contract")

    score = float(getattr(scored, "score", 0.0) or 0.0)
    score = max(0.0, min(1.0, score))

    token_type = _infer_token_type(raw_uid, raw_text)

    reasons: list[str] = []
    ar = getattr(scored, "accept_reasons", None) or meta.get("accept_reasons") or []
    rr = getattr(scored, "reject_reasons", None) or meta.get("reject_reasons") or []
    reasons.extend(f"accept:{r}" for r in ar)
    reasons.extend(f"reject:{r}" for r in rr)

    return SyntaxHeadingCandidate(
        element_index=element_index,
        element_id=element_id,
        raw_text=raw_text,
        raw_uid=raw_uid,
        title=title,
        page=page,
        token_type=token_type,
        heading_confidence=score,
        scope=scope,
        confidence_reasons=reasons,
        extra=dict(meta),
    )




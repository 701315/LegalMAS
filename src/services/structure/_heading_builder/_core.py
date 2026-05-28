# src/services/structure/_heading_builder/_core.py

"""Основной оркестратор сборкиHeadingCandidate."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from core.config import settings
from core.logging import get_logger
from services.structure.heading_llm_refiner import (
    ScoredHeadingCandidate,
    refine_ambiguous_candidates,
)
from services.structure.heading_patterns import normalize_spaces, parse_raw_heading
from services.structure.heading_scoring import score_heading_candidate
from services.structure.hierarchy_builder import HeadingCandidate
from services.structure.toc_match_utils import toc_match_payload

from ._constants import _MAX_HEADING_RAW_TEXT_LEN
from ._logic import (
    _element_scope,
    _is_candidate_element_type_allowed,
    _is_recoverable_toc_like_element_type,
    _is_strong_structural_element_type,
    _is_weak_structural_element_type,
    _require_element_structure_contract,
)
from ._ranking import _select_best_candidates_by_uid
from ._utils import (
    _is_strict_numeric_uid,
    _normalize_reject_reason,
    _normalize_scope,
    _patched_scored_candidate,
    _safe_int,
    _scope_aware_effective_uid,
    _status_to_decision,
    _uid_depth,
)

logger = get_logger(__name__)


def collect_scored_heading_candidates(
    elements: list[dict[str, Any]],
    *,
    document_id: str,
    toc_match_index: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> list[ScoredHeadingCandidate]:
    # Сначала строим контекст UID (соседние заголовки)
    parsed_by_scope = defaultdict(list)
    for i, el in enumerate(elements):
        try:
            txt = normalize_spaces(str(el.get("text") or ""))
            if not txt:
                continue
            p = parse_raw_heading(txt)
            if p and p[0]:
                parsed_by_scope[_element_scope(el)].append((i, normalize_spaces(str(p[0]))))
        except Exception:
            continue

    context_map = {}
    for scope, items in parsed_by_scope.items():
        items.sort(key=lambda x: x[0])
        for pos, (elem_i, r_uid) in enumerate(items):
            context_map[elem_i] = {
                "prev_heading_uid": items[pos - 1][1] if pos > 0 else None,
                "next_heading_uid": items[pos + 1][1] if pos + 1 < len(items) else None,
            }

    scored_candidates = []
    reject_stats = Counter()

    for elem_i, element in enumerate(elements):
        _require_element_structure_contract(element, elem_i, document_id)
        raw_text = normalize_spaces(str(element.get("text") or ""))
        if not raw_text or len(raw_text) > _MAX_HEADING_RAW_TEXT_LEN:
            continue

        el_type = normalize_spaces(str(element.get("element_type") or ""))
        if not _is_candidate_element_type_allowed(el_type):
            continue

        parsed = parse_raw_heading(raw_text)
        if not parsed or not parsed[0]:
            continue
        p_uid, p_title = normalize_spaces(str(parsed[0])), normalize_spaces(str(parsed[1]))

        el_meta = dict(element.get("metadata") or {})
        ctx = context_map.get(elem_i, {})
        t_match = toc_match_payload(p_uid, p_title, toc_match_index)

        res = score_heading_candidate(
            uid=p_uid,
            title=p_title,
            raw_text=raw_text,
            toc_match=t_match,
            element_type=el_type,
            semantic_element_type=el_meta.get("semantic_element_type"),
            continuity_signals=el_meta.get("continuity_signals"),
            prev_heading_uid=ctx.get("prev_heading_uid"),
            next_heading_uid=ctx.get("next_heading_uid"),
        )

        decision = _status_to_decision(res.status)
        reason = _normalize_reject_reason(res.primary_reason)
        score = float(res.score)

        # ── БЛОК ПРАВИЛ ТИПОВ (ВОССТАНОВЛЕНО ПОЛНОСТЬЮ) ──
        is_strong = _is_strong_structural_element_type(el_type)
        is_weak = _is_weak_structural_element_type(el_type)
        is_rec_toc = _is_recoverable_toc_like_element_type(el_type)

        if is_strong and decision == "ambiguous" and score >= 0.55:
            decision, reason = "accepted", "strong_structural_element_type"
        if is_weak and decision == "accepted" and score < 0.70:
            decision, reason = "ambiguous", "weak_structural_element_type_requires_stronger_score"

        if is_rec_toc:
            has_strong_t = (res.toc_match_type == "exact" and res.toc_match_score > 0) or (
                res.toc_match_type == "fuzzy" and res.toc_match_score >= 0.045
            )
            if decision == "accepted" and score < 0.85 and not has_strong_t:
                decision, reason = "ambiguous", "recoverable_toc_like_requires_stronger_evidence"
            if (
                decision == "ambiguous"
                and not el_meta.get("body_recoverable_from_toc")
                and el_meta.get("toc_guard_decision") == "reject_toc"
            ):
                decision, reason = "rejected", "recoverable_toc_like_rejected_by_toc_guard"

        if el_type == "list_item" and decision == "accepted":
            if not _is_strict_numeric_uid(p_uid):
                decision, reason = "rejected", "list_item_non_numeric_uid"
            elif _uid_depth(p_uid) > 4 and score < 0.85:
                decision, reason = "ambiguous", "list_item_deep_uid_requires_stronger_evidence"

        if el_type == "definition_item" and decision == "accepted":
            if not _is_strict_numeric_uid(p_uid):
                decision, reason = "rejected", "definition_item_non_numeric_uid"
            elif _uid_depth(p_uid) >= 3 and score < 0.90:
                decision, reason = (
                    "ambiguous",
                    "definition_item_requires_stronger_structural_evidence",
                )
            else:
                decision, reason = "ambiguous", "definition_item_prefer_non_section_interpretation"

        if el_type == "enumerated_clause" and decision == "accepted":
            if not _is_strict_numeric_uid(p_uid):
                decision, reason = "rejected", "enumerated_clause_non_numeric_uid"
            elif _uid_depth(p_uid) > 4 and score < 0.90:
                decision, reason = (
                    "ambiguous",
                    "enumerated_clause_deep_uid_requires_stronger_evidence",
                )

        # ── СБОР ПОЛНЫХ МЕТАДАННЫХ ──
        metadata = {
            "accept_reasons": list(res.accept_reasons),
            "reject_reasons": list(res.reject_reasons),
            "parsed_uid": p_uid,
            "raw_uid": p_uid,
            "effective_uid": _scope_aware_effective_uid(_element_scope(element), p_uid),
            "parsed_title": p_title,
            "normalized_title": p_title,
            "freeze_structural_fields": _is_strict_numeric_uid(p_uid),
            "scope": _element_scope(element),
            "segment_id": element.get("segment_id"),
            "segment_type": element.get("segment_type"),
            "segment_order": element.get("segment_order"),
            "element_type": el_type,
            "uid_depth": _uid_depth(p_uid),
            "page": element.get("page"),
            "toc_match": t_match,
            "toc_match_type": res.toc_match_type,
            "toc_match_score": float(res.toc_match_score),
            "semantic_element_type": res.semantic_element_type
            or el_meta.get("semantic_element_type"),
            "continuity_bonus": float(res.continuity_bonus),
            "legal_negative_signals": list(res.legal_negative_signals),
            "heading_confidence_from_classifier": float(el_meta.get("heading_confidence") or 0.0),
            "heading_reject_reasons_from_classifier": list(
                el_meta.get("heading_reject_reasons") or []
            ),
            "toc_guard_decision": str(el_meta.get("toc_guard_decision") or ""),
            "body_recoverable_from_toc": bool(el_meta.get("body_recoverable_from_toc")),
            "possible_toc": bool(el_meta.get("possible_toc")),
        }

        candidate = ScoredHeadingCandidate(
            elem_i=elem_i,
            page=_safe_int(element.get("page")),
            raw_text=raw_text,
            uid=p_uid,
            title=p_title,
            decision=decision,
            reason=reason,
            score=score,
            decision_source="rules",
            metadata=metadata,
            scope=_element_scope(element),
        )
        scored_candidates.append(candidate)
        if decision not in {"accepted", "ambiguous"}:
            reject_stats[reason] += 1

    return _select_best_candidates_by_uid(scored_candidates, document_id)


def filter_heading_sequence(
    candidates: list[HeadingCandidate], *, document_id: str
) -> list[HeadingCandidate]:
    """Дедупликация финального спискаHeadingCandidate."""
    if not candidates:
        return []
    filtered, seen = [], set()
    for cand in candidates:
        key = (str(cand.scope), str(cand.raw_uid))
        if key not in seen:
            seen.add(key)
            filtered.append(cand)
    return filtered


def build_heading_candidates(
    elements: list[dict[str, Any]],
    *,
    document_id: str,
    toc_match_index: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> list[HeadingCandidate]:
    """Верхнеуровневый процесс построения кандидатов с опциональным LLM-рефайнером."""
    scored = collect_scored_heading_candidates(
        elements, document_id=document_id, toc_match_index=toc_match_index
    )
    if not scored:
        return []

    if bool(getattr(settings, "STRUCTURE_ENABLE_HEADING_LLM_REFINER", False)):
        try:
            refined = refine_ambiguous_candidates(scored, elements, document_id)
            new_scored = []
            for c in refined:
                m = dict(c.metadata or {})
                m["raw_uid"] = normalize_spaces(str(m.get("raw_uid") or c.uid or ""))
                m["effective_uid"] = m.get("effective_uid") or _scope_aware_effective_uid(
                    _normalize_scope(c.scope), m["raw_uid"]
                )
                m["normalized_title"] = normalize_spaces(
                    str(m.get("normalized_title") or c.title or "")
                )
                new_scored.append(_patched_scored_candidate(c, metadata_updates=m))
            scored = new_scored
        except Exception:
            logger.exception(
                "STRUCTURE heading_llm_refiner_failed", extra={"document_id": document_id}
            )

    accepted: list[HeadingCandidate] = []
    for s in scored:
        if str(s.decision).lower() != "accepted":
            continue
        raw_uid = str((s.metadata or {}).get("raw_uid") or s.uid or "")
        if not raw_uid:
            continue
        meta = s.metadata or {}
        accepted.append(
            HeadingCandidate(
                elem_i=_safe_int(s.elem_i),
                uid=raw_uid,
                page=_safe_int(s.page),
                title=normalize_spaces(str(meta.get("normalized_title") or s.title or "")),
                scope=_normalize_scope(s.scope),
                raw_uid=raw_uid,
                effective_uid=str(meta.get("effective_uid") or ""),
                metadata=dict(meta),
            )
        )
    return filter_heading_sequence(accepted, document_id=document_id)

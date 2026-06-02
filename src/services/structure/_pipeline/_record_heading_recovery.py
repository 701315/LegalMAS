# src/services/structure/_pipeline/_record_heading_recovery.py

"""
Deterministic recovery for numbered record/list structures.

Purpose:
- rescue segments where ordinary heading detection found zero headings,
  but the body contains a strong numbered-record topology:
    N
    N.1
    N.2
    ...
- avoid early technical fallback for appendices / schedules / plain-text tables
  rendered as list items or body text.

Architecture:
- deterministic only;
- no LLM;
- conservative activation;
- modifies only element_type for selected lines and preserves original metadata.

Universal applicability:
- asset schedules
- property registers
- disclosure schedules
- payment schedules
- inventories
- technical specifications rendered as plain text
- any language, because logic depends on numeric topology, not lexical language
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from core.logging import get_logger
from services.structure.heading_patterns import normalize_spaces

logger = get_logger(__name__)

_NUMERIC_RECORD_LINE_RE = re.compile(
    r"^(?P<uid>\d{1,4}(?:\.\d{1,4}){0,5})[\.\)]?\s+(?P<title>\S.*)$"
)

_HARD_EXCLUDED_ELEMENT_TYPES = {
    "page_artifact",
    "signature_block",
    "requisites_block",
    "toc_content",
    "toc_header",
    "toc_line",
    "possible_toc",
    "unknown_layout",
}

_REFERENCE_LIKE_TITLE_PREFIXES = (
    "см.",
    "see ",
    "согласно ",
    "pursuant to ",
    "refer to ",
)

_MIN_TOTAL_RECORD_LINES = 4
_MIN_ROOTS_WITH_CHILDREN = 2
_MAX_RECORD_TITLE_CHARS = 280
_MAX_RECORD_TITLE_WORDS = 28


@dataclass(frozen=True, slots=True)
class RecordHeadingRecoveryResult:
    """
    Result of deterministic record-heading recovery.
    """

    applied: bool
    elements: list[dict[str, Any]]
    diagnostics: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _RecordLineCandidate:
    """
    Internal parsed numeric record line.
    """

    element_index: int
    uid: str
    root_uid: str
    depth: int
    title: str
    element_type: str
    has_field_separator: bool


def _safe_element_type(element: dict[str, Any]) -> str:
    return str(element.get("element_type") or "").strip().lower()


def _looks_record_like_title(title: str) -> bool:
    """
    Conservative filter for numeric record titles.

    Rejects:
    - empty / punctuation-only tails
    - very long prose paragraphs
    - obvious reference-like lines

    Accepts compact field/value-like and short descriptive titles.
    """
    normalized = normalize_spaces(title)
    if not normalized:
        return False

    if len(normalized) > _MAX_RECORD_TITLE_CHARS:
        return False

    words = normalized.split()
    if len(words) > _MAX_RECORD_TITLE_WORDS:
        return False

    if not any(ch.isalpha() for ch in normalized):
        return False

    if normalized[:1] in {".", ",", ";", ":"}:
        return False

    lower = normalized.lower()
    if lower.startswith(_REFERENCE_LIKE_TITLE_PREFIXES):
        return False

    return True


def _extract_record_line_candidate(
    *,
    element_index: int,
    element: dict[str, Any],
) -> _RecordLineCandidate | None:
    """
    Parse numeric record candidate from an element.
    """
    element_type = _safe_element_type(element)
    if element_type in _HARD_EXCLUDED_ELEMENT_TYPES:
        return None

    text = normalize_spaces(str(element.get("text") or ""))
    if not text:
        return None

    match = _NUMERIC_RECORD_LINE_RE.match(text)
    if not match:
        return None

    uid = normalize_spaces(str(match.group("uid") or ""))
    title = normalize_spaces(str(match.group("title") or ""))

    if not uid or not title:
        return None

    if not _looks_record_like_title(title):
        return None

    root_uid = uid.split(".", 1)[0]
    depth = uid.count(".") + 1
    has_field_separator = ":" in title

    return _RecordLineCandidate(
        element_index=element_index,
        uid=uid,
        root_uid=root_uid,
        depth=depth,
        title=title,
        element_type=element_type,
        has_field_separator=has_field_separator,
    )


def _roots_are_monotonic(candidates: list[_RecordLineCandidate]) -> bool:
    """
    Ensure root ids progress monotonically by first appearance.

    This is a conservative guard against random numeric noise.
    """
    first_position_by_root: dict[str, int] = {}
    for candidate in candidates:
        first_position_by_root.setdefault(candidate.root_uid, candidate.element_index)

    ordered_roots = [
        root
        for root, _ in sorted(first_position_by_root.items(), key=lambda item: item[1])
    ]

    try:
        ordered_ints = [int(root) for root in ordered_roots]
    except Exception:
        return False

    return ordered_ints == sorted(ordered_ints)


def _build_recovery_diagnostics(
    *,
    attempted: bool,
    applied: bool,
    reason: str,
    candidates: list[_RecordLineCandidate],
    selected_indices: set[int],
) -> dict[str, Any]:
    """
    Build structured diagnostics for audit/debug.
    """
    root_count = len({c.root_uid for c in candidates if c.depth == 1})
    child_count = len([c for c in candidates if c.depth > 1])
    roots_with_children = len(
        {
            c.root_uid
            for c in candidates
            if c.depth > 1
        }
    )

    type_counts = Counter(c.element_type for c in candidates)

    return {
        "attempted": attempted,
        "applied": applied,
        "mode": "numbered_record",
        "reason": reason,
        "matched_record_lines": len(candidates),
        "selected_record_lines": len(selected_indices),
        "root_count": root_count,
        "child_count": child_count,
        "roots_with_children": roots_with_children,
        "field_separator_count": len([c for c in candidates if c.has_field_separator]),
        "candidate_element_types": dict(type_counts),
        "selected_indices_preview": sorted(selected_indices)[:20],
    }


def attempt_record_heading_recovery(
    *,
    document_id: str,
    elements: list[dict[str, Any]],
) -> RecordHeadingRecoveryResult:
    """
    Attempt deterministic recovery of numbered-record structure.

    Activation criteria are conservative:
    - at least `_MIN_TOTAL_RECORD_LINES` numeric record lines
    - at least `_MIN_ROOTS_WITH_CHILDREN` distinct root records
    - each selected root has both:
      * a root line (e.g. "17 ...")
      * at least one child line (e.g. "17.1 ...")
    - root ids progress monotonically by appearance

    If applied:
    - promotes selected elements to element_type="heading_candidate"
    - preserves original element type in metadata
    """
    if not elements:
        return RecordHeadingRecoveryResult(
            applied=False,
            elements=elements,
            diagnostics=_build_recovery_diagnostics(
                attempted=True,
                applied=False,
                reason="empty_elements",
                candidates=[],
                selected_indices=set(),
            ),
        )

    candidates: list[_RecordLineCandidate] = []
    for index, element in enumerate(elements):
        candidate = _extract_record_line_candidate(
            element_index=index,
            element=element,
        )
        if candidate is not None:
            candidates.append(candidate)

    if len(candidates) < _MIN_TOTAL_RECORD_LINES:
        return RecordHeadingRecoveryResult(
            applied=False,
            elements=elements,
            diagnostics=_build_recovery_diagnostics(
                attempted=True,
                applied=False,
                reason="insufficient_numeric_record_lines",
                candidates=candidates,
                selected_indices=set(),
            ),
        )

    if not _roots_are_monotonic(candidates):
        return RecordHeadingRecoveryResult(
            applied=False,
            elements=elements,
            diagnostics=_build_recovery_diagnostics(
                attempted=True,
                applied=False,
                reason="non_monotonic_root_progression",
                candidates=candidates,
                selected_indices=set(),
            ),
        )

    root_line_by_root: dict[str, _RecordLineCandidate] = {}
    child_lines_by_root: dict[str, list[_RecordLineCandidate]] = defaultdict(list)

    for candidate in candidates:
        if candidate.depth == 1:
            root_line_by_root.setdefault(candidate.root_uid, candidate)
        else:
            child_lines_by_root[candidate.root_uid].append(candidate)

    eligible_roots = [
        root_uid
        for root_uid in sorted(root_line_by_root.keys(), key=lambda value: int(value))
        if child_lines_by_root.get(root_uid)
    ]

    if len(eligible_roots) < _MIN_ROOTS_WITH_CHILDREN:
        return RecordHeadingRecoveryResult(
            applied=False,
            elements=elements,
            diagnostics=_build_recovery_diagnostics(
                attempted=True,
                applied=False,
                reason="insufficient_roots_with_children",
                candidates=candidates,
                selected_indices=set(),
            ),
        )

    selected_indices: set[int] = set()
    for root_uid in eligible_roots:
        selected_indices.add(root_line_by_root[root_uid].element_index)
        selected_indices.update(
            child.element_index for child in child_lines_by_root[root_uid]
        )

    if len(selected_indices) < _MIN_TOTAL_RECORD_LINES:
        return RecordHeadingRecoveryResult(
            applied=False,
            elements=elements,
            diagnostics=_build_recovery_diagnostics(
                attempted=True,
                applied=False,
                reason="selected_topology_too_small",
                candidates=candidates,
                selected_indices=selected_indices,
            ),
        )

    recovered_elements = list(elements)
    promoted_count = 0

    for candidate in candidates:
        if candidate.element_index not in selected_indices:
            continue

        original = recovered_elements[candidate.element_index]
        cloned = dict(original)
        metadata = dict(cloned.get("metadata") or {})

        original_type = _safe_element_type(original)
        metadata["record_heading_recovery"] = True
        metadata["record_heading_recovery_uid"] = candidate.uid
        metadata["record_heading_recovery_root_uid"] = candidate.root_uid
        metadata["record_heading_recovery_depth"] = candidate.depth
        metadata["record_heading_recovery_original_element_type"] = original_type
        metadata["record_heading_recovery_mode"] = "numbered_record"

        cloned["metadata"] = metadata
        cloned["element_type"] = "heading_candidate"
        recovered_elements[candidate.element_index] = cloned
        promoted_count += 1

    diagnostics = _build_recovery_diagnostics(
        attempted=True,
        applied=True,
        reason="numbered_record_topology_detected",
        candidates=candidates,
        selected_indices=selected_indices,
    )
    diagnostics["promoted_count"] = promoted_count

    logger.info(
        "STRUCTURE record_heading_recovery_applied",
        extra={
            "document_id": document_id,
            "matched_record_lines": diagnostics["matched_record_lines"],
            "selected_record_lines": diagnostics["selected_record_lines"],
            "root_count": diagnostics["root_count"],
            "child_count": diagnostics["child_count"],
        },
    )

    return RecordHeadingRecoveryResult(
        applied=True,
        elements=recovered_elements,
        diagnostics=diagnostics,
    )



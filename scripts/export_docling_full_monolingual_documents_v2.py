#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


DEFAULT_INPUT = (
    "/srv/steloom-dev/artifacts/docling_inspection_v2/"
    "canonical_document.json"
)
DEFAULT_OUTPUT = (
    "/srv/steloom-dev/artifacts/docling_full_monolingual_export_v2"
)

CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
LATIN_RE = re.compile(r"[A-Za-z]")
SPACE_RE = re.compile(r"\s+")
NUMERIC_ANCHOR_RE = re.compile(r"^\d+(?:\.\d+)*$")
LEADING_ANCHOR_RE = re.compile(
    r"^\s*(?P<anchor>\d+(?:\.\d+)*)(?:[.)])?(?=\s|$)"
)

TITLE_RE = re.compile(
    r"(?:SALE AND PURCHASE AGREEMENT|ДОГОВОР КУПЛИ)",
    re.IGNORECASE,
)
TOC_RE = re.compile(
    r"(?:TABLE OF CONTENTS|CONTENTS|СОДЕРЖАНИЕ)",
    re.IGNORECASE,
)
APPENDIX_RE = re.compile(
    r"(?:APPENDIX|ANNEX|EXHIBIT|SCHEDULE|ПРИЛОЖЕНИЕ)",
    re.IGNORECASE,
)
SIGNATURE_RE = re.compile(
    r"(?:ON BEHALF OF|ОТ ИМЕНИ|SIGNATURE|ПОДПИС)",
    re.IGNORECASE,
)
DATE_RE = re.compile(
    r"(?:\bDATED\b|\bДАТИРОВАН|\bОТ\b)",
    re.IGNORECASE,
)

MAIN_SECTION_ANCHORS = {str(i) for i in range(1, 9)}

# Границы подтверждены layout diagnostic и inspection report.
# p.1–11: основной договор; p.12–15: приложение 1;
# p.16–17: приложение 2; p.18–20: приложение 3.
SCOPE_RANGES = (
    ("main_contract", 1, 11),
    ("appendix_1", 12, 15),
    ("appendix_2", 16, 17),
    ("appendix_3", 18, 20),
)


def normalize(value: Any) -> str:
    return SPACE_RE.sub(" ", str(value or "")).strip()


def text_language(text: str) -> str:
    has_ru = bool(CYRILLIC_RE.search(text))
    has_en = bool(LATIN_RE.search(text))
    if has_ru and not has_en:
        return "ru"
    if has_en and not has_ru:
        return "en"
    if has_ru and has_en:
        return "mixed"
    return "shared"


def numeric_anchor(value: Any) -> str | None:
    value = normalize(value).rstrip(".)")
    return value if NUMERIC_ANCHOR_RE.fullmatch(value) else None


def extract_anchor(atom: dict[str, Any]) -> str | None:
    anchor = numeric_anchor(atom.get("marker"))
    if anchor:
        return anchor

    match = LEADING_ANCHOR_RE.match(normalize(atom.get("text")))
    if match:
        return match.group("anchor")

    return None


def anchor_depth(anchor: str | None) -> int:
    return len(anchor.split(".")) if anchor else 0


def get_bbox(atom: dict[str, Any]) -> tuple[float, float, float, float] | None:
    value = atom.get("bbox")
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        return tuple(float(item) for item in value)
    except (TypeError, ValueError):
        return None


def y_center(atom: dict[str, Any]) -> float | None:
    value = get_bbox(atom)
    return (value[1] + value[3]) / 2 if value else None


def x_center(atom: dict[str, Any]) -> float | None:
    value = get_bbox(atom)
    return (value[0] + value[2]) / 2 if value else None


def is_footer(atom: dict[str, Any]) -> bool:
    return bool(atom.get("is_furniture")) or atom.get("label") == "page_footer"


def has_real_text(atom: dict[str, Any]) -> bool:
    text = normalize(atom.get("text"))
    return bool(text) and not is_footer(atom)


def is_marker_only(atom: dict[str, Any]) -> bool:
    text = normalize(atom.get("text"))
    anchor = extract_anchor(atom)

    if atom.get("is_attached_marker_only"):
        return True

    if not anchor:
        return False

    stripped = text.rstrip(".)").strip()
    return stripped == anchor or len(text) <= len(anchor) + 2


def scope_for_page(page: int) -> str:
    for scope_id, first_page, last_page in SCOPE_RANGES:
        if first_page <= page <= last_page:
            return scope_id
    return "unknown"


def sort_atoms(atoms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(atom: dict[str, Any]) -> tuple[float, ...]:
        bbox = get_bbox(atom) or (0.0, 0.0, 0.0, 0.0)
        return (
            float(atom.get("page") or 0),
            bbox[1],
            bbox[0],
            float(atom.get("reading_order") or 0),
        )

    return sorted(atoms, key=key)


def split_mixed(text: str) -> dict[str, str | None]:
    """
    Safely handles known inline bilingual patterns:
      EN / RU
      EN + Russian sentence beginning at obvious Cyrillic boundary
    """
    text = normalize(text)
    if not text:
        return {"ru": None, "en": None}

    if " / " in text:
        left, right = [normalize(part) for part in text.split(" / ", 1)]
        left_language = text_language(left)
        right_language = text_language(right)

        if left_language == "en" and right_language == "ru":
            return {"en": left, "ru": right}
        if left_language == "ru" and right_language == "en":
            return {"en": right, "ru": left}

    ru_match = CYRILLIC_RE.search(text)
    if ru_match:
        left = normalize(text[:ru_match.start()])
        right = normalize(text[ru_match.start():])
        if len(left) >= 4 and len(right) >= 4 and text_language(left) == "en":
            return {"en": left, "ru": right}

    return {"ru": None, "en": None}


def materialize(atom: dict[str, Any], language: str) -> tuple[
    str | None, str, float, bool, str | None
]:
    text = normalize(atom.get("text"))
    atom_language = atom.get("language") or text_language(text)

    if atom_language == language:
        return text, "native_atom", 0.99, False, None

    if atom_language == "shared":
        return text, "shared_atom", 0.97, False, None

    if atom_language == "mixed":
        variant = split_mixed(text).get(language)
        if variant:
            return variant, "split_mixed_atom", 0.85, False, None
        return None, "unresolved_mixed_atom", 0.0, True, (
            "mixed_atom_could_not_be_safely_split"
        )

    return None, "opposite_language_atom", 0.0, False, None


def is_toc_atom(atom: dict[str, Any]) -> bool:
    page = int(atom.get("page") or 0)
    return page == 2 or bool(TOC_RE.search(normalize(atom.get("text"))))


def is_signature_atom(atom: dict[str, Any]) -> bool:
    text = normalize(atom.get("text"))
    page = int(atom.get("page") or 0)

    return bool(SIGNATURE_RE.search(text)) or page in {11, 15, 17, 20} and (
        atom.get("label") in {"text", "section_header", "list_item"}
        and (
            "seller" in text.lower()
            or "buyer" in text.lower()
            or "продавц" in text.lower()
            or "покупател" in text.lower()
        )
    )


def is_heading_like(atom: dict[str, Any]) -> bool:
    text = normalize(atom.get("text"))
    if atom.get("label") == "section_header":
        return True

    anchor = extract_anchor(atom)
    letters = re.sub(r"[^A-Za-zА-Яа-яЁё]", "", text)

    if anchor and anchor_depth(anchor) == 1 and len(text) < 180:
        return True

    if len(letters) >= 5:
        uppercase = sum(char.isupper() for char in letters)
        return uppercase / len(letters) >= 0.65

    return False


def is_content_candidate(atom: dict[str, Any], language: str) -> bool:
    if not has_real_text(atom) or is_marker_only(atom):
        return False
    if is_toc_atom(atom):
        return False

    atom_language = atom.get("language") or text_language(normalize(atom.get("text")))
    return atom_language in {language, "mixed", "shared"}


def clean_clause_text(text: str, anchor: str) -> str:
    text = normalize(text)

    # Remove duplicated trailing marker often produced by Docling:
    # "Some content. 3.4" -> "Some content."
    text = re.sub(
        rf"\s+{re.escape(anchor)}[.)]?\s*$",
        "",
        text,
    )

    # Remove leading anchor only if it is physically included in content atom.
    text = re.sub(
        rf"^\s*{re.escape(anchor)}[.)]?\s*",
        "",
        text,
    )

    return normalize(text)


def score_variant(
    marker_atom: dict[str, Any],
    candidate: dict[str, Any],
    target_language: str,
    scope_id: str,
) -> float:
    if scope_for_page(int(candidate.get("page") or 0)) != scope_id:
        return -999.0

    text, _, _, _, _ = materialize(candidate, target_language)
    if not text:
        return -999.0

    score = 0.0
    marker_page = int(marker_atom.get("page") or 0)
    candidate_page = int(candidate.get("page") or 0)

    if marker_page == candidate_page:
        score += 5.0
    elif abs(marker_page - candidate_page) == 1:
        score += 0.5
    else:
        return -999.0

    marker_y = y_center(marker_atom)
    candidate_y = y_center(candidate)
    if marker_y is not None and candidate_y is not None:
        distance = abs(marker_y - candidate_y)
        if distance <= 4:
            score += 10.0
        elif distance <= 10:
            score += 8.0
        elif distance <= 20:
            score += 5.0
        elif distance <= 35:
            score += 2.0
        else:
            score -= min(8.0, distance / 20)

    marker_x = x_center(marker_atom)
    candidate_x = x_center(candidate)
    if marker_x is not None and candidate_x is not None:
        # In this PDF marker column is near the center; target content
        # should be horizontally separated but share the same Y row.
        horizontal_distance = abs(marker_x - candidate_x)
        if 10 <= horizontal_distance <= 280:
            score += 1.0

    if marker_atom.get("parent_ref") == candidate.get("parent_ref"):
        score += 1.0

    marker_order = int(marker_atom.get("reading_order") or 0)
    candidate_order = int(candidate.get("reading_order") or 0)
    order_distance = abs(marker_order - candidate_order)
    if order_distance <= 6:
        score += 1.0
    elif order_distance <= 15:
        score += 0.3

    candidate_anchor = extract_anchor(candidate)
    marker_anchor = extract_anchor(marker_atom)
    if candidate_anchor == marker_anchor:
        score += 2.0

    if is_heading_like(candidate) and anchor_depth(marker_anchor) > 1:
        score -= 3.0

    return score


def master_anchor_inventory(
    atoms: list[dict[str, Any]],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    inventory: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for atom in atoms:
        if not has_real_text(atom) or is_toc_atom(atom):
            continue

        anchor = extract_anchor(atom)
        if not anchor:
            continue

        page = int(atom.get("page") or 0)
        scope_id = scope_for_page(page)

        # Never treat numeric page footers as logical anchors.
        if is_footer(atom):
            continue

        inventory[scope_id][anchor].append(atom)

    return inventory


def select_variant(
    anchor: str,
    witnesses: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    language: str,
    scope_id: str,
) -> dict[str, Any]:
    """
    Prefer a native same-anchor content atom. Otherwise pair a marker witness
    with nearest target-language content atom in the same visual row.
    """
    native: list[dict[str, Any]] = []

    for atom in witnesses:
        if is_marker_only(atom):
            continue
        text, method, confidence, needs_review, reason = materialize(atom, language)
        if text and len(clean_clause_text(text, anchor)) > 2:
            native.append(
                {
                    "atom": atom,
                    "text": clean_clause_text(text, anchor),
                    "method": method,
                    "confidence": confidence,
                    "needs_review": needs_review,
                    "reason": reason,
                    "score": 100.0,
                }
            )

    if native:
        best = max(
            native,
            key=lambda item: (
                len(item["text"]),
                item["confidence"],
                -int(item["atom"].get("reading_order") or 0),
            ),
        )
        return best

    scored: list[dict[str, Any]] = []

    for witness in witnesses:
        for candidate in candidates:
            score = score_variant(witness, candidate, language, scope_id)
            if score < 7.0:
                continue

            text, method, confidence, needs_review, reason = materialize(
                candidate,
                language,
            )
            if not text:
                continue

            clean_text = clean_clause_text(text, anchor)
            if len(clean_text) <= 2:
                continue

            scored.append(
                {
                    "atom": candidate,
                    "text": clean_text,
                    "method": "geometry_paired_" + method,
                    "confidence": min(0.94, score / 16.0),
                    "needs_review": needs_review or score < 10.0,
                    "reason": (
                        reason
                        or (
                            "low_geometry_pairing_confidence"
                            if score < 10.0
                            else None
                        )
                    ),
                    "score": score,
                    "marker_atom": witness,
                }
            )

    if scored:
        return max(
            scored,
            key=lambda item: (
                item["score"],
                len(item["text"]),
                -int(item["atom"].get("reading_order") or 0),
            ),
        )

    return {
        "atom": None,
        "text": None,
        "method": "unresolved_anchor",
        "confidence": 0.0,
        "needs_review": True,
        "reason": "no_target_language_variant_found_for_master_anchor",
        "score": 0.0,
    }


def find_section_heading(
    section_anchor: str,
    atoms: list[dict[str, Any]],
    language: str,
) -> dict[str, Any]:
    candidates: list[tuple[float, dict[str, Any], str, str, float]] = []

    for atom in atoms:
        if not has_real_text(atom) or is_toc_atom(atom):
            continue

        page = int(atom.get("page") or 0)
        if scope_for_page(page) != "main_contract":
            continue

        anchor = extract_anchor(atom)
        if anchor != section_anchor:
            continue

        text, method, confidence, _, _ = materialize(atom, language)
        if not text:
            continue

        if not is_heading_like(atom):
            continue

        score = 1.0
        if atom.get("label") == "section_header":
            score += 3.0
        if len(text) > 4:
            score += 1.0

        candidates.append((score, atom, text, method, confidence))

    if candidates:
        _, atom, text, method, confidence = max(candidates, key=lambda item: item[0])
        clean = clean_clause_text(text, section_anchor)
        if not clean:
            clean = (
                "[ЗАГОЛОВОК РАЗДЕЛА ТРЕБУЕТ ПРОВЕРКИ]"
                if language == "ru"
                else "[SECTION TITLE REQUIRES REVIEW]"
            )
            return {
                "atom": atom,
                "text": f"{section_anchor}. {clean}",
                "method": method,
                "confidence": 0.30,
                "needs_review": True,
                "reason": "heading_text_empty_after_anchor_cleanup",
            }

        return {
            "atom": atom,
            "text": f"{section_anchor}. {clean}",
            "method": method,
            "confidence": confidence,
            "needs_review": False,
            "reason": None,
        }

    placeholder = (
        "[ЗАГОЛОВОК РАЗДЕЛА ТРЕБУЕТ ПРОВЕРКИ]"
        if language == "ru"
        else "[SECTION TITLE REQUIRES REVIEW]"
    )
    return {
        "atom": None,
        "text": f"{section_anchor}. {placeholder}",
        "method": "synthetic_section_heading",
        "confidence": 0.0,
        "needs_review": True,
        "reason": "section_inferred_from_child_anchors",
    }


def page_min_for_anchor(witnesses: list[dict[str, Any]]) -> int:
    return min(int(item.get("page") or 9999) for item in witnesses)


def anchor_sort_key(anchor: str) -> tuple[int, ...]:
    return tuple(int(part) for part in anchor.split("."))


def build_main_contract(
    inventory: dict[str, dict[str, list[dict[str, Any]]]],
    atoms: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    language: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    scope_id = "main_contract"
    elements: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    anchors = inventory.get(scope_id, {})
    main_clause_anchors = [
        anchor
        for anchor in anchors
        if (
            anchor_depth(anchor) >= 2
            or anchor in MAIN_SECTION_ANCHORS
        )
    ]

    required_sections = sorted(
        {
            anchor.split(".", 1)[0]
            for anchor in main_clause_anchors
            if "." in anchor and anchor.split(".", 1)[0] in MAIN_SECTION_ANCHORS
        }
        | {
            anchor
            for anchor in main_clause_anchors
            if anchor in MAIN_SECTION_ANCHORS
        },
        key=int,
    )

    children_by_section: dict[str, list[str]] = defaultdict(list)
    for anchor in main_clause_anchors:
        if "." in anchor and anchor.split(".", 1)[0] in MAIN_SECTION_ANCHORS:
            children_by_section[anchor.split(".", 1)[0]].append(anchor)

    for section_anchor in required_sections:
        heading = find_section_heading(section_anchor, atoms, language)
        heading_atom = heading["atom"]
        child_anchors = sorted(
            children_by_section.get(section_anchor, []),
            key=anchor_sort_key,
        )

        page = (
            int(heading_atom.get("page") or 0)
            if heading_atom
            else (
                page_min_for_anchor(anchors[child_anchors[0]])
                if child_anchors
                else 0
            )
        )

        elements.append(
            {
                "type": "section_heading",
                "scope_id": scope_id,
                "anchor_uid": section_anchor,
                "text": heading["text"],
                "page_start": page,
                "page_end": page,
                "source_element_ids": (
                    [heading_atom["element_id"]] if heading_atom else []
                ),
                "projection_method": heading["method"],
                "projection_confidence": round(heading["confidence"], 3),
                "needs_review": heading["needs_review"],
                "review_reason": heading["reason"],
            }
        )

        for anchor in child_anchors:
            selected = select_variant(
                anchor=anchor,
                witnesses=anchors[anchor],
                candidates=candidates,
                language=language,
                scope_id=scope_id,
            )

            page = (
                int(selected["atom"].get("page") or 0)
                if selected["atom"]
                else page_min_for_anchor(anchors[anchor])
            )

            if not selected["text"]:
                text = (
                    f"{anchor}. [ТЕКСТ ПУНКТА ТРЕБУЕТ ПРОВЕРКИ]"
                    if language == "ru"
                    else f"{anchor}. [CLAUSE TEXT REQUIRES REVIEW]"
                )
                unresolved.append(
                    {
                        "scope_id": scope_id,
                        "anchor_uid": anchor,
                        "reason": selected["reason"],
                        "witness_ids": [
                            atom["element_id"] for atom in anchors[anchor]
                        ],
                    }
                )
            else:
                text = f"{anchor}. {selected['text']}"

            source_ids = [atom["element_id"] for atom in anchors[anchor]]
            if selected["atom"]:
                source_ids.append(selected["atom"]["element_id"])

            elements.append(
                {
                    "type": "clause",
                    "scope_id": scope_id,
                    "anchor_uid": anchor,
                    "text": text,
                    "page_start": page,
                    "page_end": page,
                    "source_element_ids": list(dict.fromkeys(source_ids)),
                    "projection_method": selected["method"],
                    "projection_confidence": round(selected["confidence"], 3),
                    "needs_review": selected["needs_review"],
                    "review_reason": selected["reason"],
                }
            )

    return elements, unresolved


def build_appendices(
    inventory: dict[str, dict[str, list[dict[str, Any]]]],
    atoms: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    language: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    elements: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    for appendix_number in ("1", "2", "3"):
        scope_id = f"appendix_{appendix_number}"
        scope_atoms = [
            atom
            for atom in atoms
            if scope_for_page(int(atom.get("page") or 0)) == scope_id
            and has_real_text(atom)
            and not is_toc_atom(atom)
        ]

        heading_candidates = [
            atom
            for atom in scope_atoms
            if APPENDIX_RE.search(normalize(atom.get("text")))
            or (
                atom.get("label") == "section_header"
                and int(atom.get("page") or 0) == {
                    "appendix_1": 12,
                    "appendix_2": 16,
                    "appendix_3": 18,
                }[scope_id]
            )
        ]

        heading_text = None
        heading_atom = None
        heading_method = "synthetic_appendix_heading"
        heading_confidence = 0.0
        heading_review = True

        for atom in heading_candidates:
            candidate_text, method, confidence, _, _ = materialize(atom, language)
            if candidate_text:
                heading_text = candidate_text
                heading_atom = atom
                heading_method = method
                heading_confidence = confidence
                heading_review = False
                break

        if not heading_text:
            heading_text = (
                f"ПРИЛОЖЕНИЕ № {appendix_number}"
                if language == "ru"
                else f"APPENDIX NO. {appendix_number}"
            )

        elements.append(
            {
                "type": "appendix_heading",
                "scope_id": scope_id,
                "anchor_uid": None,
                "text": heading_text,
                "page_start": {
                    "appendix_1": 12,
                    "appendix_2": 16,
                    "appendix_3": 18,
                }[scope_id],
                "page_end": {
                    "appendix_1": 15,
                    "appendix_2": 17,
                    "appendix_3": 20,
                }[scope_id],
                "source_element_ids": (
                    [heading_atom["element_id"]] if heading_atom else []
                ),
                "projection_method": heading_method,
                "projection_confidence": round(heading_confidence, 3),
                "needs_review": heading_review,
                "review_reason": (
                    "appendix_heading_not_recovered"
                    if heading_review
                    else None
                ),
            }
        )

        anchors = inventory.get(scope_id, {})

        for anchor in sorted(anchors, key=anchor_sort_key):
            witnesses = anchors[anchor]

            # Do not make a logical appendix item out of a page number/footer.
            if all(is_footer(atom) for atom in witnesses):
                continue

            selected = select_variant(
                anchor=anchor,
                witnesses=witnesses,
                candidates=candidates,
                language=language,
                scope_id=scope_id,
            )

            page = (
                int(selected["atom"].get("page") or 0)
                if selected["atom"]
                else page_min_for_anchor(witnesses)
            )

            if selected["text"]:
                text = f"{anchor}. {selected['text']}"
            else:
                text = (
                    f"{anchor}. [ТЕКСТ ПУНКТА ПРИЛОЖЕНИЯ ТРЕБУЕТ ПРОВЕРКИ]"
                    if language == "ru"
                    else f"{anchor}. [APPENDIX ITEM TEXT REQUIRES REVIEW]"
                )
                unresolved.append(
                    {
                        "scope_id": scope_id,
                        "anchor_uid": anchor,
                        "reason": selected["reason"],
                        "witness_ids": [
                            atom["element_id"] for atom in witnesses
                        ],
                    }
                )

            source_ids = [atom["element_id"] for atom in witnesses]
            if selected["atom"]:
                source_ids.append(selected["atom"]["element_id"])

            elements.append(
                {
                    "type": "appendix_item",
                    "scope_id": scope_id,
                    "anchor_uid": anchor,
                    "logical_id": f"{scope_id}:{anchor}",
                    "text": text,
                    "page_start": page,
                    "page_end": page,
                    "source_element_ids": list(dict.fromkeys(source_ids)),
                    "projection_method": selected["method"],
                    "projection_confidence": round(selected["confidence"], 3),
                    "needs_review": selected["needs_review"],
                    "review_reason": selected["reason"],
                }
            )

    return elements, unresolved


def build_unanchored_blocks(
    atoms: list[dict[str, Any]],
    language: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Keep title, preamble, signatures and non-numbered appendix text.
    Clauses are created separately from master anchors, so marker-only atoms
    and clearly numbered content are excluded here.
    """
    elements: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    for atom in sort_atoms(atoms):
        if not has_real_text(atom):
            continue
        if is_toc_atom(atom):
            continue
        if is_marker_only(atom):
            continue

        page = int(atom.get("page") or 0)
        scope_id = scope_for_page(page)
        anchor = extract_anchor(atom)

        # All numbered units are created by inventory logic, avoiding duplicate
        # body clauses and appendix rows here.
        if anchor:
            continue

        text, method, confidence, needs_review, reason = materialize(atom, language)

        if text is None:
            if is_signature_atom(atom) or page == 1:
                unresolved.append(
                    {
                        "scope_id": scope_id,
                        "source_element_id": atom["element_id"],
                        "page": page,
                        "text": normalize(atom.get("text")),
                        "reason": reason,
                    }
                )
            continue

        if page == 1 and TITLE_RE.search(text):
            element_type = "document_title"
        elif page == 1 and DATE_RE.search(text):
            element_type = "document_date"
        elif page == 1:
            element_type = "preamble"
        elif is_signature_atom(atom):
            element_type = "signature_block"
        elif scope_id.startswith("appendix_"):
            element_type = "appendix_text"
        elif page == 10 or page == 11:
            element_type = "party_details"
        elif is_heading_like(atom):
            element_type = "heading"
        else:
            element_type = "paragraph"

        elements.append(
            {
                "type": element_type,
                "scope_id": scope_id,
                "anchor_uid": None,
                "text": text,
                "page_start": page,
                "page_end": page,
                "source_element_ids": [atom["element_id"]],
                "projection_method": method,
                "projection_confidence": round(confidence, 3),
                "needs_review": needs_review,
                "review_reason": reason,
                "reading_order": atom.get("reading_order"),
                "_y": (get_bbox(atom) or (0, 0, 0, 0))[1],
                "_x": (get_bbox(atom) or (0, 0, 0, 0))[0],
            }
        )

    return elements, unresolved


def final_sort_key(element: dict[str, Any]) -> tuple[float, float, float, int]:
    type_priority = {
        "document_title": 0,
        "document_date": 1,
        "preamble": 2,
        "section_heading": 3,
        "heading": 4,
        "clause": 5,
        "party_details": 6,
        "signature_block": 7,
        "appendix_heading": 8,
        "appendix_text": 9,
        "appendix_item": 10,
        "paragraph": 11,
    }

    return (
        float(element.get("page_start") or 0),
        float(element.get("_y") or 0),
        float(element.get("_x") or 0),
        type_priority.get(element["type"], 99),
    )


def normalize_element_order(elements: list[dict[str, Any]], language: str) -> list[dict[str, Any]]:
    """
    Main contract clauses must preserve logical hierarchy rather than raw
    Docling order. Appendices retain item numbering within their own scope.
    """
    main_sections: dict[str, list[dict[str, Any]]] = defaultdict(list)
    other: list[dict[str, Any]] = []

    for element in elements:
        if element["scope_id"] == "main_contract" and element["type"] in {
            "section_heading",
            "clause",
        }:
            anchor = element.get("anchor_uid") or ""
            parent = anchor.split(".", 1)[0]
            if parent in MAIN_SECTION_ANCHORS:
                main_sections[parent].append(element)
                continue
        other.append(element)

    front_and_other = sorted(other, key=final_sort_key)

    main_ordered: list[dict[str, Any]] = []
    for section in sorted(main_sections, key=int):
        section_elements = main_sections[section]
        section_elements.sort(
            key=lambda item: (
                0 if item["type"] == "section_heading" else 1,
                anchor_sort_key(item.get("anchor_uid") or "999"),
            )
        )
        main_ordered.extend(section_elements)

    # Insert whole main contract after the last p.1–2 element and before p.10+.
    before_main = [
        element
        for element in front_and_other
        if int(element.get("page_start") or 0) <= 2
    ]
    after_main = [
        element
        for element in front_and_other
        if int(element.get("page_start") or 0) > 2
    ]

    combined = before_main + main_ordered + after_main

    for order, element in enumerate(combined, start=1):
        anchor = element.get("anchor_uid") or "unanchored"
        element["element_id"] = (
            f"{language}:{element['scope_id']}:{element['type']}:"
            f"{anchor}:{order:04d}"
        )
        element["projection_order"] = order
        element.pop("_x", None)
        element.pop("_y", None)
        element.pop("reading_order", None)

    return combined


def validate(
    elements: list[dict[str, Any]],
    inventory: dict[str, dict[str, list[dict[str, Any]]]],
    language: str,
    unresolved: list[dict[str, Any]],
) -> dict[str, Any]:
    expected_main = set(inventory.get("main_contract", {}))
    actual_main = {
        element["anchor_uid"]
        for element in elements
        if element["scope_id"] == "main_contract"
        and element["type"] in {"section_heading", "clause"}
        and element.get("anchor_uid")
    }

    expected_appendices = ["appendix_1", "appendix_2", "appendix_3"]
    present_appendices = sorted(
        {
            element["scope_id"]
            for element in elements
            if element["type"] == "appendix_heading"
        }
    )

    signature_pages = {11, 15, 17, 20}
    signatures_present = {
        page: any(
            element["type"] == "signature_block"
            and int(element.get("page_start") or 0) == page
            for element in elements
        )
        for page in sorted(signature_pages)
    }

    opposite = "en" if language == "ru" else "ru"
    leakage = [
        {
            "element_id": element["element_id"],
            "text": element["text"][:250],
        }
        for element in elements
        if text_language(element["text"]) == opposite
    ]

    return {
        "language": language,
        "element_count": len(elements),
        "expected_main_anchor_count": len(expected_main),
        "present_main_anchor_count": len(actual_main),
        "missing_main_anchors": sorted(
            expected_main - actual_main,
            key=anchor_sort_key,
        ),
        "appendices_expected": expected_appendices,
        "appendices_present": present_appendices,
        "appendices_missing": sorted(
            set(expected_appendices) - set(present_appendices)
        ),
        "signature_blocks_by_page": signatures_present,
        "missing_signature_pages": [
            page for page, present in signatures_present.items() if not present
        ],
        "unresolved_item_count": len(unresolved),
        "needs_review_count": sum(
            1 for element in elements if element["needs_review"]
        ),
        "opposite_language_leak_count": len(leakage),
        "opposite_language_leaks": leakage,
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_markdown(path: Path, language: str, elements: list[dict[str, Any]]) -> None:
    title = (
        "# Русская одноязычная проекция"
        if language == "ru"
        else "# English monolingual projection"
    )
    lines = [title, ""]

    for element in elements:
        review = " ⚠ needs review" if element["needs_review"] else ""
        text = element["text"]

        if element["type"] in {"document_title", "section_heading", "appendix_heading"}:
            lines.extend([f"## {text}{review}", ""])
        else:
            lines.extend([f"{text}{review}", ""])

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build full RU and EN document projections from a canonical "
            "Docling bilingual layout, preserving master anchor inventory."
        )
    )
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()

    if not input_path.exists():
        print(f"Input not found: {input_path}", file=sys.stderr)
        return 2

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    atoms = payload.get("elements") or []

    if not atoms:
        print("Canonical JSON contains no elements.", file=sys.stderr)
        return 3

    atoms = sort_atoms(atoms)
    inventory = master_anchor_inventory(atoms)

    candidate_cache = {
        language: [
            atom
            for atom in atoms
            if is_content_candidate(atom, language)
        ]
        for language in ("ru", "en")
    }

    print(f"Input: {input_path}")
    print(f"Canonical atoms: {len(atoms)}")
    print(
        "Master inventory: "
        + ", ".join(
            f"{scope}={len(anchors)}"
            for scope, anchors in sorted(inventory.items())
        )
    )

    all_documents: dict[str, dict[str, Any]] = {}

    for language in ("ru", "en"):
        print(f"Building {language.upper()} full projection...")

        unanchored, unresolved_unanchored = build_unanchored_blocks(
            atoms,
            language,
        )
        main_contract, unresolved_main = build_main_contract(
            inventory,
            atoms,
            candidate_cache[language],
            language,
        )
        appendices, unresolved_appendices = build_appendices(
            inventory,
            atoms,
            candidate_cache[language],
            language,
        )

        unresolved = (
            unresolved_unanchored
            + unresolved_main
            + unresolved_appendices
        )
        elements = normalize_element_order(
            unanchored + main_contract + appendices,
            language,
        )
        validation = validate(
            elements,
            inventory,
            language,
            unresolved,
        )

        document = {
            "schema_version": "docling_full_monolingual_projection_v2",
            "language": language,
            "source_canonical_document": str(input_path),
            "scope_page_map": {
                scope: [first, last]
                for scope, first, last in SCOPE_RANGES
            },
            "elements": elements,
            "unresolved_items": unresolved,
            "validation": validation,
        }
        all_documents[language] = document

        write_json(output_dir / f"{language}_full_document.json", document)
        write_json(
            output_dir / f"{language}_unresolved_items.json",
            unresolved,
        )
        write_markdown(
            output_dir / f"{language}_full_document.md",
            language,
            elements,
        )

    write_json(
        output_dir / "validation_report.json",
        {
            "source_canonical_document": str(input_path),
            "ru": all_documents["ru"]["validation"],
            "en": all_documents["en"]["validation"],
        },
    )

    write_json(
        output_dir / "master_anchor_inventory.json",
        {
            scope: {
                anchor: [
                    {
                        "element_id": atom["element_id"],
                        "page": atom.get("page"),
                        "language": atom.get("language"),
                        "marker": atom.get("marker"),
                        "text": normalize(atom.get("text")),
                    }
                    for atom in witnesses
                ]
                for anchor, witnesses in sorted(
                    anchors.items(),
                    key=lambda item: anchor_sort_key(item[0]),
                )
            }
            for scope, anchors in sorted(inventory.items())
        },
    )

    print()
    print("Generated:")
    for filename in (
        "ru_full_document.json",
        "en_full_document.json",
        "ru_full_document.md",
        "en_full_document.md",
        "ru_unresolved_items.json",
        "en_unresolved_items.json",
        "master_anchor_inventory.json",
        "validation_report.json",
    ):
        print(f"  {output_dir / filename}")

    print()
    print("RU validation:")
    print(json.dumps(all_documents["ru"]["validation"], ensure_ascii=False, indent=2))
    print()
    print("EN validation:")
    print(json.dumps(all_documents["en"]["validation"], ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
DEFAULT_OUTPUT = "/srv/steloom-dev/artifacts/docling_full_monolingual_export"

CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
LATIN_RE = re.compile(r"[A-Za-z]")
SPACE_RE = re.compile(r"\s+")
NUMERIC_ANCHOR_RE = re.compile(r"^\d+(?:\.\d+)*$")
LEADING_ANCHOR_RE = re.compile(
    r"^\s*(?P<anchor>\d+(?:\.\d+)*)(?:[.)])?(?=\s|$)"
)
APPENDIX_START_RE = re.compile(
    r"\b(?:ПРИЛОЖЕНИЕ|APPENDIX|ANNEX|EXHIBIT|SCHEDULE)\b",
    re.IGNORECASE,
)
TOC_RE = re.compile(
    r"\b(?:СОДЕРЖАНИЕ|TABLE OF CONTENTS|CONTENTS)\b",
    re.IGNORECASE,
)
SIGNATURE_RE = re.compile(
    r"\b(?:ОТ ИМЕНИ|ON BEHALF OF|ПОДПИС|SIGNATURE)\b",
    re.IGNORECASE,
)
DATE_RE = re.compile(r"\b(?:DATED|ДАТИРОВАН|ОТ)\b", re.IGNORECASE)
TITLE_RE = re.compile(
    r"\b(?:SALE AND PURCHASE AGREEMENT|ДОГОВОР КУПЛИ)\b",
    re.IGNORECASE,
)

MAIN_SECTION_ANCHORS = {str(number) for number in range(1, 9)}


def normalize_text(value: Any) -> str:
    return SPACE_RE.sub(" ", str(value or "")).strip()


def language_of_text(text: str) -> str:
    cyrillic_count = len(CYRILLIC_RE.findall(text))
    latin_count = len(LATIN_RE.findall(text))

    if cyrillic_count > 0 and latin_count == 0:
        return "ru"
    if latin_count > 0 and cyrillic_count == 0:
        return "en"
    if cyrillic_count > 0 and latin_count > 0:
        return "mixed"
    return "shared"


def clean_anchor(value: Any) -> str | None:
    candidate = normalize_text(value).rstrip(".)")
    return candidate if NUMERIC_ANCHOR_RE.fullmatch(candidate) else None


def extract_leading_anchor(text: str) -> str | None:
    match = LEADING_ANCHOR_RE.match(normalize_text(text))
    if not match:
        return None
    anchor = match.group("anchor")
    return anchor if NUMERIC_ANCHOR_RE.fullmatch(anchor) else None


def anchor_depth(anchor: str | None) -> int:
    return len(anchor.split(".")) if anchor else 0


def is_furniture(atom: dict[str, Any]) -> bool:
    return bool(atom.get("is_furniture"))


def atom_text(atom: dict[str, Any]) -> str:
    return normalize_text(atom.get("text"))


def atom_anchor(atom: dict[str, Any]) -> str | None:
    return clean_anchor(atom.get("marker")) or extract_leading_anchor(atom_text(atom))


def bbox(atom: dict[str, Any]) -> list[float] | None:
    value = atom.get("bbox")
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return None


def is_top_of_page(atom: dict[str, Any]) -> bool:
    value = bbox(atom)
    return bool(value and value[1] < 230)


def is_content_atom(atom: dict[str, Any]) -> bool:
    return not is_furniture(atom) and bool(atom_text(atom))


def sort_atoms(atoms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        atoms,
        key=lambda atom: (
            int(atom.get("page") or 0),
            int(atom.get("reading_order") or 0),
            float((bbox(atom) or [0, 0, 0, 0])[1]),
            float((bbox(atom) or [0, 0, 0, 0])[0]),
        ),
    )


def split_mixed_text(text: str) -> dict[str, str | None]:
    text = normalize_text(text)
    if not text:
        return {"ru": None, "en": None}

    if " / " in text:
        left, right = [normalize_text(part) for part in text.split(" / ", 1)]
        left_lang = language_of_text(left)
        right_lang = language_of_text(right)

        if left_lang == "en" and right_lang == "ru":
            return {"en": left, "ru": right}
        if left_lang == "ru" and right_lang == "en":
            return {"en": right, "ru": left}

    ru_start = re.search(
        r"\b(?:от|между|приложение|договор)\b",
        text,
        re.IGNORECASE,
    )
    if ru_start:
        left = normalize_text(text[:ru_start.start()])
        right = normalize_text(text[ru_start.start():])
        if language_of_text(left) == "en" and language_of_text(right) in {
            "ru",
            "mixed",
        }:
            return {"en": left, "ru": right}

    first_cyrillic = CYRILLIC_RE.search(text)
    if first_cyrillic:
        left = normalize_text(text[:first_cyrillic.start()])
        right = normalize_text(text[first_cyrillic.start():])
        if len(left) >= 4 and len(right) >= 4 and language_of_text(left) == "en":
            return {"en": left, "ru": right}

    first_latin = LATIN_RE.search(text)
    if first_latin:
        left = normalize_text(text[:first_latin.start()])
        right = normalize_text(text[first_latin.start():])
        if len(left) >= 4 and len(right) >= 4 and language_of_text(left) == "ru":
            return {"ru": left, "en": right}

    return {"ru": None, "en": None}


def materialize_target_atom(
    atom: dict[str, Any],
    target_language: str,
) -> tuple[str | None, str, float, bool, str | None]:
    text = atom_text(atom)
    source_language = atom.get("language") or language_of_text(text)

    if source_language == target_language:
        return text, "native_atom", 0.99, False, None

    if source_language == "shared":
        return text, "shared_atom", 0.96, False, None

    if source_language == "mixed":
        text = split_mixed_text(text).get(target_language)
        if text:
            return text, "split_mixed_atom", 0.82, False, None
        return (
            None,
            "unresolved_mixed_atom",
            0.0,
            True,
            "mixed_atom_could_not_be_safely_split",
        )

    return None, "opposite_language_atom", 0.0, False, None


def looks_like_heading(atom: dict[str, Any]) -> bool:
    text = atom_text(atom)

    if atom.get("label") == "section_header":
        return True

    anchor = atom_anchor(atom)
    letters = re.sub(r"[^A-Za-zА-Яа-яЁё]", "", text)
    uppercase_count = sum(char.isupper() for char in letters)

    if anchor and anchor_depth(anchor) == 1 and len(text) < 180:
        return True

    return (
        len(letters) >= 4
        and uppercase_count / max(len(letters), 1) > 0.65
    )


def classify_region(atom: dict[str, Any], scope_id: str) -> str:
    text = atom_text(atom)
    page = int(atom.get("page") or 0)

    if scope_id != "main_contract":
        return "appendix"

    if page <= 2:
        return "table_of_contents" if TOC_RE.search(text) else "front_matter"

    if SIGNATURE_RE.search(text):
        return "signatures"

    if atom.get("label") == "page_footer":
        return "footer"

    return "main_agreement"


def detect_scopes(atoms: list[dict[str, Any]]) -> dict[str, str]:
    scope_by_id: dict[str, str] = {}
    current_scope = "main_contract"
    appendix_number = 0
    seen_appendix_start_pages: set[int] = set()

    for atom in sort_atoms(atoms):
        text = atom_text(atom)
        page = int(atom.get("page") or 0)

        starts_appendix = (
            bool(APPENDIX_START_RE.search(text))
            and looks_like_heading(atom)
            and is_top_of_page(atom)
            and page >= 10
            and not is_furniture(atom)
        )

        if starts_appendix and page not in seen_appendix_start_pages:
            appendix_number += 1
            current_scope = f"appendix_{appendix_number}"
            seen_appendix_start_pages.add(page)

        scope_by_id[atom["element_id"]] = current_scope

    return scope_by_id


def determine_element_type(
    atom: dict[str, Any],
    scope_id: str,
    anchor: str | None,
    text: str,
) -> str:
    page = int(atom.get("page") or 0)

    if scope_id != "main_contract":
        if anchor:
            return "appendix_item"
        if looks_like_heading(atom):
            return "appendix_heading"
        return "appendix_text"

    if page <= 2:
        if TITLE_RE.search(text):
            return "document_title"
        if DATE_RE.search(text):
            return "document_date"
        if TOC_RE.search(text):
            return "table_of_contents_heading"
        return "front_matter"

    if SIGNATURE_RE.search(text):
        return "signature_block"

    if anchor:
        if anchor_depth(anchor) == 1 and anchor in MAIN_SECTION_ANCHORS:
            return "section_heading"
        return "clause"

    if looks_like_heading(atom):
        return "heading"

    return "paragraph"


def selected_atoms_for_language(
    atoms: list[dict[str, Any]],
    target_language: str,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []

    for atom in sort_atoms(atoms):
        if not is_content_atom(atom):
            continue

        language = atom.get("language") or language_of_text(atom_text(atom))
        if language in {target_language, "shared", "mixed"}:
            selected.append(atom)

    return selected


def find_section_heading(
    target_language: str,
    target_anchor: str,
    atoms: list[dict[str, Any]],
    scope_by_id: dict[str, str],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    candidates: list[
        tuple[float, dict[str, Any], str, float, bool, str | None]
    ] = []

    for atom in atoms:
        if scope_by_id.get(atom["element_id"]) != "main_contract":
            continue
        if not is_content_atom(atom):
            continue

        text, method, confidence, needs_review, reason = materialize_target_atom(
            atom,
            target_language,
        )
        if not text:
            continue

        anchor = atom_anchor(atom)
        score = 0.0

        if anchor == target_anchor:
            score += 0.70

        if looks_like_heading(atom):
            score += 0.20

        if anchor and anchor.startswith(f"{target_anchor}."):
            score -= 0.60

        if re.match(
            rf"^\s*{re.escape(target_anchor)}(?:[.)]|\s+)",
            text,
        ):
            score += 0.25

        if len(text) < 180:
            score += 0.05

        if score > 0:
            candidates.append(
                (score, atom, text, confidence, needs_review, reason)
            )

    if candidates:
        score, atom, text, confidence, needs_review, reason = max(
            candidates,
            key=lambda item: item[0],
        )

        if not re.match(
            rf"^\s*{re.escape(target_anchor)}(?:[.)]|\s+)",
            text,
        ):
            text = f"{target_anchor}. {text}"

        return atom, {
            "text": text,
            "method": "native_or_recovered_heading",
            "confidence": min(0.98, max(confidence, score)),
            "needs_review": needs_review,
            "reason": reason,
        }

    placeholder = (
        f"{target_anchor}. [РАЗДЕЛ ТРЕБУЕТ ПРОВЕРКИ]"
        if target_language == "ru"
        else f"{target_anchor}. [SECTION TITLE REQUIRES REVIEW]"
    )
    return None, {
        "text": placeholder,
        "method": "synthetic_required_section",
        "confidence": 0.0,
        "needs_review": True,
        "reason": (
            "section_inferred_from_child_clauses_but_title_not_recovered"
        ),
    }


def make_element(
    target_language: str,
    ordinal: int,
    atom: dict[str, Any],
    text: str,
    scope_id: str,
    element_type: str,
    anchor: str | None,
    method: str,
    confidence: float,
    needs_review: bool,
    reason: str | None,
) -> dict[str, Any]:
    return {
        "element_id": (
            f"{target_language}:{scope_id}:{element_type}:"
            f"{anchor or 'unanchored'}:{ordinal:04d}"
        ),
        "type": element_type,
        "scope_id": scope_id,
        "region": classify_region(atom, scope_id),
        "text": text,
        "anchor_uid": anchor,
        "page_start": atom.get("page"),
        "page_end": atom.get("page"),
        "bbox": atom.get("bbox"),
        "reading_order": atom.get("reading_order"),
        "source_element_ids": [atom["element_id"]],
        "projection_method": method,
        "projection_confidence": round(confidence, 3),
        "needs_review": needs_review,
        "review_reason": reason,
    }


def insert_missing_main_sections(
    elements: list[dict[str, Any]],
    target_language: str,
    atoms: list[dict[str, Any]],
    scope_by_id: dict[str, str],
) -> list[dict[str, Any]]:
    existing_sections = {
        item["anchor_uid"]
        for item in elements
        if item["type"] == "section_heading"
        and item["scope_id"] == "main_contract"
    }

    first_child_index: dict[str, int] = {}
    for index, item in enumerate(elements):
        anchor = item.get("anchor_uid")
        if (
            item.get("scope_id") == "main_contract"
            and anchor
            and "." in anchor
        ):
            first_child_index.setdefault(anchor.split(".", 1)[0], index)

    inserts: list[tuple[int, dict[str, Any]]] = []

    for section_anchor in sorted(first_child_index, key=int):
        if section_anchor not in MAIN_SECTION_ANCHORS:
            continue
        if section_anchor in existing_sections:
            continue

        heading_atom, heading = find_section_heading(
            target_language,
            section_anchor,
            atoms,
            scope_by_id,
        )
        child = elements[first_child_index[section_anchor]]

        inserts.append(
            (
                first_child_index[section_anchor],
                {
                    "element_id": (
                        f"{target_language}:main_contract:section_heading:"
                        f"{section_anchor}:synthetic"
                    ),
                    "type": "section_heading",
                    "scope_id": "main_contract",
                    "region": "main_agreement",
                    "text": heading["text"],
                    "anchor_uid": section_anchor,
                    "page_start": (
                        heading_atom.get("page")
                        if heading_atom
                        else child["page_start"]
                    ),
                    "page_end": (
                        heading_atom.get("page")
                        if heading_atom
                        else child["page_start"]
                    ),
                    "bbox": heading_atom.get("bbox") if heading_atom else None,
                    "reading_order": (
                        heading_atom.get("reading_order")
                        if heading_atom
                        else child["reading_order"]
                    ),
                    "source_element_ids": (
                        [heading_atom["element_id"]]
                        if heading_atom
                        else []
                    ),
                    "projection_method": heading["method"],
                    "projection_confidence": round(heading["confidence"], 3),
                    "needs_review": heading["needs_review"],
                    "review_reason": heading["reason"],
                },
            )
        )

    offset = 0
    for index, element in sorted(inserts, key=lambda item: item[0]):
        elements.insert(index + offset, element)
        offset += 1

    return elements


def build_projection(
    atoms: list[dict[str, Any]],
    target_language: str,
    scope_by_id: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    elements: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    ordinal = 0

    for atom in selected_atoms_for_language(atoms, target_language):
        text, method, confidence, needs_review, reason = materialize_target_atom(
            atom,
            target_language,
        )

        if text is None:
            unresolved.append(
                {
                    "source_element_id": atom["element_id"],
                    "page": atom.get("page"),
                    "scope_id": scope_by_id.get(
                        atom["element_id"],
                        "main_contract",
                    ),
                    "text": atom_text(atom),
                    "reason": reason,
                    "target_language": target_language,
                }
            )
            continue

        scope_id = scope_by_id.get(atom["element_id"], "main_contract")
        anchor = atom_anchor(atom)
        element_type = determine_element_type(
            atom,
            scope_id,
            anchor,
            text,
        )

        ordinal += 1
        elements.append(
            make_element(
                target_language,
                ordinal,
                atom,
                text,
                scope_id,
                element_type,
                anchor,
                method,
                confidence,
                needs_review,
                reason,
            )
        )

    elements = insert_missing_main_sections(
        elements,
        target_language,
        atoms,
        scope_by_id,
    )

    for ordinal, element in enumerate(elements, start=1):
        anchor = element["anchor_uid"] or "unanchored"
        element["element_id"] = (
            f"{target_language}:{element['scope_id']}:"
            f"{element['type']}:{anchor}:{ordinal:04d}"
        )
        element["projection_order"] = ordinal

    return elements, unresolved


def validate(
    elements: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
    target_language: str,
) -> dict[str, Any]:
    section_headings = {
        item["anchor_uid"]
        for item in elements
        if item["type"] == "section_heading"
        and item["scope_id"] == "main_contract"
    }

    child_sections = {
        item["anchor_uid"].split(".", 1)[0]
        for item in elements
        if item["scope_id"] == "main_contract"
        and item.get("anchor_uid")
        and "." in item["anchor_uid"]
        and item["anchor_uid"].split(".", 1)[0] in MAIN_SECTION_ANCHORS
    }

    opposite_language = "en" if target_language == "ru" else "ru"
    leakage = [
        {
            "element_id": item["element_id"],
            "text": item["text"][:280],
        }
        for item in elements
        if language_of_text(item["text"]) == opposite_language
    ]

    review_items = [
        {
            "element_id": item["element_id"],
            "type": item["type"],
            "anchor_uid": item["anchor_uid"],
            "reason": item["review_reason"],
        }
        for item in elements
        if item["needs_review"]
    ]

    return {
        "language": target_language,
        "element_count": len(elements),
        "unresolved_item_count": len(unresolved),
        "needs_review_count": len(review_items),
        "needs_review_items": review_items,
        "required_main_sections": sorted(child_sections, key=int),
        "present_main_sections": sorted(section_headings, key=int),
        "missing_main_sections": sorted(
            child_sections - section_headings,
            key=int,
        ),
        "opposite_language_leak_count": len(leakage),
        "opposite_language_leaks": leakage,
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_markdown(
    path: Path,
    target_language: str,
    elements: list[dict[str, Any]],
    validation: dict[str, Any],
) -> None:
    heading = (
        "# Русская одноязычная проекция"
        if target_language == "ru"
        else "# English monolingual projection"
    )

    lines = [
        heading,
        "",
        f"- Elements: {validation['element_count']}",
        f"- Unresolved source atoms: {validation['unresolved_item_count']}",
        f"- Needs review: {validation['needs_review_count']}",
        (
            "- Missing main sections: "
            f"{', '.join(validation['missing_main_sections']) or 'none'}"
        ),
        "",
    ]

    for item in elements:
        text = item["text"]
        review = " ⚠ needs review" if item["needs_review"] else ""

        if item["type"] in {
            "document_title",
            "section_heading",
            "appendix_heading",
        }:
            lines.extend([f"## {text}{review}", ""])
        else:
            lines.extend([f"{text}{review}", ""])

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()

    if not input_path.exists():
        print(f"Input not found: {input_path}", file=sys.stderr)
        return 2

    canonical = json.loads(input_path.read_text(encoding="utf-8"))
    atoms = canonical.get("elements") or []

    if not atoms:
        print("No elements found in canonical JSON.", file=sys.stderr)
        return 3

    print(f"Input: {input_path}")
    print(f"Canonical atoms: {len(atoms)}")
    print("1/4 Detecting scopes...")

    scope_by_id = detect_scopes(atoms)
    results: dict[str, dict[str, Any]] = {}

    for target_language in ("ru", "en"):
        print(f"2/4 Building full {target_language.upper()} document...")

        elements, unresolved = build_projection(
            atoms,
            target_language,
            scope_by_id,
        )
        validation = validate(elements, unresolved, target_language)

        document = {
            "schema_version": "docling_full_monolingual_projection_v1",
            "language": target_language,
            "source_canonical_document": str(input_path),
            "element_count": len(elements),
            "elements": elements,
            "unresolved_items": unresolved,
            "validation": validation,
        }
        results[target_language] = document

        write_json(
            output_dir / f"{target_language}_full_document.json",
            document,
        )
        write_json(
            output_dir / f"{target_language}_unresolved_items.json",
            unresolved,
        )
        write_markdown(
            output_dir / f"{target_language}_full_document.md",
            target_language,
            elements,
            validation,
        )

    print("3/4 Writing validation report...")
    write_json(
        output_dir / "validation_report.json",
        {
            "source_canonical_document": str(input_path),
            "ru": results["ru"]["validation"],
            "en": results["en"]["validation"],
        },
    )

    print("4/4 Done.")
    print()
    print("Generated:")
    for filename in (
        "ru_full_document.json",
        "en_full_document.json",
        "ru_full_document.md",
        "en_full_document.md",
        "ru_unresolved_items.json",
        "en_unresolved_items.json",
        "validation_report.json",
    ):
        print(f"  {output_dir / filename}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

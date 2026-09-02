#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import pymupdf
from docling.document_converter import DocumentConverter


DEFAULT_INPUT = (
    "/srv/steloom-dev/docs/"
    "Simonova _ SPA _ Property _ execution _version (full).pdf"
)
DEFAULT_OUTPUT = "/srv/steloom-dev/artifacts/canonical_bilingual_layout"

CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
LATIN_RE = re.compile(r"[A-Za-z]")
SPACE_RE = re.compile(r"\s+")
NUMERIC_MARKER_RE = re.compile(r"^\d+(?:\.\d+)*$")


def normalize_text(value: Any) -> str:
    return SPACE_RE.sub(" ", str(value or "")).strip()


def classify_language(text: str) -> str:
    text = normalize_text(text)
    has_cyrillic = bool(CYRILLIC_RE.search(text))
    has_latin = bool(LATIN_RE.search(text))

    if has_cyrillic and not has_latin:
        return "ru"
    if has_latin and not has_cyrillic:
        return "en"
    if has_cyrillic and has_latin:
        return "mixed"
    return "shared"


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, dict):
        return {
            str(key): json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]

    if hasattr(value, "model_dump"):
        try:
            return json_safe(value.model_dump(mode="json"))
        except Exception:
            try:
                return json_safe(value.model_dump())
            except Exception:
                pass

    if hasattr(value, "dict"):
        try:
            return json_safe(value.dict())
        except Exception:
            pass

    if hasattr(value, "__dict__"):
        try:
            return {
                str(key): json_safe(item)
                for key, item in vars(value).items()
                if not str(key).startswith("_")
            }
        except Exception:
            pass

    return str(value)


def item_ref(item: Any) -> str | None:
    for field in ("self_ref", "ref"):
        value = getattr(item, field, None)
        if value is not None:
            value = str(value).strip()
            if value:
                return value
    return None


def item_parent_ref(item: Any) -> str | None:
    value = getattr(item, "parent", None)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def item_label(item: Any) -> str | None:
    value = getattr(item, "label", None)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def item_text(item: Any) -> str:
    for field in ("text", "name"):
        value = getattr(item, field, None)
        text = normalize_text(value)
        if text:
            return text
    return ""


def item_marker(item: Any) -> str | None:
    """
    Preserves Docling marker metadata if it exists on the text item.
    """
    value = normalize_text(getattr(item, "marker", None))
    return value or None


def is_numeric_marker(value: str | None) -> bool:
    if not value:
        return False
    return bool(NUMERIC_MARKER_RE.fullmatch(value.rstrip(".)")))


def provenance_items(item: Any) -> list[Any]:
    value = getattr(item, "prov", None)
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def page_from_provenance(provenance: Any) -> int | None:
    for field in ("page_no", "page"):
        value = getattr(provenance, field, None)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None


def bbox_from_provenance(provenance: Any) -> list[float] | None:
    bbox = getattr(provenance, "bbox", None)
    if bbox is None:
        return None

    result: list[float] = []
    for field in ("l", "t", "r", "b"):
        value = getattr(bbox, field, None)
        if value is None:
            return None
        try:
            result.append(round(float(value), 3))
        except (TypeError, ValueError):
            return None

    return result


def locations_for_item(item: Any) -> list[tuple[int | None, list[float] | None]]:
    locations = [
        (
            page_from_provenance(provenance),
            bbox_from_provenance(provenance),
        )
        for provenance in provenance_items(item)
    ]
    return locations or [(None, None)]


def item_is_attached_marker_only(item: Any, text: str, marker: str | None) -> bool:
    """
    Handles known Docling marker-only representations without inferring clauses.
    """
    explicit = getattr(item, "is_attached_marker_only", None)
    if explicit is not None:
        return bool(explicit)

    if marker and is_numeric_marker(marker):
        cleaned_text = text.rstrip(".)").strip()
        if not cleaned_text or cleaned_text == marker.rstrip(".)"):
            return True

    return bool(is_numeric_marker(text))


def serialize_raw_text_item(index: int, item: Any) -> dict[str, Any]:
    return {
        "source_collection": "texts",
        "source_index": index,
        "item_ref": item_ref(item),
        "parent_ref": item_parent_ref(item),
        "label": item_label(item),
        "text": item_text(item),
        "marker": item_marker(item),
        "raw": json_safe(item),
    }


def serialize_raw_body_item(index: int, item: Any, level: Any) -> dict[str, Any]:
    return {
        "source_collection": "iterate_items",
        "source_index": index,
        "level": level,
        "item_ref": item_ref(item),
        "parent_ref": item_parent_ref(item),
        "label": item_label(item),
        "text": item_text(item),
        "marker": item_marker(item),
        "raw": json_safe(item),
    }


def iter_body_items(document: Any) -> Iterable[tuple[int, Any, Any]]:
    if not hasattr(document, "iterate_items"):
        return

    try:
        for index, (item, level) in enumerate(document.iterate_items()):
            yield index, item, level
    except Exception:
        return


def extract_pymupdf_spans(pdf_path: Path) -> dict[int, list[dict[str, Any]]]:
    pages: dict[int, list[dict[str, Any]]] = defaultdict(list)

    with pymupdf.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf, start=1):
            page_data = page.get_text("dict")

            for block_index, block in enumerate(page_data.get("blocks", [])):
                if block.get("type") != 0:
                    continue

                for line_index, line in enumerate(block.get("lines", [])):
                    for span_index, span in enumerate(line.get("spans", [])):
                        text = normalize_text(span.get("text"))
                        if not text:
                            continue

                        flags = int(span.get("flags") or 0)
                        pages[page_number].append(
                            {
                                "span_id": (
                                    f"pymupdf:p{page_number}:"
                                    f"b{block_index}:l{line_index}:s{span_index}"
                                ),
                                "text": text,
                                "bbox": [
                                    round(float(value), 3)
                                    for value in span.get(
                                        "bbox",
                                        [0, 0, 0, 0],
                                    )
                                ],
                                "font": span.get("font"),
                                "font_size": round(
                                    float(span.get("size") or 0),
                                    3,
                                ),
                                "flags": flags,
                                "bold": bool(flags & 16),
                                "italic": bool(flags & 2),
                                "color": span.get("color"),
                            }
                        )

    return pages


def page_dimensions(pdf_path: Path) -> dict[int, dict[str, float]]:
    result: dict[int, dict[str, float]] = {}

    with pymupdf.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf, start=1):
            rect = page.rect
            result[page_number] = {
                "width": round(float(rect.width), 3),
                "height": round(float(rect.height), 3),
            }

    return result


def bbox_distance(first: list[float], second: list[float]) -> float:
    first_x = (first[0] + first[2]) / 2
    first_y = (first[1] + first[3]) / 2
    second_x = (second[0] + second[2]) / 2
    second_y = (second[1] + second[3]) / 2
    return ((first_x - second_x) ** 2 + (first_y - second_y) ** 2) ** 0.5


def overlap_area(first: list[float], second: list[float]) -> float:
    x0 = max(first[0], second[0])
    y0 = max(first[1], second[1])
    x1 = min(first[2], second[2])
    y1 = min(first[3], second[3])
    return max(0.0, x1 - x0) * max(0.0, y1 - y0)


def match_style(
    atom_bbox: list[float] | None,
    atom_text: str,
    spans: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """
    Adds visual style evidence. It never changes atom text or layout.
    """
    if not spans:
        return None

    text = normalize_text(atom_text).lower()
    scored: list[tuple[float, dict[str, Any]]] = []

    for span in spans:
        score = 0.0
        span_text = span["text"].lower()

        if text and text == span_text:
            score += 10000.0
        elif text and (text in span_text or span_text in text):
            score += 5000.0

        if atom_bbox:
            score += overlap_area(atom_bbox, span["bbox"]) * 10.0
            score -= bbox_distance(atom_bbox, span["bbox"]) * 0.01

        scored.append((score, span))

    score, best = max(scored, key=lambda item: item[0])
    if score <= 0:
        return None

    return {
        "span_id": best["span_id"],
        "font": best["font"],
        "font_size": best["font_size"],
        "bold": best["bold"],
        "italic": best["italic"],
        "color": best["color"],
        "match_score": round(score, 3),
    }


def atom_sort_key(atom: dict[str, Any]) -> tuple[float, float, int]:
    bbox = atom.get("bbox")
    if bbox:
        return bbox[1], bbox[0], atom["source"]["docling_index"]
    return 10**9, 10**9, atom["source"]["docling_index"]


def build_canonical_layout(
    pdf_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Generic extraction layer.

    Canonical pages[].atoms[] are built exclusively from document.texts.
    iterate_items() is exported separately as raw diagnostic provenance.

    This function does NOT infer:
    - clauses;
    - document tree;
    - sections;
    - appendix scopes;
    - page ranges;
    - semantic relationships between atoms.
    """
    converter = DocumentConverter()
    conversion = converter.convert(str(pdf_path))
    document = conversion.document

    dimensions = page_dimensions(pdf_path)
    pymupdf_spans = extract_pymupdf_spans(pdf_path)

    text_items = list(getattr(document, "texts", None) or [])
    table_items = list(getattr(document, "tables", None) or [])

    raw_text_items: list[dict[str, Any]] = []
    raw_body_items: list[dict[str, Any]] = []
    raw_table_items: list[dict[str, Any]] = []

    for index, item in enumerate(text_items):
        raw_text_items.append(serialize_raw_text_item(index, item))

    for index, item, level in iter_body_items(document):
        raw_body_items.append(serialize_raw_body_item(index, item, level))

    for index, item in enumerate(table_items):
        raw_table_items.append(
            {
                "source_collection": "tables",
                "source_index": index,
                "item_ref": item_ref(item),
                "parent_ref": item_parent_ref(item),
                "label": item_label(item),
                "text": item_text(item),
                "raw": json_safe(item),
            }
        )

    atoms_by_page: dict[int, list[dict[str, Any]]] = defaultdict(list)
    no_page_items: list[dict[str, Any]] = []

    for index, item in enumerate(text_items):
        text = item_text(item)
        marker = item_marker(item)
        label = item_label(item)
        ref = item_ref(item)
        parent_ref = item_parent_ref(item)

        for page, bbox in locations_for_item(item):
            if page is None:
                no_page_items.append(
                    {
                        "source_collection": "texts",
                        "source_index": index,
                        "item_ref": ref,
                        "parent_ref": parent_ref,
                        "label": label,
                        "marker": marker,
                        "text": text,
                        "reason": "missing_page_provenance",
                    }
                )
                continue

            is_marker_only = item_is_attached_marker_only(item, text, marker)

            atoms_by_page[page].append(
                {
                    "element_id": "",
                    "page": page,
                    "bbox": bbox,
                    "reading_order": None,
                    "text": text,
                    "marker": marker,
                    "language": classify_language(text),
                    "label": label,
                    "parent_ref": parent_ref,
                    "is_marker_only": is_marker_only,
                    "formatting": {
                        "source_label": label,
                        "is_furniture": label in {
                            "page_header",
                            "page_footer",
                        },
                        "is_table": False,
                        "is_heading_candidate": label == "section_header",
                    },
                    "style": match_style(
                        bbox,
                        text,
                        pymupdf_spans.get(page, []),
                    ),
                    "source": {
                        "docling_collection": "texts",
                        "docling_index": index,
                        "docling_item_ref": ref,
                    },
                }
            )

    pages: list[dict[str, Any]] = []
    atom_counter = 0

    for page_number in sorted(dimensions):
        atoms = atoms_by_page.get(page_number, [])
        atoms.sort(key=atom_sort_key)

        for atom in atoms:
            atom_counter += 1
            atom["element_id"] = f"atom:{atom_counter:06d}"
            atom["reading_order"] = atom_counter

        pages.append(
            {
                "page_number": page_number,
                **dimensions[page_number],
                "atoms": atoms,
                "pymupdf_spans": pymupdf_spans.get(page_number, []),
            }
        )

    canonical = {
        "schema_version": "canonical_bilingual_layout_v3",
        "source_pdf": str(pdf_path),
        "page_count": len(pages),
        "pages": pages,
        "source_item_counts": {
            "texts": len(text_items),
            "tables": len(table_items),
            "body_traversal_items": len(raw_body_items),
        },
        "layout_atom_count": atom_counter,
        "items_without_page_provenance_count": len(no_page_items),
        "items_without_page_provenance": no_page_items,
        "metadata": {
            "canonical_atom_source": "document.texts only",
            "body_traversal_saved_separately": (
                "docling_body_traversal_raw.json"
            ),
            "contract": (
                "Extraction-only layout JSON. No clauses, sections, "
                "appendix scopes, document tree, or semantic links are "
                "inferred in this stage."
            ),
        },
    }

    raw = {
        "docling_text_items_raw": raw_text_items,
        "docling_body_traversal_raw": raw_body_items,
        "docling_tables_raw": raw_table_items,
        "items_without_page_provenance": no_page_items,
    }

    return canonical, raw


def split_clear_inline_bilingual(text: str) -> dict[str, str | None]:
    """
    Only split simple EN / RU or RU / EN pair. Complex mixed atoms stay visible
    in both language views with needs_review=true.
    """
    text = normalize_text(text)
    if not text or " / " not in text:
        return {"ru": None, "en": None}

    left, right = [normalize_text(part) for part in text.split(" / ", 1)]
    left_language = classify_language(left)
    right_language = classify_language(right)

    if left_language == "en" and right_language == "ru":
        return {"en": left, "ru": right}
    if left_language == "ru" and right_language == "en":
        return {"ru": left, "en": right}

    return {"ru": None, "en": None}


def project_atom(
    atom: dict[str, Any],
    target_language: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    source_language = atom["language"]

    base = {
        "projection_id": f"{target_language}:{atom['element_id']}",
        "source_element_ids": [atom["element_id"]],
        "page": atom["page"],
        "bbox": atom["bbox"],
        "reading_order": atom["reading_order"],
        "text": atom["text"],
        "marker": atom["marker"],
        "language": target_language,
        "label": atom["label"],
        "parent_ref": atom["parent_ref"],
        "is_marker_only": atom["is_marker_only"],
        "formatting": atom["formatting"],
        "style": atom["style"],
        "source": atom["source"],
    }

    if source_language == target_language:
        return {
            **base,
            "projection_method": "native_language_atom",
            "projection_confidence": 0.99,
            "needs_review": False,
        }, None

    if source_language == "shared":
        return {
            **base,
            "projection_method": "shared_layout_atom",
            "projection_confidence": 0.99,
            "needs_review": False,
        }, None

    if source_language == "mixed":
        text = split_clear_inline_bilingual(atom["text"]).get(target_language)

        if text:
            return {
                **base,
                "text": text,
                "projection_method": "split_clear_inline_bilingual_atom",
                "projection_confidence": 0.90,
                "needs_review": False,
            }, None

        unresolved = {
            "source_element_id": atom["element_id"],
            "page": atom["page"],
            "bbox": atom["bbox"],
            "marker": atom["marker"],
            "label": atom["label"],
            "text": atom["text"],
            "reason": "complex_mixed_atom_not_safely_split",
            "target_language": target_language,
        }

        return {
            **base,
            "projection_method": "unresolved_mixed_atom_preserved",
            "projection_confidence": 0.0,
            "needs_review": True,
            "review_reason": unresolved["reason"],
        }, unresolved

    return None, None


def build_monolingual_projection(
    canonical: dict[str, Any],
    target_language: str,
) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    source_count = 0
    projected_count = 0
    projected_marker_count = 0

    for page in canonical["pages"]:
        atoms: list[dict[str, Any]] = []

        for source_atom in page["atoms"]:
            source_count += 1
            projected, unresolved_record = project_atom(
                source_atom,
                target_language,
            )

            if projected is not None:
                atoms.append(projected)
                projected_count += 1
                if projected["is_marker_only"]:
                    projected_marker_count += 1

            if unresolved_record is not None:
                unresolved.append(unresolved_record)

        pages.append(
            {
                "page_number": page["page_number"],
                "width": page["width"],
                "height": page["height"],
                "atoms": atoms,
            }
        )

    return {
        "schema_version": "monolingual_layout_projection_v3",
        "language": target_language,
        "source_canonical_layout": canonical["source_pdf"],
        "page_count": canonical["page_count"],
        "pages": pages,
        "unresolved_mixed_atoms": unresolved,
        "validation": {
            "source_atom_count": source_count,
            "projected_atom_count": projected_count,
            "projected_marker_only_atom_count": projected_marker_count,
            "unresolved_mixed_atom_count": len(unresolved),
            "contract": (
                "Language-only layout projection. No clauses, sections, "
                "appendix scopes, document tree, or semantic links are "
                "inferred."
            ),
        },
    }


def make_report(
    canonical: dict[str, Any],
    ru: dict[str, Any],
    en: dict[str, Any],
) -> str:
    atoms = [
        atom
        for page in canonical["pages"]
        for atom in page["atoms"]
    ]
    languages = Counter(atom["language"] for atom in atoms)
    labels = Counter(atom["label"] or "unknown" for atom in atoms)
    marker_count = sum(1 for atom in atoms if atom["is_marker_only"])
    explicit_marker_count = sum(
        1 for atom in atoms if atom["marker"] is not None
    )

    lines = [
        "# Canonical bilingual layout export v3",
        "",
        f"- Source PDF: `{canonical['source_pdf']}`",
        f"- Pages: {canonical['page_count']}",
        f"- Canonical layout atoms: {canonical['layout_atom_count']}",
        f"- Explicit Docling marker fields: {explicit_marker_count}",
        f"- Marker-only atoms: {marker_count}",
        (
            "- Source counts: "
            + ", ".join(
                f"`{key}`={value}"
                for key, value in canonical["source_item_counts"].items()
            )
        ),
        (
            "- Items without page provenance: "
            f"{canonical['items_without_page_provenance_count']}"
        ),
        f"- RU layout atoms: {ru['validation']['projected_atom_count']}",
        f"- EN layout atoms: {en['validation']['projected_atom_count']}",
        (
            "- RU projected marker-only atoms: "
            f"{ru['validation']['projected_marker_only_atom_count']}"
        ),
        (
            "- EN projected marker-only atoms: "
            f"{en['validation']['projected_marker_only_atom_count']}"
        ),
        (
            "- RU unresolved mixed atoms: "
            f"{ru['validation']['unresolved_mixed_atom_count']}"
        ),
        (
            "- EN unresolved mixed atoms: "
            f"{en['validation']['unresolved_mixed_atom_count']}"
        ),
        "",
        "## Language distribution",
        "",
    ]

    for language, count in sorted(languages.items()):
        lines.append(f"- `{language}`: {count}")

    lines.extend(["", "## Label distribution", ""])

    for label, count in sorted(labels.items()):
        lines.append(f"- `{label}`: {count}")

    lines.extend(
        [
            "",
            "## Contract",
            "",
            "- Canonical atom layer comes only from `document.texts`.",
            "- Attached markers and `marker` fields are retained.",
            "- Body traversal is written separately and is not mixed into "
            "layout atoms.",
            "- No clauses, headings hierarchy, appendix scopes, page maps, "
            "or document tree are inferred.",
            "- Complex bilingual atoms are preserved and flagged rather "
            "than deleted.",
        ]
    )

    return "\n".join(lines)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(json_safe(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Convert bilingual PDF to generic canonical layout JSON and "
            "RU/EN layout projections without document-structure inference."
        )
    )
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()

    if not input_path.exists():
        print(f"Input PDF not found: {input_path}", file=sys.stderr)
        return 2

    print(f"Input: {input_path}")
    print("1/4 Converting PDF and extracting canonical Docling text atoms...")

    try:
        canonical, raw = build_canonical_layout(input_path)
    except Exception as exc:
        print(f"Conversion failed: {exc}", file=sys.stderr)
        return 3

    print("2/4 Building Russian layout projection...")
    ru_projection = build_monolingual_projection(canonical, "ru")

    print("3/4 Building English layout projection...")
    en_projection = build_monolingual_projection(canonical, "en")

    print("4/4 Writing artifacts...")

    write_json(output_dir / "canonical_layout.json", canonical)
    write_json(output_dir / "docling_items_raw.json", raw)
    write_json(output_dir / "ru_layout.json", ru_projection)
    write_json(output_dir / "en_layout.json", en_projection)

    report = make_report(canonical, ru_projection, en_projection)
    (output_dir / "layout_export_report.md").write_text(
        report,
        encoding="utf-8",
    )

    print()
    print("Generated:")
    for filename in (
        "canonical_layout.json",
        "docling_items_raw.json",
        "ru_layout.json",
        "en_layout.json",
        "layout_export_report.md",
    ):
        print(f"  {output_dir / filename}")

    print()
    print(
        "Canonical atoms:",
        canonical["layout_atom_count"],
        "| explicit markers:",
        sum(
            1
            for page in canonical["pages"]
            for atom in page["atoms"]
            if atom["marker"] is not None
        ),
        "| marker-only:",
        sum(
            1
            for page in canonical["pages"]
            for atom in page["atoms"]
            if atom["is_marker_only"]
        ),
    )
    print(
        "RU projection:",
        ru_projection["validation"]["projected_atom_count"],
        "| marker-only:",
        ru_projection["validation"]["projected_marker_only_atom_count"],
        "| unresolved mixed:",
        ru_projection["validation"]["unresolved_mixed_atom_count"],
    )
    print(
        "EN projection:",
        en_projection["validation"]["projected_atom_count"],
        "| marker-only:",
        en_projection["validation"]["projected_marker_only_atom_count"],
        "| unresolved mixed:",
        en_projection["validation"]["unresolved_mixed_atom_count"],
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

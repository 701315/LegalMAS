#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pymupdf
from docling.document_converter import DocumentConverter


DEFAULT_INPUT = (
    "/srv/steloom-dev/docs/"
    "Simonova _ SPA _ Property _ execution _version (full).pdf"
)
DEFAULT_OUTPUT = "/srv/steloom-dev/artifacts/docling_inspection_v2"

CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
LATIN_RE = re.compile(r"[A-Za-z]")
NUMERIC_OR_SYMBOLIC_RE = re.compile(r"^[\s\d№#./()\-–—:;,+=×xX%₽$€£]+$")
ANCHOR_RE = re.compile(r"^\s*(\d+(?:\.\d+)*|[IVXLCM]+|[A-Za-zА-Яа-яЁё])(?:[.)])?\s*$")
NUMERIC_MARKER_RE = re.compile(r"^\d+(?:\.\d+)*$")
APPENDIX_RE = re.compile(r"\b(?:ПРИЛОЖЕНИЕ|APPENDIX|ANNEX|EXHIBIT|SCHEDULE)\b", re.IGNORECASE)
MONEY_DATE_RE = re.compile(
    r"(?:\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b|\b\d{1,3}(?:[\s,]\d{3})+(?:[.,]\d{2})?\b|\b(?:RUB|USD|EUR|GBP|руб\.?|₽)\b)",
    re.IGNORECASE,
)


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def numeric_anchor(value: str | None) -> str | None:
    value = normalize_text(value)
    if not value:
        return None
    value = value.rstrip(".)")
    return value if NUMERIC_MARKER_RE.fullmatch(value) else None


def language_evidence(text: str) -> dict[str, Any]:
    text = normalize_text(text)
    cyrillic_chars = len(CYRILLIC_RE.findall(text))
    latin_chars = len(LATIN_RE.findall(text))
    alphabetic_chars = cyrillic_chars + latin_chars

    if not text:
        return {
            "language": "unknown",
            "confidence": 0.0,
            "decision": "empty",
            "cyrillic_chars": 0,
            "latin_chars": 0,
            "alphabetic_chars": 0,
        }

    if alphabetic_chars == 0 or NUMERIC_OR_SYMBOLIC_RE.fullmatch(text):
        return {
            "language": "shared",
            "confidence": 1.0,
            "decision": "numeric_or_symbolic",
            "cyrillic_chars": cyrillic_chars,
            "latin_chars": latin_chars,
            "alphabetic_chars": alphabetic_chars,
        }

    cyr_ratio = cyrillic_chars / alphabetic_chars
    lat_ratio = latin_chars / alphabetic_chars

    if cyr_ratio >= 0.85:
        return {
            "language": "ru",
            "confidence": round(cyr_ratio, 3),
            "decision": "cyrillic_dominant",
            "cyrillic_chars": cyrillic_chars,
            "latin_chars": latin_chars,
            "alphabetic_chars": alphabetic_chars,
        }

    if lat_ratio >= 0.85:
        return {
            "language": "en",
            "confidence": round(lat_ratio, 3),
            "decision": "latin_dominant",
            "cyrillic_chars": cyrillic_chars,
            "latin_chars": latin_chars,
            "alphabetic_chars": alphabetic_chars,
        }

    return {
        "language": "mixed",
        "confidence": round(max(cyr_ratio, lat_ratio), 3),
        "decision": "mixed_scripts",
        "cyrillic_chars": cyrillic_chars,
        "latin_chars": latin_chars,
        "alphabetic_chars": alphabetic_chars,
    }


def docling_bbox_to_top_left(bbox: dict[str, Any], page_height: float) -> list[float]:
    origin = str(bbox.get("coord_origin") or "").upper()
    left = float(bbox.get("l", 0.0))
    right = float(bbox.get("r", 0.0))
    top_raw = float(bbox.get("t", 0.0))
    bottom_raw = float(bbox.get("b", 0.0))

    if origin == "BOTTOMLEFT":
        top = page_height - top_raw
        bottom = page_height - bottom_raw
    else:
        top = top_raw
        bottom = bottom_raw

    return [
        round(min(left, right), 3),
        round(min(top, bottom), 3),
        round(max(left, right), 3),
        round(max(top, bottom), 3),
    ]


def pymupdf_raw_page(page: pymupdf.Page) -> dict[str, Any]:
    raw = page.get_text("rawdict")
    blocks: list[dict[str, Any]] = []

    for block_index, block in enumerate(raw.get("blocks", [])):
        if block.get("type") != 0:
            continue

        lines: list[dict[str, Any]] = []
        for line_index, line in enumerate(block.get("lines", [])):
            spans: list[dict[str, Any]] = []
            for span_index, span in enumerate(line.get("spans", [])):
                text = normalize_text(span.get("text"))
                if not text:
                    continue
                spans.append(
                    {
                        "span_index": span_index,
                        "text": text,
                        "bbox": [round(float(v), 3) for v in span.get("bbox", [])],
                        "font": span.get("font"),
                        "size": span.get("size"),
                        "flags": span.get("flags"),
                        "color": span.get("color"),
                    }
                )
            if spans:
                lines.append(
                    {
                        "line_index": line_index,
                        "bbox": [round(float(v), 3) for v in line.get("bbox", [])],
                        "spans": spans,
                    }
                )
        if lines:
            blocks.append(
                {
                    "block_index": block_index,
                    "bbox": [round(float(v), 3) for v in block.get("bbox", [])],
                    "lines": lines,
                }
            )

    return {
        "page": page.number + 1,
        "width": round(float(page.rect.width), 3),
        "height": round(float(page.rect.height), 3),
        "blocks": blocks,
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_provenance(
    item: dict[str, Any], page_heights: dict[int, float]
) -> tuple[int | None, list[float] | None]:
    provenance = item.get("prov") or []
    if not provenance:
        return None, None
    first = provenance[0]
    page_no = first.get("page_no")
    bbox = first.get("bbox")
    if not page_no or not bbox:
        return None, None
    page_no = int(page_no)
    page_height = page_heights.get(page_no)
    if page_height is None:
        return page_no, None
    return page_no, docling_bbox_to_top_left(bbox, page_height)


def infer_region(bbox: list[float] | None, page_width: float) -> str:
    if bbox is None or not page_width:
        return "unknown"
    x0, _, x1, _ = bbox
    center = (x0 + x1) / 2
    midpoint = page_width / 2
    band = page_width * 0.08
    if x1 < midpoint - band:
        return "left_region"
    if x0 > midpoint + band:
        return "right_region"
    if abs(center - midpoint) <= band:
        return "center_region"
    return "spanning_region"


def flatten_docling(docling: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[int, float]]:
    page_heights = {
        int(k): float(v["size"]["height"])
        for k, v in (docling.get("pages") or {}).items()
    }
    page_widths = {
        int(k): float(v["size"]["width"])
        for k, v in (docling.get("pages") or {}).items()
    }

    elements: list[dict[str, Any]] = []
    for index, item in enumerate(docling.get("texts") or []):
        page, bbox = get_provenance(item, page_heights)
        text = normalize_text(item.get("text"))
        raw_text = normalize_text(item.get("orig") or text)
        marker = normalize_text(item.get("marker")) or None
        label = str(item.get("label") or "text")
        layer = str(item.get("content_layer") or "body")
        parent = (item.get("parent") or {}).get("$ref") if isinstance(item.get("parent"), dict) else None
        evidence = language_evidence(text)

        elements.append(
            {
                "element_id": f"docling:{item.get('self_ref', f'#/texts/{index}')}",
                "docling_ref": item.get("self_ref", f"#/texts/{index}"),
                "source_index": index,
                "page": page,
                "bbox": bbox,
                "reading_order": index,
                "text": text,
                "raw_text": raw_text,
                "marker": marker,
                "marker_source": "docling_marker" if marker else None,
                "label": label,
                "content_layer": layer,
                "parent_ref": parent,
                "enumerated": bool(item.get("enumerated")),
                "language": evidence["language"],
                "language_confidence": evidence["confidence"],
                "language_evidence": evidence,
                "region_id": (
                    f"p{page}:{infer_region(bbox, page_widths.get(page, 0.0))}"
                    if page else "unknown"
                ),
                "is_furniture": layer == "furniture" or label in {"page_footer", "page_header"},
                "is_heading_candidate": label == "section_header",
                "is_list_item": label == "list_item",
            }
        )
    return elements, page_heights


def vertical_overlap(a: list[float], b: list[float]) -> float:
    return max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def attach_shared_markers(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_page: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in elements:
        if item["page"] is not None and item["bbox"] is not None and not item["is_furniture"]:
            by_page[item["page"]].append(item)

    attachments: dict[str, list[dict[str, Any]]] = defaultdict(list)
    consumed: set[str] = set()

    for page_items in by_page.values():
        for source in page_items:
            if source["language"] != "shared" or source["marker"]:
                continue
            if not numeric_anchor(source["text"]):
                continue

            sx0, st, sx1, sb = source["bbox"]
            source_center_y = (st + sb) / 2
            candidates: list[tuple[float, dict[str, Any]]] = []

            for target in page_items:
                if target["element_id"] == source["element_id"]:
                    continue
                if target["language"] not in {"ru", "en", "mixed"}:
                    continue
                if target["bbox"] is None:
                    continue

                tx0, tt, _, tb = target["bbox"]
                target_center_y = (tt + tb) / 2
                y_distance = abs(source_center_y - target_center_y)
                x_gap = tx0 - sx1
                overlap = vertical_overlap(source["bbox"], target["bbox"])

                if 0 <= x_gap <= 125 and (overlap > 0 or y_distance <= 25):
                    score = x_gap + y_distance * 2 - min(overlap, 15)
                    candidates.append((score, target))

            if candidates:
                _, target = min(candidates, key=lambda pair: pair[0])
                attachments[target["element_id"]].append(source)
                consumed.add(source["element_id"])

    output: list[dict[str, Any]] = []
    for item in elements:
        result = dict(item)
        attached = attachments.get(item["element_id"], [])
        if attached and not result["marker"]:
            prefix = " ".join(x["text"] for x in attached)
            result["marker"] = prefix
            result["marker_source"] = "adjacent_shared_marker"
            result["raw_text"] = f"{prefix} {result['raw_text']}".strip()
        result["attached_shared_marker_ids"] = [x["element_id"] for x in attached]
        result["is_attached_marker_only"] = result["element_id"] in consumed
        output.append(result)
    return output


def is_structural_shared(item: dict[str, Any]) -> bool:
    text = item["text"]
    return bool(
        numeric_anchor(item.get("marker"))
        or numeric_anchor(text)
        or APPENDIX_RE.search(text)
        or MONEY_DATE_RE.search(text)
    )


def mixed_target_hint(item: dict[str, Any], target_language: str) -> bool:
    text = item["text"]
    evidence = item["language_evidence"]
    if target_language == "ru":
        return evidence["cyrillic_chars"] > evidence["latin_chars"]
    if target_language == "en":
        return evidence["latin_chars"] > evidence["cyrillic_chars"]
    return False


def build_language_view(elements: list[dict[str, Any]], target_language: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    for item in elements:
        if item["is_furniture"] or item.get("is_attached_marker_only"):
            continue

        language = item["language"]
        include = language == target_language
        decision = "exact_language_match" if include else None

        if language == "shared" and is_structural_shared(item):
            include = True
            decision = "structural_shared"
        elif language == "mixed":
            if mixed_target_hint(item, target_language):
                include = True
                decision = "mixed_script_majority"
            else:
                unresolved.append(
                    {
                        "element_id": item["element_id"],
                        "page": item["page"],
                        "bbox": item["bbox"],
                        "text": item["text"],
                        "reason": "mixed_script_requires_alignment_or_review",
                    }
                )

        if not include:
            continue

        projected = dict(item)
        marker = projected.get("marker")
        projected["structure_text"] = (
            f"{marker} {projected['text']}".strip()
            if marker and not projected["text"].startswith(marker)
            else projected["text"]
        )
        projected["view_language"] = target_language
        projected["selection_decision"] = decision
        selected.append(projected)

    return selected, unresolved


def build_alignment_candidates(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_page: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in elements:
        if item["page"] is not None and item["bbox"] is not None and not item["is_furniture"]:
            by_page[item["page"]].append(item)

    result: list[dict[str, Any]] = []
    for page, items in sorted(by_page.items()):
        ru_items = [x for x in items if x["language"] == "ru"]
        en_items = [x for x in items if x["language"] == "en"]

        for ru in ru_items:
            candidates: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
            for en in en_items:
                overlap = vertical_overlap(ru["bbox"], en["bbox"])
                ru_center = (ru["bbox"][1] + ru["bbox"][3]) / 2
                en_center = (en["bbox"][1] + en["bbox"][3]) / 2
                y_distance = abs(ru_center - en_center)
                ru_anchor = numeric_anchor(ru.get("marker"))
                en_anchor = numeric_anchor(en.get("marker"))
                same_anchor = bool(ru_anchor and en_anchor and ru_anchor == en_anchor)

                if same_anchor or overlap > 0 or y_distance <= 32:
                    score = 0.0
                    evidence = {
                        "same_page": True,
                        "vertical_overlap": round(overlap, 3),
                        "vertical_distance": round(y_distance, 3),
                        "same_anchor": same_anchor,
                        "ru_marker": ru.get("marker"),
                        "en_marker": en.get("marker"),
                    }
                    if same_anchor:
                        score += 0.65
                    if overlap > 0:
                        score += 0.25
                    else:
                        score += max(0.0, 0.20 * (1 - y_distance / 32))
                    if ru["label"] == en["label"]:
                        score += 0.10
                    candidates.append((score, en, evidence))

            if not candidates:
                continue
            score, en, evidence = max(candidates, key=lambda item: item[0])
            if score < 0.20:
                continue
            result.append(
                {
                    "alignment_id": f"align:p{page}:{ru['element_id']}:{en['element_id']}",
                    "relation": "parallel_translation_candidate",
                    "page": page,
                    "ru_element_id": ru["element_id"],
                    "en_element_id": en["element_id"],
                    "confidence": round(min(score, 1.0), 3),
                    "evidence": evidence,
                }
            )
    return result


def anchor_inventory(elements: list[dict[str, Any]]) -> list[str]:
    anchors: set[str] = set()
    for item in elements:
        anchor = numeric_anchor(item.get("marker"))
        if anchor:
            anchors.add(anchor)
    return sorted(anchors, key=lambda x: [int(part) for part in x.split(".")])


def markdown_report(
    pdf_path: Path,
    page_count: int,
    canonical: list[dict[str, Any]],
    ru_view: list[dict[str, Any]],
    en_view: list[dict[str, Any]],
    ru_unresolved: list[dict[str, Any]],
    en_unresolved: list[dict[str, Any]],
    alignments: list[dict[str, Any]],
) -> str:
    language_counts = Counter(item["language"] for item in canonical)
    label_counts = Counter(item["label"] for item in canonical)
    ru_anchors = anchor_inventory(ru_view)
    en_anchors = anchor_inventory(en_view)
    only_ru = sorted(set(ru_anchors) - set(en_anchors))
    only_en = sorted(set(en_anchors) - set(ru_anchors))

    lines = [
        "# Bilingual canonical-document inspection v2",
        "",
        f"- Source PDF: `{pdf_path}`",
        f"- Pages: {page_count}",
        f"- Canonical atoms: {len(canonical)}",
        f"- RU view atoms: {len(ru_view)}",
        f"- EN view atoms: {len(en_view)}",
        f"- RU unresolved mixed atoms: {len(ru_unresolved)}",
        f"- EN unresolved mixed atoms: {len(en_unresolved)}",
        f"- RU↔EN alignment candidates: {len(alignments)}",
        "",
        "## Canonical language distribution",
        "",
        *[f"- `{k}`: {v}" for k, v in sorted(language_counts.items())],
        "",
        "## Canonical label distribution",
        "",
        *[f"- `{k}`: {v}" for k, v in sorted(label_counts.items())],
        "",
        "## Anchor comparison",
        "",
        f"- RU anchors ({len(ru_anchors)}): `{', '.join(ru_anchors[:120])}`",
        f"- EN anchors ({len(en_anchors)}): `{', '.join(en_anchors[:120])}`",
        f"- Only RU ({len(only_ru)}): `{', '.join(only_ru[:80])}`",
        f"- Only EN ({len(only_en)}): `{', '.join(only_en[:80])}`",
        "",
        "## First RU headings",
        "",
    ]

    for item in [x for x in ru_view if x["label"] == "section_header"][:35]:
        lines.append(
            f"- p.{item['page']} | `{item.get('marker') or '-'}` | `{item['structure_text'][:180]}`"
        )

    lines.extend(["", "## First RU numbered units", ""])
    for item in [x for x in ru_view if numeric_anchor(x.get("marker"))][:50]:
        lines.append(
            f"- p.{item['page']} | `{item['marker']}` | `{item['text'][:180]}`"
        )

    lines.extend(["", "## First unresolved mixed atoms", ""])
    for item in ru_unresolved[:25]:
        lines.append(f"- p.{item['page']} | `{item['text'][:180]}`")

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This script does not physically remove a language from the PDF.",
            "- It creates language-specific JSON views from one immutable canonical layout model.",
            "- `region_id` is geometry metadata only; it is not used as a language-selection rule.",
            "- `mixed` atoms are never silently discarded: they are selected only by script-majority or listed as unresolved.",
            "- A production adapter must additionally merge clause continuations across pages and resolve ambiguous mixed atoms through alignment/context or manual review.",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build canonical bilingual layout JSON and RU/EN document views with Docling + PyMuPDF."
    )
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    pdf_path = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    if not pdf_path.exists():
        print(f"Input PDF not found: {pdf_path}", file=sys.stderr)
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Input: {pdf_path}")

    print("1/6 PyMuPDF raw extraction...")
    pymupdf_pages: list[dict[str, Any]] = []
    with pymupdf.open(pdf_path) as pdf:
        for page in pdf:
            pymupdf_pages.append(pymupdf_raw_page(page))
        page_count = len(pdf)
    write_json(
        output_dir / "pymupdf_raw_layout.json",
        {
            "schema_version": "pymupdf_raw_v1",
            "source_pdf": str(pdf_path),
            "page_count": page_count,
            "pages": pymupdf_pages,
        },
    )

    print("2/6 Docling conversion...")
    converter = DocumentConverter()
    result = converter.convert(str(pdf_path))
    docling_path = output_dir / "docling_document.json"
    result.document.save_as_json(docling_path)

    print("3/6 Canonical atom normalization...")
    docling_payload = json.loads(docling_path.read_text(encoding="utf-8"))
    elements, _ = flatten_docling(docling_payload)
    elements = attach_shared_markers(elements)

    print("4/6 Language-neutral alignment candidates...")
    alignments = build_alignment_candidates(elements)

    canonical = {
        "schema_version": "steloom_canonical_document_prototype_v2",
        "created_at": datetime.now(UTC).isoformat(),
        "source": {
            "pdf_path": str(pdf_path),
            "page_count": page_count,
            "docling_schema": docling_payload.get("schema_name"),
            "docling_version": docling_payload.get("version"),
        },
        "coordinate_system": {
            "origin": "TOPLEFT",
            "unit": "PDF points",
            "bbox_format": "[x0, top, x1, bottom]",
        },
        "selection_principle": "language is selected from text evidence; geometry is used only for context and alignment",
        "elements": elements,
        "parallel_alignment_candidates": alignments,
    }
    write_json(output_dir / "canonical_document.json", canonical)

    print("5/6 Building RU and EN views...")
    ru_view, ru_unresolved = build_language_view(elements, "ru")
    en_view, en_unresolved = build_language_view(elements, "en")

    write_json(
        output_dir / "ru_document_view.json",
        {
            "schema_version": "steloom_language_view_prototype_v2",
            "canonical_document": "canonical_document.json",
            "analysis_language": "ru",
            "elements": ru_view,
            "unresolved_mixed_atoms": ru_unresolved,
            "anchor_inventory": anchor_inventory(ru_view),
        },
    )
    write_json(
        output_dir / "en_document_view.json",
        {
            "schema_version": "steloom_language_view_prototype_v2",
            "canonical_document": "canonical_document.json",
            "analysis_language": "en",
            "elements": en_view,
            "unresolved_mixed_atoms": en_unresolved,
            "anchor_inventory": anchor_inventory(en_view),
        },
    )

    print("6/6 Writing inspection report...")
    (output_dir / "inspection_report.md").write_text(
        markdown_report(
            pdf_path,
            page_count,
            elements,
            ru_view,
            en_view,
            ru_unresolved,
            en_unresolved,
            alignments,
        ),
        encoding="utf-8",
    )

    print("Done. Generated:")
    for name in [
        "pymupdf_raw_layout.json",
        "docling_document.json",
        "canonical_document.json",
        "ru_document_view.json",
        "en_document_view.json",
        "inspection_report.md",
    ]:
        print(f"  {output_dir / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
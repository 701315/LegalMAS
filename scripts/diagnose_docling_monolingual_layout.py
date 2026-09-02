#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_INPUT = (
    "/srv/steloom-dev/artifacts/docling_inspection_v2/"
    "canonical_document.json"
)
DEFAULT_OUTPUT = "/srv/steloom-dev/artifacts/docling_monolingual_diagnostics"

CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
LATIN_RE = re.compile(r"[A-Za-z]")
SPACE_RE = re.compile(r"\s+")

TOC_RE = re.compile(
    r"\b(?:TABLE OF CONTENTS|CONTENTS|СОДЕРЖАНИЕ)\b",
    re.IGNORECASE,
)
APPENDIX_RE = re.compile(
    r"\b(?:APPENDIX|ANNEX|EXHIBIT|SCHEDULE|ПРИЛОЖЕНИЕ)\b",
    re.IGNORECASE,
)
SIGNATURE_RE = re.compile(
    r"\b(?:ON BEHALF OF|ОТ ИМЕНИ|SIGNATURE|ПОДПИС)\b",
    re.IGNORECASE,
)
TITLE_RE = re.compile(
    r"\b(?:SALE AND PURCHASE AGREEMENT|ДОГОВОР КУПЛИ)\b",
    re.IGNORECASE,
)
NUMERIC_ANCHOR_RE = re.compile(r"^\d+(?:\.\d+)*$")
LEADING_ANCHOR_RE = re.compile(
    r"^\s*(?P<anchor>\d+(?:\.\d+)*)(?:[.)])?(?=\s|$)"
)


def normalize_text(value: Any) -> str:
    return SPACE_RE.sub(" ", str(value or "")).strip()


def text_language(text: str) -> str:
    cyrillic_count = len(CYRILLIC_RE.findall(text))
    latin_count = len(LATIN_RE.findall(text))

    if cyrillic_count and not latin_count:
        return "ru"
    if latin_count and not cyrillic_count:
        return "en"
    if cyrillic_count and latin_count:
        return "mixed"
    return "shared"


def extract_anchor(atom: dict[str, Any]) -> str | None:
    marker = normalize_text(atom.get("marker")).rstrip(".)")
    if NUMERIC_ANCHOR_RE.fullmatch(marker):
        return marker

    match = LEADING_ANCHOR_RE.match(normalize_text(atom.get("text")))
    if match:
        return match.group("anchor")

    return None


def parse_bbox(atom: dict[str, Any]) -> tuple[float | None, ...]:
    value = atom.get("bbox")

    if not isinstance(value, list) or len(value) != 4:
        return None, None, None, None, None, None

    try:
        x0, y0, x1, y1 = (float(item) for item in value)
    except (ValueError, TypeError):
        return None, None, None, None, None, None

    return x0, y0, x1, y1, round((x0 + x1) / 2, 2), round((y0 + y1) / 2, 2)


def is_furniture(atom: dict[str, Any]) -> bool:
    return bool(atom.get("is_furniture"))


def classify_document_area(atom: dict[str, Any]) -> str:
    text = normalize_text(atom.get("text"))
    page = int(atom.get("page") or 0)

    if is_furniture(atom):
        return "furniture"

    if page == 1:
        return "title_page"

    if TOC_RE.search(text) or page == 2:
        return "table_of_contents"

    if APPENDIX_RE.search(text) and page >= 12:
        return "appendix_start_candidate"

    if SIGNATURE_RE.search(text):
        return "signature_candidate"

    if TITLE_RE.search(text) and page >= 3:
        return "repeated_contract_title"

    if 3 <= page <= 10:
        return "main_contract_candidate"

    return "other"


def row_from_atom(atom: dict[str, Any]) -> dict[str, Any]:
    x0, y0, x1, y1, x_center, y_center = parse_bbox(atom)
    text = normalize_text(atom.get("text"))

    return {
        "element_id": atom.get("element_id"),
        "page": atom.get("page"),
        "reading_order": atom.get("reading_order"),
        "parent_ref": atom.get("parent_ref"),
        "label": atom.get("label"),
        "language": atom.get("language") or text_language(text),
        "detected_language": text_language(text),
        "marker_field": normalize_text(atom.get("marker")) or None,
        "recovered_anchor": extract_anchor(atom),
        "is_furniture": is_furniture(atom),
        "is_attached_marker_only": bool(atom.get("is_attached_marker_only")),
        "region_id": atom.get("region_id"),
        "area": classify_document_area(atom),
        "x0": x0,
        "y0": y0,
        "x1": x1,
        "y1": y1,
        "x_center": x_center,
        "y_center": y_center,
        "text": text,
    }


def sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            int(row["page"] or 0),
            float(row["y0"] if row["y0"] is not None else 10**9),
            float(row["x0"] if row["x0"] is not None else 10**9),
            int(row["reading_order"] or 0),
        ),
    )


def language_selectable(
    row: dict[str, Any],
    target_language: str,
) -> bool:
    return row["language"] in {target_language, "shared", "mixed"}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "element_id",
        "page",
        "reading_order",
        "parent_ref",
        "label",
        "language",
        "detected_language",
        "marker_field",
        "recovered_anchor",
        "is_furniture",
        "is_attached_marker_only",
        "region_id",
        "area",
        "x0",
        "y0",
        "x1",
        "y1",
        "x_center",
        "y_center",
        "text",
    ]

    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def markdown_escape(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def write_page_markdown(
    path: Path,
    rows: list[dict[str, Any]],
    title: str,
) -> None:
    lines = [
        f"# {title}",
        "",
        (
            "| Page | Y | X | Order | Language | Marker | Label | Area | Text |"
        ),
        "|---:|---:|---:|---:|---|---|---|---|---|",
    ]

    for row in rows:
        lines.append(
            "| {page} | {y} | {x} | {order} | {language} | {marker} | "
            "{label} | {area} | {text} |".format(
                page=markdown_escape(row["page"]),
                y=markdown_escape(row["y0"]),
                x=markdown_escape(row["x0"]),
                order=markdown_escape(row["reading_order"]),
                language=markdown_escape(row["language"]),
                marker=markdown_escape(
                    row["marker_field"] or row["recovered_anchor"] or "-"
                ),
                label=markdown_escape(row["label"]),
                area=markdown_escape(row["area"]),
                text=markdown_escape(row["text"]),
            )
        )

    path.write_text("\n".join(lines), encoding="utf-8")


def write_readable_layout(
    path: Path,
    rows: list[dict[str, Any]],
    title: str,
) -> None:
    lines = [f"# {title}", ""]

    current_page: int | None = None

    for row in rows:
        page = int(row["page"] or 0)

        if page != current_page:
            current_page = page
            lines.extend([f"## Page {page}", ""])

        marker = row["marker_field"] or row["recovered_anchor"] or "-"
        bbox_text = (
            f"x={row['x0']}..{row['x1']}, y={row['y0']}..{row['y1']}"
        )

        lines.extend(
            [
                (
                    f"`{row['element_id']}` | "
                    f"lang={row['language']} | marker={marker} | "
                    f"label={row['label']} | area={row['area']}"
                ),
                f"`{bbox_text}` | order={row['reading_order']} | "
                f"parent={row['parent_ref']}",
                row["text"],
                "",
            ]
        )

    path.write_text("\n".join(lines), encoding="utf-8")


def make_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    language_counts = Counter(row["language"] for row in rows)
    label_counts = Counter(row["label"] for row in rows)
    area_counts = Counter(row["area"] for row in rows)

    anchors = [
        {
            "page": row["page"],
            "element_id": row["element_id"],
            "language": row["language"],
            "marker": row["marker_field"],
            "recovered_anchor": row["recovered_anchor"],
            "label": row["label"],
            "text": row["text"],
        }
        for row in rows
        if row["marker_field"] or row["recovered_anchor"]
    ]

    marker_only = [
        row
        for row in rows
        if row["is_attached_marker_only"]
        or (
            (row["marker_field"] or row["recovered_anchor"])
            and len(row["text"]) <= 20
        )
    ]

    return {
        "atom_count": len(rows),
        "page_count": len({row["page"] for row in rows if row["page"]}),
        "language_distribution": dict(sorted(language_counts.items())),
        "label_distribution": dict(sorted(label_counts.items())),
        "area_distribution": dict(sorted(area_counts.items())),
        "anchors": anchors,
        "marker_only_or_near_empty_atoms": marker_only,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create safe diagnostic layout artifacts before constructing "
            "a monolingual legal-document projection."
        )
    )
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--pages",
        default="1-10",
        help="Inclusive page range for focused artifacts, e.g. 1-10.",
    )
    args = parser.parse_args()

    match = re.fullmatch(r"(\d+)-(\d+)", args.pages)
    if not match:
        print("--pages must have format FIRST-LAST, for example 1-10", file=sys.stderr)
        return 2

    first_page = int(match.group(1))
    last_page = int(match.group(2))
    if first_page > last_page:
        print("First page must not exceed last page.", file=sys.stderr)
        return 2

    input_path = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()

    if not input_path.exists():
        print(f"Input does not exist: {input_path}", file=sys.stderr)
        return 3

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    atoms = payload.get("elements") or []

    if not atoms:
        print("Input JSON has no .elements array.", file=sys.stderr)
        return 4

    rows = sort_rows([row_from_atom(atom) for atom in atoms])
    focused_rows = [
        row
        for row in rows
        if first_page <= int(row["page"] or 0) <= last_page
    ]

    ru_rows = [
        row for row in focused_rows if language_selectable(row, "ru")
    ]
    en_rows = [
        row for row in focused_rows if language_selectable(row, "en")
    ]

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Input: {input_path}")
    print(f"Canonical atoms: {len(rows)}")
    print(f"Focused pages: {first_page}-{last_page}")
    print("1/4 Writing complete JSON and CSV diagnostic tables...")

    write_json(output_dir / "all_atoms.json", rows)
    write_csv(output_dir / "all_atoms.csv", rows)
    write_json(output_dir / f"pages_{first_page}_{last_page}_atoms.json", focused_rows)
    write_csv(output_dir / f"pages_{first_page}_{last_page}_atoms.csv", focused_rows)

    print("2/4 Writing RU and EN selectable layout tables...")

    write_json(output_dir / f"ru_pages_{first_page}_{last_page}.json", ru_rows)
    write_json(output_dir / f"en_pages_{first_page}_{last_page}.json", en_rows)
    write_csv(output_dir / f"ru_pages_{first_page}_{last_page}.csv", ru_rows)
    write_csv(output_dir / f"en_pages_{first_page}_{last_page}.csv", en_rows)

    print("3/4 Writing readable page-order reports...")

    write_readable_layout(
        output_dir / f"pages_{first_page}_{last_page}_layout.txt",
        focused_rows,
        f"Canonical layout: pages {first_page}-{last_page}",
    )
    write_readable_layout(
        output_dir / f"ru_pages_{first_page}_{last_page}_layout.txt",
        ru_rows,
        f"RU-selectable layout: pages {first_page}-{last_page}",
    )
    write_readable_layout(
        output_dir / f"en_pages_{first_page}_{last_page}_layout.txt",
        en_rows,
        f"EN-selectable layout: pages {first_page}-{last_page}",
    )
    write_page_markdown(
        output_dir / f"pages_{first_page}_{last_page}_layout.md",
        focused_rows,
        f"Canonical layout table: pages {first_page}-{last_page}",
    )

    print("4/4 Writing summaries...")

    summary = {
        "source": str(input_path),
        "focused_pages": [first_page, last_page],
        "all_atoms": make_summary(rows),
        "focused_atoms": make_summary(focused_rows),
        "ru_selectable_focused_atoms": make_summary(ru_rows),
        "en_selectable_focused_atoms": make_summary(en_rows),
    }
    write_json(output_dir / "diagnostic_summary.json", summary)

    print()
    print("Generated:")
    for name in [
        "all_atoms.json",
        "all_atoms.csv",
        f"pages_{first_page}_{last_page}_atoms.json",
        f"pages_{first_page}_{last_page}_atoms.csv",
        f"ru_pages_{first_page}_{last_page}.json",
        f"ru_pages_{first_page}_{last_page}.csv",
        f"en_pages_{first_page}_{last_page}.json",
        f"en_pages_{first_page}_{last_page}.csv",
        f"pages_{first_page}_{last_page}_layout.txt",
        f"ru_pages_{first_page}_{last_page}_layout.txt",
        f"en_pages_{first_page}_{last_page}_layout.txt",
        f"pages_{first_page}_{last_page}_layout.md",
        "diagnostic_summary.json",
    ]:
        print(f"  {output_dir / name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

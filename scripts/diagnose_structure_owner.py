#!/usr/bin/env python3
"""
Diagnose ownership of structure/chunking errors from exported stage JSONs.

Purpose:
- locate whether the failure starts at segmentation, structure/heading layer,
  or chunk planning;
- inspect a suspicious numbered clause (e.g. 3.8);
- inspect follow-up headings (e.g. 4 / 4.1 / 4.1.1);
- detect overly wide chunks under a section prefix (e.g. section 2).

This script is intentionally standalone and tolerant to different JSON shapes:
- it recursively scans payloads;
- finds dicts that look like segments / elements / chunks;
- prints evidence and a heuristic diagnosis.

Recommended inputs:
- segments JSON payload (if available)
- structured/elements JSON payload
- chunks JSON payload

Usage example:
    python scripts/diagnose_structure_owner.py \
      --segments-json /tmp/segments.json \
      --elements-json /tmp/structured.json \
      --chunks-json /tmp/chunks.json \
      --focus 3.8 \
      --follow-prefix 4 \
      --chunk-prefix 2
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


HEADING_UID_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s+(?=\S)")
INLINE_UID_RE = re.compile(r"(?<!\d)(\d+(?:\.\d+)+)(?!\d)")

APPENDIX_WORD_RE = re.compile(
    r"(appendix|appendices|schedule|schedules|exhibit|exhibits|annex|annexes|annexure|annexures|attachment|attachments|приложени)",
    re.IGNORECASE,
)

AMENDMENT_WORD_RE = re.compile(
    r"(amendment|amendments|addendum|addenda|supplemental\s+agreement|supplemental\s+agreements|дополнительн\w+\s+соглашен\w+|дополнен\w+)",
    re.IGNORECASE,
)

CHUNK_TEXT_KEYS = (
    "exact_text",
    "retrieval_text",
    "text",
    "content",
    "body",
    "chunk_text",
)
CHUNK_KIND_KEYS = (
    "kind",
    "level",
    "chunk_kind",
    "role",
)
SEGMENT_TYPES_OF_INTEREST = {"appendix", "amendment"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_dicts(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from iter_dicts(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from iter_dicts(item)


def safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def shorten(text: str, limit: int = 140) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def parse_heading_uid(text: str) -> str | None:
    text = normalize_text(text)
    if not text:
        return None
    match = HEADING_UID_RE.match(text)
    if not match:
        return None
    return match.group(1)


def keyword_flags(text: str) -> list[str]:
    flags: list[str] = []
    if APPENDIX_WORD_RE.search(text):
        flags.append("appendix_kw")
    if AMENDMENT_WORD_RE.search(text):
        flags.append("amendment_kw")
    return flags


def is_segment_dict(d: dict[str, Any]) -> bool:
    return (
        "segment_type" in d
        and any(k in d for k in ("page_start", "page_end"))
        and any(k in d for k in ("segment_id", "segment_order", "document_id"))
    )


def is_element_dict(d: dict[str, Any]) -> bool:
    return "text" in d and any(k in d for k in ("page", "element_id", "element_index"))


def is_chunk_dict(d: dict[str, Any]) -> bool:
    has_chunkish_id = any(
        k in d for k in ("chunk_id", "display_title", "kind", "level", "chunk_kind")
    )
    has_text = any(k in d for k in CHUNK_TEXT_KEYS)
    return has_chunkish_id and has_text


def segment_signature(d: dict[str, Any]) -> tuple[Any, ...]:
    return (
        d.get("segment_id"),
        d.get("segment_order"),
        d.get("segment_type"),
        d.get("page_start"),
        d.get("page_end"),
        d.get("segment_title"),
    )


def element_signature(d: dict[str, Any]) -> tuple[Any, ...]:
    return (
        d.get("element_id"),
        d.get("page"),
        d.get("text"),
    )


def chunk_signature(d: dict[str, Any]) -> tuple[Any, ...]:
    return (
        d.get("chunk_id"),
        d.get("kind"),
        d.get("level"),
        d.get("display_title"),
        extract_chunk_text(d)[:120],
    )


def dedupe_dicts(
    items: list[dict[str, Any]],
    signature_fn,
) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        sig = signature_fn(item)
        if sig in seen:
            continue
        seen.add(sig)
        result.append(item)
    return result


def collect_segments(payload: Any) -> list[dict[str, Any]]:
    return dedupe_dicts(
        [d for d in iter_dicts(payload) if is_segment_dict(d)],
        segment_signature,
    )


def collect_elements(payload: Any) -> list[dict[str, Any]]:
    return dedupe_dicts(
        [d for d in iter_dicts(payload) if is_element_dict(d)],
        element_signature,
    )


def collect_chunks(payload: Any) -> list[dict[str, Any]]:
    return dedupe_dicts(
        [d for d in iter_dicts(payload) if is_chunk_dict(d)],
        chunk_signature,
    )


def derive_segments_from_elements(
    elements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not elements:
        return []

    if not any(
        ("segment_id" in el or "segment_order" in el or "segment_type" in el)
        for el in elements
    ):
        return []

    result: list[dict[str, Any]] = []

    def seg_sig(el: dict[str, Any]) -> tuple[Any, ...]:
        return (
            el.get("segment_id"),
            el.get("segment_order"),
            el.get("segment_type"),
        )

    start = 0
    current_sig = seg_sig(elements[0])

    for i in range(1, len(elements)):
        if seg_sig(elements[i]) != current_sig:
            result.append(_build_segment_stub_from_range(elements, start, i))
            start = i
            current_sig = seg_sig(elements[i])

    result.append(_build_segment_stub_from_range(elements, start, len(elements)))
    return result


def _build_segment_stub_from_range(
    elements: list[dict[str, Any]],
    start: int,
    end: int,
) -> dict[str, Any]:
    slice_ = elements[start:end]
    first = slice_[0]
    last = slice_[-1]
    return {
        "segment_id": first.get("segment_id"),
        "segment_order": first.get("segment_order"),
        "segment_type": first.get("segment_type"),
        "page_start": first.get("page"),
        "page_end": last.get("page"),
        "segment_title": None,
        "scope_name": first.get("scope"),
        "_derived_from_elements": True,
    }


def sort_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        segments,
        key=lambda d: (
            safe_int(d.get("segment_order")) if safe_int(d.get("segment_order")) is not None else 10**9,
            safe_int(d.get("page_start")) if safe_int(d.get("page_start")) is not None else 10**9,
        ),
    )


def extract_chunk_text(chunk: dict[str, Any]) -> str:
    for key in CHUNK_TEXT_KEYS:
        value = normalize_text(chunk.get(key))
        if value:
            return value
    return ""


def extract_chunk_kind(chunk: dict[str, Any]) -> str:
    for key in CHUNK_KIND_KEYS:
        value = normalize_text(chunk.get(key))
        if value:
            return value
    return "unknown"


def matches_focus(text: str, focus: str) -> bool:
    text = normalize_text(text)
    if not text:
        return False
    focus_norm = focus.strip().rstrip(".")
    uid = parse_heading_uid(text)
    if uid == focus_norm:
        return True
    return focus_norm.lower() in text.lower()


def find_focus_indexes(
    elements: list[dict[str, Any]],
    focus: str,
) -> list[int]:
    result: list[int] = []
    for i, el in enumerate(elements):
        if matches_focus(normalize_text(el.get("text")), focus):
            result.append(i)
    return result


def print_segments(segments: list[dict[str, Any]]) -> None:
    print("\n=== SEGMENTS ===")
    if not segments:
        print("No explicit segments found.")
        return

    for seg in sort_segments(segments):
        print(
            f"- order={seg.get('segment_order')!r} "
            f"type={seg.get('segment_type')!r} "
            f"pages={seg.get('page_start')}-{seg.get('page_end')} "
            f"scope={seg.get('scope_name')!r} "
            f"title={shorten(normalize_text(seg.get('segment_title')), 80)!r}"
            + (" [derived]" if seg.get("_derived_from_elements") else "")
        )


def print_focus_window(
    elements: list[dict[str, Any]],
    focus_index: int,
    *,
    window: int,
) -> None:
    left = max(0, focus_index - window)
    right = min(len(elements), focus_index + window + 1)

    print("\n=== ELEMENT WINDOW AROUND FOCUS ===")
    for i in range(left, right):
        el = elements[i]
        text = normalize_text(el.get("text"))
        uid = parse_heading_uid(text)
        flags = keyword_flags(text)
        marker = ">>" if i == focus_index else "  "
        print(
            f"{marker} idx={i:04d} "
            f"page={el.get('page')!r} "
            f"seg_type={el.get('segment_type')!r} "
            f"seg_order={el.get('segment_order')!r} "
            f"el_type={el.get('element_type')!r} "
            f"sem_type={el.get('semantic_type')!r} "
            f"uid={uid!r} "
            f"flags={flags} "
            f"text={shorten(text, 180)!r}"
        )


def collect_followup_headings(
    elements: list[dict[str, Any]],
    focus_index: int,
    follow_prefix: str,
    *,
    limit: int = 20,
) -> list[tuple[int, dict[str, Any], str]]:
    result: list[tuple[int, dict[str, Any], str]] = []
    prefix = follow_prefix.strip().rstrip(".")

    for i in range(focus_index + 1, len(elements)):
        el = elements[i]
        text = normalize_text(el.get("text"))
        uid = parse_heading_uid(text)
        if not uid:
            continue
        if uid == prefix or uid.startswith(prefix + "."):
            result.append((i, el, uid))
        if len(result) >= limit:
            break

    return result


def print_followup_headings(
    elements: list[dict[str, Any]],
    focus_index: int,
    follow_prefix: str,
) -> list[tuple[int, dict[str, Any], str]]:
    rows = collect_followup_headings(elements, focus_index, follow_prefix)

    print("\n=== FOLLOW-UP HEADINGS ===")
    if not rows:
        print(f"No follow-up headings found for prefix {follow_prefix!r}.")
        return rows

    for i, el, uid in rows:
        text = normalize_text(el.get("text"))
        print(
            f"- idx={i:04d} "
            f"page={el.get('page')!r} "
            f"uid={uid!r} "
            f"seg_type={el.get('segment_type')!r} "
            f"seg_order={el.get('segment_order')!r} "
            f"el_type={el.get('element_type')!r} "
            f"sem_type={el.get('semantic_type')!r} "
            f"text={shorten(text, 160)!r}"
        )

    return rows


def direct_child_uids_in_text(text: str, prefix: str) -> list[str]:
    prefix_norm = prefix.strip().rstrip(".")
    direct_depth = prefix_norm.count(".") + 1

    found = sorted(
        {
            uid
            for uid in INLINE_UID_RE.findall(text)
            if uid.startswith(prefix_norm + ".") and uid.count(".") == direct_depth
        }
    )
    return found


def analyze_chunk_overmerge(
    chunks: list[dict[str, Any]],
    prefix: str,
) -> list[dict[str, Any]]:
    suspicious: list[dict[str, Any]] = []

    for chunk in chunks:
        text = extract_chunk_text(chunk)
        if not text:
            continue

        direct_children = direct_child_uids_in_text(text, prefix)
        if len(direct_children) < 2:
            continue

        suspicious.append(
            {
                "chunk_id": chunk.get("chunk_id"),
                "kind": extract_chunk_kind(chunk),
                "display_title": chunk.get("display_title"),
                "direct_children": direct_children,
                "text_preview": shorten(text, 220),
            }
        )

    return suspicious


def print_chunk_analysis(
    chunks: list[dict[str, Any]],
    prefix: str,
) -> list[dict[str, Any]]:
    print("\n=== CHUNK ANALYSIS ===")
    if not chunks:
        print("No chunk-like payloads found.")
        return []

    suspicious = analyze_chunk_overmerge(chunks, prefix)
    if not suspicious:
        print(f"No suspicious over-merged chunks detected for section prefix {prefix!r}.")
        return []

    print(f"Suspicious chunks for section prefix {prefix!r}: {len(suspicious)}")
    for row in suspicious[:20]:
        print(
            f"- chunk_id={row['chunk_id']!r} "
            f"kind={row['kind']!r} "
            f"title={shorten(normalize_text(row['display_title']), 80)!r} "
            f"children={row['direct_children']} "
            f"text={row['text_preview']!r}"
        )

    if len(suspicious) > 20:
        print(f"... and {len(suspicious) - 20} more")

    return suspicious


def diagnose_owner(
    *,
    segments: list[dict[str, Any]],
    elements: list[dict[str, Any]],
    focus_index: int | None,
    followup_rows: list[tuple[int, dict[str, Any], str]],
    suspicious_chunks: list[dict[str, Any]],
) -> None:
    print("\n=== HEURISTIC DIAGNOSIS ===")

    if focus_index is None:
        print("- Focus clause not found in elements; cannot localize owner reliably.")
        return

    focus_el = elements[focus_index]
    focus_page = safe_int(focus_el.get("page"))
    focus_seg_type = normalize_text(focus_el.get("segment_type")) or None

    follow_seg_types = Counter(
        normalize_text(el.get("segment_type")) or "<none>"
        for _, el, _ in followup_rows
    )

    first_non_contract_segment = None
    for seg in sort_segments(segments):
        seg_type = normalize_text(seg.get("segment_type"))
        if seg_type in SEGMENT_TYPES_OF_INTEREST:
            first_non_contract_segment = seg
            break

    segmenter_evidence: list[str] = []
    structure_evidence: list[str] = []
    chunk_evidence: list[str] = []

    if first_non_contract_segment is not None:
        seg_type = normalize_text(first_non_contract_segment.get("segment_type"))
        seg_start = safe_int(first_non_contract_segment.get("page_start"))
        if focus_page is not None and seg_start is not None and seg_start >= focus_page:
            segmenter_evidence.append(
                f"first non-contract segment is {seg_type!r} starting at page {seg_start}"
            )

    if followup_rows:
        poisoned_followups = [
            (uid, normalize_text(el.get("segment_type")) or "<none>")
            for _, el, uid in followup_rows
            if normalize_text(el.get("segment_type")) in SEGMENT_TYPES_OF_INTEREST
        ]
        if poisoned_followups:
            segmenter_evidence.append(
                "follow-up headings after focus already carry non-contract segment_type: "
                + ", ".join(f"{uid}->{seg_type}" for uid, seg_type in poisoned_followups[:10])
            )

        appendix_like_structure_rows = [
            uid
            for _, el, uid in followup_rows
            if "appendix" in normalize_text(el.get("element_type")).lower()
            or "appendix" in normalize_text(el.get("semantic_type")).lower()
            or "amendment" in normalize_text(el.get("element_type")).lower()
            or "amendment" in normalize_text(el.get("semantic_type")).lower()
        ]
        if appendix_like_structure_rows:
            structure_evidence.append(
                "follow-up headings have appendix/amendment-like structure labels: "
                + ", ".join(appendix_like_structure_rows[:10])
            )

    focus_text = normalize_text(focus_el.get("text"))
    if keyword_flags(focus_text):
        structure_evidence.append(
            f"focus clause contains catalog-like keywords: {keyword_flags(focus_text)}"
        )

    if suspicious_chunks:
        chunk_evidence.append(
            f"{len(suspicious_chunks)} chunks contain multiple sibling headings under one section"
        )

    if segmenter_evidence:
        print("- LIKELY PRIMARY OWNER: SEGMENTER")
        for item in segmenter_evidence:
            print(f"  * {item}")
        print("  * Universal fix direction:")
        print(
            "    reject body-internal appendix/amendment listings as segment boundaries "
            "when numbered contract progression continues (e.g. 3.8 -> 4 -> 4.1) "
            "and there is no real segment-start context."
        )

    elif structure_evidence:
        print("- LIKELY PRIMARY OWNER: STRUCTURE / HEADING LAYER")
        for item in structure_evidence:
            print(f"  * {item}")
        print("  * Universal fix direction:")
        print(
            "    add hard negatives for appendix/amendment-like heading interpretation "
            "inside numbered body progression unless strong page-start / boundary context exists."
        )

    else:
        print("- No strong segmentation/structure owner evidence from provided payloads.")

    if chunk_evidence:
        print("- SECONDARY OWNER PRESENT: CHUNK PLANNER")
        for item in chunk_evidence:
            print(f"  * {item}")
        print("  * Universal fix direction:")
        print(
            "    add sibling-span guard so one chunk does not absorb too many direct "
            "siblings (e.g. 2.1-2.4 or 2.5-2.12) when structure continues cleanly."
        )

    if not segmenter_evidence and not structure_evidence and not chunk_evidence:
        print(
            "- Script found no decisive evidence. In that case export richer stage payloads: "
            "segments, structured elements, and chunks."
        )

    print("\n--- Additional context ---")
    print(f"- focus_page={focus_page!r}")
    print(f"- focus_segment_type={focus_seg_type!r}")
    print(f"- followup_segment_types={dict(follow_seg_types)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--segments-json", type=Path, help="Exported segments payload JSON")
    parser.add_argument("--elements-json", type=Path, help="Exported structured/elements payload JSON")
    parser.add_argument("--chunks-json", type=Path, help="Exported chunks payload JSON")
    parser.add_argument("--focus", type=str, default="3.8", help="Suspicious focus clause/heading, e.g. 3.8")
    parser.add_argument(
        "--follow-prefix",
        type=str,
        default="4",
        help="Follow-up heading prefix to inspect after focus, e.g. 4",
    )
    parser.add_argument(
        "--chunk-prefix",
        type=str,
        default="2",
        help="Section prefix to inspect for chunk over-merge, e.g. 2",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=8,
        help="How many elements to print before/after focus",
    )
    args = parser.parse_args()

    if not args.segments_json and not args.elements_json and not args.chunks_json:
        print("Provide at least one of --segments-json / --elements-json / --chunks-json", file=sys.stderr)
        return 2

    segments: list[dict[str, Any]] = []
    elements: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []

    if args.segments_json:
        segments_payload = load_json(args.segments_json)
        segments = collect_segments(segments_payload)

    if args.elements_json:
        elements_payload = load_json(args.elements_json)
        elements = collect_elements(elements_payload)

        if not segments:
            segments = derive_segments_from_elements(elements)

    if args.chunks_json:
        chunks_payload = load_json(args.chunks_json)
        chunks = collect_chunks(chunks_payload)

    print("=== SUMMARY ===")
    print(f"- segments_found={len(segments)}")
    print(f"- elements_found={len(elements)}")
    print(f"- chunks_found={len(chunks)}")
    print(f"- focus={args.focus!r}")
    print(f"- follow_prefix={args.follow_prefix!r}")
    print(f"- chunk_prefix={args.chunk_prefix!r}")

    print_segments(segments)

    focus_index: int | None = None
    followup_rows: list[tuple[int, dict[str, Any], str]] = []

    if elements:
        focus_indexes = find_focus_indexes(elements, args.focus)
        print("\n=== FOCUS SEARCH ===")
        print(f"- focus_matches={focus_indexes[:20]}{' ...' if len(focus_indexes) > 20 else ''}")

        if focus_indexes:
            focus_index = focus_indexes[0]
            print_focus_window(elements, focus_index, window=args.window)
            followup_rows = print_followup_headings(elements, focus_index, args.follow_prefix)
        else:
            print(f"- Focus {args.focus!r} was not found in provided elements.")
    else:
        print("\n=== ELEMENT ANALYSIS ===")
        print("No element-like payloads found.")

    suspicious_chunks = print_chunk_analysis(chunks, args.chunk_prefix)

    diagnose_owner(
        segments=segments,
        elements=elements,
        focus_index=focus_index,
        followup_rows=followup_rows,
        suspicious_chunks=suspicious_chunks,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())



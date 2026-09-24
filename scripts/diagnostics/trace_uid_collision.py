"""
Полный trace кандидатов с заданными raw_uid на конкретном layout-файле.

Использование:
    python scripts/diagnostics/trace_uid_collision.py \
        --layout /tmp/layout_d37201cc.json \
        --doc-id d37201cc-c650-472d-ae88-3e9a9ae0743d \
        --uids 7.1 7.2 7.3

Выводит полное состояние каждого кандидата ДО и ПОСЛЕ dedup:
- element_type, semantic_element_type
- raw_text, parsed_uid, parsed_title
- decision, reason, score (полный)
- accept_reasons, reject_reasons
- toc_match_type, toc_match_score, continuity_bonus
- _preamble_zone, toc_guard_decision, possible_toc, strong_toc_confirmation
- соседние элементы (idx-1, idx+1)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.structure.element_classifier import classify_elements
from services.structure.toc_parser import detect_toc_block
import services.structure._heading_builder._core as core


def _format_meta(meta: dict, keys: list[str]) -> str:
    parts = []
    for k in keys:
        v = meta.get(k)
        if v is None or v == "":
            continue
        parts.append(f"{k}={v!r}")
    return " ".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--layout", required=True, help="Путь к JSON layout-файла")
    parser.add_argument("--doc-id", required=True)
    parser.add_argument("--uids", nargs="+", required=True)
    args = parser.parse_args()

    data = json.loads(Path(args.layout).read_text())
    els = data.get("elements") or []

    classified = classify_elements(els, document_id=args.doc_id)

    r = detect_toc_block(classified)
    print(f"TOC: detected={r.detected} start={r.start_index} end={r.end_index} reason={r.reason}\n")

    for i, el in enumerate(classified):
        el.setdefault("scope", "main_contract")
        el.setdefault("segment_id", "seg-diag")
        el.setdefault("segment_type", "contract")
        el.setdefault("segment_order", 0)
        if r.detected and r.start_index is not None and r.end_index is not None:
            if i < r.start_index:
                zone = "pre_toc"
            elif i < r.end_index:
                zone = "in_toc"
            else:
                zone = "post_toc"
        else:
            zone = "no_toc"
        el["_preamble_zone"] = zone

    # PRE-dedup
    original = core._select_best_candidates_by_uid
    core._select_best_candidates_by_uid = lambda cands, doc_id: cands
    try:
        pre = core.collect_scored_heading_candidates(classified, document_id=args.doc_id)
    finally:
        core._select_best_candidates_by_uid = original

    post = core.collect_scored_heading_candidates(classified, document_id=args.doc_id)

    wanted = set(args.uids)

    def _dump(title: str, scored: list) -> None:
        print(f"=== {title}: {len(scored)} кандидатов ===")
        for s in scored:
            meta = s.metadata or {}
            raw_uid = str(meta.get("raw_uid") or s.uid or "")
            if raw_uid not in wanted:
                continue
            print(f"\n--- uid={raw_uid} elem_i={s.elem_i} page={s.page} ---")
            print(f"  decision={s.decision!r} reason={s.reason!r}")
            print(f"  score={s.score!r} (полный)")
            print(f"  raw_text={s.raw_text[:120]!r}")
            print(f"  title={s.title!r}")
            print(
                "  meta: "
                + _format_meta(
                    meta,
                    [
                        "element_type",
                        "semantic_element_type",
                        "_preamble_zone",
                        "toc_match_type",
                        "toc_match_score",
                        "continuity_bonus",
                        "toc_guard_decision",
                        "body_recoverable_from_toc",
                        "possible_toc",
                        "strong_toc_confirmation",
                        "is_appendix_uid",
                        "is_root_numeric_uid",
                    ],
                )
            )
            print(f"  accept_reasons={meta.get('accept_reasons')}")
            print(f"  reject_reasons={meta.get('reject_reasons')}")

            # Соседние элементы
            for offset in (-1, 1):
                neighbor_idx = s.elem_i + offset
                if 0 <= neighbor_idx < len(els):
                    nb = els[neighbor_idx]
                    nb_text = str(nb.get("text") or "")[:90]
                    nb_page = nb.get("page")
                    nb_zone = classified[neighbor_idx].get("_preamble_zone", "")
                    print(f"  neighbor[{offset:+d}] idx={neighbor_idx} p={nb_page} zone={nb_zone!r}: {nb_text!r}")
        print()

    _dump("PRE-dedup", pre)
    _dump("POST-dedup", post)

    # Финальная сводка: кто победил
    print("=== Winners (post-dedup) ===")
    for s in post:
        meta = s.metadata or {}
        raw_uid = str(meta.get("raw_uid") or s.uid or "")
        if raw_uid in wanted:
            print(f"  uid={raw_uid}: page={s.page} raw={s.raw_text[:80]!r}")


if __name__ == "__main__":
    main()

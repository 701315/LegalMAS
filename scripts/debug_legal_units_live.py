# scripts/debug_legal_units_live.py

from __future__ import annotations

import argparse
import asyncio
import uuid
from collections import Counter
from typing import Any

from db.repositories.document_repo import DocumentRepository
from db.repositories.document_segment_repo import DocumentSegmentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.session import get_db
from engine.content.clause_tree_builder import ClauseTreeBuilder
from services.structure.legal_unit_builder import LegalUnitBuilder
from storage.artifact_store import ArtifactStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Live-build LegalUnitsSnapshot for a document and inspect extracted units."
    )
    parser.add_argument(
        "--doc-id",
        required=True,
        help="Document UUID",
    )
    parser.add_argument(
        "--version-id",
        required=False,
        help="Optional DocumentVersion UUID. If omitted, latest version is used.",
    )
    parser.add_argument(
        "--segment-id",
        required=False,
        help="Optional segment_id. If omitted, all segments are processed.",
    )
    parser.add_argument(
        "--uid-prefix",
        default="main_contract:1",
        help="Only print units whose unit_id starts with this prefix (default: main_contract:1)",
    )
    parser.add_argument(
        "--pages",
        nargs="*",
        type=int,
        default=[],
        help="Optional page filter. Example: --pages 3 4",
    )
    parser.add_argument(
        "--max-text-chars",
        type=int,
        default=240,
        help="Preview length for own/exact text",
    )
    return parser.parse_args()


def clip(text: str | None, max_chars: int) -> str:
    value = (text or "").strip()
    if not value:
        return ""
    if len(value) <= max_chars:
        return value
    return value[:max_chars].rstrip() + "…"


def unit_matches_pages(unit: Any, pages: set[int]) -> bool:
    if not pages:
        return True
    start = getattr(unit, "page_start", None)
    end = getattr(unit, "page_end", None)
    if not isinstance(start, int):
        return False
    if not isinstance(end, int):
        end = start
    return any(start <= p <= end for p in pages)


def print_header(title: str) -> None:
    print("\n" + "=" * 110)
    print(title)
    print("=" * 110)


async def main() -> None:
    args = parse_args()
    doc_id = uuid.UUID(args.doc_id)
    version_id = uuid.UUID(args.version_id) if args.version_id else None
    wanted_pages = set(args.pages)

    db_gen = get_db()
    session = await db_gen.__anext__()
    try:
        doc_repo = DocumentRepository(session)
        ver_repo = DocumentVersionRepository(session)
        seg_repo = DocumentSegmentRepository(session)
        store = ArtifactStore()

        doc = await doc_repo.get_by_id(doc_id)
        if doc is None:
            raise RuntimeError(f"Document not found: {doc_id}")

        if version_id is not None:
            version = await ver_repo.get_by_id(version_id)
            if version is None:
                raise RuntimeError(f"Version not found: {version_id}")
            if version.document_id != doc_id:
                raise RuntimeError(
                    f"Version {version_id} does not belong to document {doc_id}"
                )
        else:
            version = await ver_repo.get_latest(doc_id)
            if version is None:
                raise RuntimeError(f"Latest version not found for document {doc_id}")

        layout_ref = (
            getattr(version, "layout_primary_sanitized_ref", None)
            or getattr(version, "layout_primary_ref", None)
        )
        if not layout_ref:
            raise RuntimeError("No layout ref on document version")

        layout = store.get_json(layout_ref)
        if not isinstance(layout, dict):
            raise RuntimeError(f"Layout artifact is invalid: {layout_ref}")

        element_index = ClauseTreeBuilder.build_element_index(layout)

        segments = await seg_repo.list_by_version(version.id)
        if not segments:
            raise RuntimeError(f"No segments for version {version.id}")

        if args.segment_id:
            segments = [s for s in segments if s.segment_id == args.segment_id]
            if not segments:
                raise RuntimeError(f"Segment not found: {args.segment_id}")

        print_header("DOCUMENT / VERSION")
        print(f"document_id:         {doc.id}")
        print(f"document_version_id: {version.id}")
        print(f"filename:            {getattr(doc, 'filename', '-')}")
        print(f"layout_ref:          {layout_ref}")
        print(f"segments_count:      {len(segments)}")
        print(f"uid_prefix filter:   {args.uid_prefix!r}")
        print(f"page filter:         {sorted(wanted_pages) if wanted_pages else '-'}")

        builder = LegalUnitBuilder()

        for segment in sorted(segments, key=lambda s: int(s.segment_order)):
            if not getattr(segment, "segment_clause_tree_ref", None):
                print_header(f"SEGMENT {segment.segment_id} — NO segment_clause_tree_ref")
                continue

            clause_tree = store.get_json(segment.segment_clause_tree_ref)
            if not isinstance(clause_tree, dict):
                print_header(f"SEGMENT {segment.segment_id} — INVALID CLAUSE TREE")
                continue

            snapshot = builder.build_from_clause_tree(
                clause_tree=clause_tree,
                segment_id=segment.segment_id,
                segment_type=segment.segment_type,
                segment_order=segment.segment_order,
                is_primary_segment=bool(segment.is_primary),
                document_id=str(doc.id),
                document_version_id=str(version.id),
                element_index=element_index,
            )

            print_header(
                f"SEGMENT {segment.segment_id} | type={segment.segment_type} | order={segment.segment_order} | primary={bool(segment.is_primary)}"
            )

            print("SNAPSHOT STATS")
            print(f"  total_units:            {len(snapshot.units)}")
            print(f"  units_with_known_type:  {snapshot.units_with_known_type}")
            print(f"  units_heading_only:     {snapshot.units_heading_only}")
            print(f"  units_best_effort:      {snapshot.units_best_effort}")
            print(f"  warnings:               {snapshot.build_warnings or []}")

            unit_type_counts = Counter(getattr(u, "unit_type").value for u in snapshot.units)
            unit_class_counts = Counter(getattr(u, "unit_class", "generic_block") for u in snapshot.units)

            print("\nUNIT TYPE COUNTS")
            for k, v in sorted(unit_type_counts.items()):
                print(f"  {k}: {v}")

            print("\nUNIT CLASS COUNTS")
            for k, v in sorted(unit_class_counts.items()):
                print(f"  {k}: {v}")

            matching_units = [
                u
                for u in snapshot.units
                if (not args.uid_prefix or u.unit_id.startswith(args.uid_prefix))
                and unit_matches_pages(u, wanted_pages)
            ]

            matching_units.sort(key=lambda u: (u.page_start, u.unit_id))

            print(f"\nMATCHING UNITS ({len(matching_units)})")
            for u in matching_units:
                print("-" * 110)
                print(f"unit_id:            {u.unit_id}")
                print(f"raw_uid:            {u.raw_uid}")
                print(f"title:              {u.title!r}")
                print(f"unit_class:         {getattr(u, 'unit_class', None)!r}")
                print(f"unit_type:          {u.unit_type.value}")
                print(f"clause_function:    {u.clause_function.value}")
                print(f"pages:              {u.page_start}-{u.page_end}")
                print(f"parent_unit_id:     {getattr(u, 'parent_unit_id', None)!r}")
                print(f"children_count:     {len(getattr(u, 'children_unit_ids', []) or [])}")
                print(f"citability_band:    {u.citability.citability_band}")
                print(f"heading_text:       {getattr(u, 'heading_text', None)!r}")
                print(f"own_element_ids:    {len(u.own_element_ids)}")
                print(f"source_element_ids: {len(getattr(u, 'source_element_ids', []) or [])}")
                print(f"own_text:           {clip(u.own_text, args.max_text_chars)!r}")
                print(f"exact_text:         {clip(getattr(u, 'exact_text', None), args.max_text_chars)!r}")
                print(f"children_ids:       {getattr(u, 'children_unit_ids', []) or []}")

            # Special focus: exact parent vs children for prefix
            parent = next((u for u in snapshot.units if u.unit_id == args.uid_prefix), None)
            if parent is not None:
                print("\nPARENT FOCUS")
                print(f"  unit_id:         {parent.unit_id}")
                print(f"  unit_class:      {getattr(parent, 'unit_class', None)!r}")
                print(f"  unit_type:       {parent.unit_type.value}")
                print(f"  citability:      {parent.citability.citability_band}")
                print(f"  children_count:  {len(getattr(parent, 'children_unit_ids', []) or [])}")
                print(f"  own_text:        {clip(parent.own_text, args.max_text_chars)!r}")
                print(f"  exact_text:      {clip(getattr(parent, 'exact_text', None), args.max_text_chars)!r}")

                if getattr(parent, "children_unit_ids", None):
                    print("\nPARENT CHILDREN")
                    children_map = {u.unit_id: u for u in snapshot.units}
                    for child_id in parent.children_unit_ids:
                        child = children_map.get(child_id)
                        if child is None:
                            print(f"  - {child_id}  [MISSING IN SNAPSHOT]")
                            continue
                        print(
                            f"  - {child.unit_id} | class={getattr(child, 'unit_class', None)!r} | "
                            f"type={child.unit_type.value} | pages={child.page_start}-{child.page_end} | "
                            f"title={child.title!r}"
                        )

    finally:
        await db_gen.aclose()


if __name__ == "__main__":
    asyncio.run(main())


    
# scripts/debug_structure_live.py

from __future__ import annotations

import argparse
import asyncio
import uuid
from typing import Any

from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.session import get_db
from storage.artifact_store import ArtifactStore
from services.structure.pipeline import build_file_structure_with_chunk_plan
from engine.content.clause_tree_builder import ClauseTreeBuilder


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="In-memory rebuild of STRUCTURE using production path."
    )
    parser.add_argument(
        "--doc-id",
        required=True,
        help="Document UUID",
    )
    parser.add_argument(
        "--version-id",
        required=False,
        help="Optional version UUID. If omitted, latest version is used.",
    )
    return parser.parse_args()


def walk_nodes(nodes: list[dict[str, Any]]):
    for node in nodes:
        if not isinstance(node, dict):
            continue
        yield node
        children = node.get("children") or []
        yield from walk_nodes(children)


def print_header(title: str) -> None:
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


async def main() -> None:
    args = parse_args()
    doc_id = uuid.UUID(args.doc_id)
    version_id = uuid.UUID(args.version_id) if args.version_id else None

    db_gen = get_db()
    session = await db_gen.__anext__()
    try:
        doc_repo = DocumentRepository(session)
        ver_repo = DocumentVersionRepository(session)
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
            raise RuntimeError(f"Layout artifact invalid: {layout_ref}")

        elements = layout.get("elements") or []
        if not isinstance(elements, list) or not elements:
            raise RuntimeError("Layout has no elements")

        print_header("DOCUMENT / VERSION")
        print(f"document_id:         {doc.id}")
        print(f"document_version_id: {version.id}")
        print(f"filename:            {getattr(doc, 'filename', '-')}")
        print(f"layout_ref:          {layout_ref}")
        print(f"elements_count:      {len(elements)}")

        # ── Production structure path (same as structure worker) ──────────
        file_analysis, file_chunk_plan = build_file_structure_with_chunk_plan(
            document_id=str(doc.id),
            elements=elements,
            document_version_id=str(version.id),
        )

        file_result = file_analysis.file_structure
        clause_tree_obj = file_result.primary_tree
        clause_tree = clause_tree_obj.to_dict()

        print_header("FILE STRUCTURE RESULT")
        print(f"primary_tree_present:   {clause_tree_obj is not None}")
        print(f"segment_trees_count:    {len(file_result.segment_trees)}")
        print(f"chunk_plan_mode:        {file_chunk_plan.mode_decision.mode.value}")
        print(f"overall_retrieval_safe: {file_chunk_plan.overall_retrieval_safe}")
        print(f"any_layout_fallback:    {file_chunk_plan.any_layout_fallback}")

        roots = clause_tree.get("root") or []
        if not isinstance(roots, list):
            raise RuntimeError("primary_tree.to_dict()['root'] is not a list")

        nodes = {str(n.get("effective_uid") or ""): n for n in walk_nodes(roots)}

        target_uids = ["main_contract:1", "main_contract:2.1", "main_contract:2.2"]

        print_header("TARGET NODES IN REBUILT TREE")
        for uid in target_uids:
            node = nodes.get(uid)
            if node is None:
                print(f"\n{uid}: [NOT FOUND]")
                continue

            diag = node.get("diagnostics") or {}
            own_ids = list(node.get("own_element_ids") or [])
            print(f"\nUID: {uid}")
            print(f"  raw_uid:            {node.get('raw_uid')}")
            print(f"  title:              {node.get('title')!r}")
            print(f"  node_kind:          {node.get('node_kind')}")
            print(f"  start_page-end:     {node.get('start_page')}-{node.get('end_page')}")
            print(f"  range_end_reason:   {node.get('range_end_reason')}")
            print(f"  source_elem_i:      {diag.get('source_elem_i')}")
            print(f"  own_ids_count:      {len(own_ids)}")
            print(f"  own_range_span:     {diag.get('own_range_span')}")
            print(f"  own_text_preview:   {(str(node.get('own_text') or '')[:260]).replace(chr(10), ' ')}")

            if own_ids:
                print("  own elements:")
                element_index = ClauseTreeBuilder.build_element_index(layout)
                for i, el_id in enumerate(own_ids, start=1):
                    el = element_index.get(el_id)
                    if not el:
                        print(f"    [{i}] {el_id} [MISSING]")
                        continue
                    text = str(el.get("text") or "").strip().replace("\n", " ")
                    print(
                        f"    [{i}] {el_id} | page={el.get('page')} | "
                        f"type={el.get('type')} | text={text[:140]!r}"
                    )

        # ── Overlap check ────────────────────────────────────────────────
        n21 = nodes.get("main_contract:2.1")
        n22 = nodes.get("main_contract:2.2")
        if n21 and n22:
            s21 = set(n21.get("own_element_ids") or [])
            s22 = set(n22.get("own_element_ids") or [])
            inter = sorted(s21 & s22)

            print_header("OVERLAP main_contract:2.1 vs main_contract:2.2")
            print(f"2.1 own_ids:      {len(s21)}")
            print(f"2.2 own_ids:      {len(s22)}")
            print(f"intersection:     {len(inter)}")
            if inter:
                element_index = ClauseTreeBuilder.build_element_index(layout)
                for el_id in inter:
                    el = element_index.get(el_id)
                    if not el:
                        print(f"  - {el_id} [MISSING]")
                        continue
                    text = str(el.get('text') or '').strip().replace('\n', ' ')
                    print(
                        f"  - {el_id} | page={el.get('page')} | type={el.get('type')} | text={text[:140]!r}"
                    )

    finally:
        await db_gen.aclose()


if __name__ == "__main__":
    asyncio.run(main())


    
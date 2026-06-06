# src/scripts/debug_pages_chunks.py

from __future__ import annotations

import argparse
import asyncio
import textwrap
import uuid
from collections import defaultdict
from typing import Any

from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.session import get_db
from engine.content.chunk_snapshot_reader import ChunkCorpusReaderV2
from engine.content.document_content_service import DocumentContentService
from storage.artifact_store import ArtifactStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Показать, как сейчас выглядят выбранные страницы документа: "
            "raw layout text + canonical chunks + retrieval-visible chunks."
        )
    )
    parser.add_argument(
        "--doc-id",
        required=True,
        help="UUID документа из последнего теста",
    )
    parser.add_argument(
        "--pages",
        nargs="+",
        type=int,
        default=[3, 4],
        help="Какие страницы смотреть (по умолчанию: 3 4)",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=4000,
        help="Сколько символов текста печатать на один блок (по умолчанию: 4000)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Печатать полный текст блока без усечения",
    )
    return parser.parse_args()


def page_range_from_chunk(chunk: dict[str, Any]) -> tuple[int | None, int | None]:
    meta = chunk.get("metadata") or {}
    page_from = meta.get("page_from") or meta.get("start_page")
    page_to = meta.get("page_to") or meta.get("end_page") or page_from

    if not isinstance(page_from, int):
        page_from = None
    if not isinstance(page_to, int):
        page_to = page_from

    return page_from, page_to


def intersects_pages(chunk: dict[str, Any], wanted_pages: set[int]) -> bool:
    page_from, page_to = page_range_from_chunk(chunk)
    if page_from is None and page_to is None:
        return False

    start = page_from if page_from is not None else page_to
    end = page_to if page_to is not None else page_from
    if start is None or end is None:
        return False

    return any(start <= p <= end for p in wanted_pages)


def clip_text(text: str, max_chars: int, full: bool) -> str:
    text = (text or "").strip()
    if full or len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n…[TRUNCATED]…"


def format_chunk_header(
    chunk: dict[str, Any],
    *,
    idx: int,
    source: str,
) -> str:
    meta = chunk.get("metadata") or {}
    kind = meta.get("chunk_kind") or "-"
    uid = meta.get("effective_uid") or meta.get("clause_uid") or "-"
    chunk_id = chunk.get("id") or "-"
    retrieval_safe = meta.get("retrieval_safe")
    segment_id = meta.get("segment_id") or "-"
    page_from, page_to = page_range_from_chunk(chunk)

    if page_from is None and page_to is None:
        pages = "-"
    elif page_from == page_to:
        pages = str(page_from)
    else:
        pages = f"{page_from}–{page_to}"

    retrieval_safe_str = (
        str(retrieval_safe) if retrieval_safe is not None else "n/a"
    )

    return (
        f"[{idx}] source={source} "
        f"kind={kind} "
        f"uid={uid} "
        f"pages={pages} "
        f"retrieval_safe={retrieval_safe_str} "
        f"segment_id={segment_id} "
        f"chunk_id={chunk_id}"
    )


def print_section(title: str) -> None:
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


def extract_layout_page_text(layout: dict[str, Any], page: int) -> str:
    elements = layout.get("elements") or []
    texts: list[str] = []

    for el in elements:
        if not isinstance(el, dict):
            continue
        if el.get("page") != page:
            continue

        text = (el.get("text") or "").strip()
        if not text:
            continue
        texts.append(text)

    return "\n".join(texts).strip()


async def main() -> None:
    args = parse_args()
    doc_id = uuid.UUID(args.doc_id)
    pages = sorted(set(args.pages))
    wanted_pages = set(pages)

    db_gen = get_db()
    session = await db_gen.__anext__()
    try:
        doc_repo = DocumentRepository(session)
        ver_repo = DocumentVersionRepository(session)

        doc = await doc_repo.get_by_id(doc_id)
        if doc is None:
            raise RuntimeError(f"Document not found: {doc_id}")

        version = await ver_repo.get_latest(doc_id)
        if version is None:
            raise RuntimeError(f"Latest version not found for document: {doc_id}")

        store = ArtifactStore()
        layout_ref = (
            getattr(version, "layout_primary_sanitized_ref", None)
            or getattr(version, "layout_primary_ref", None)
        )

        print_section("DOCUMENT / VERSION")
        print(f"document_id:         {doc_id}")
        print(f"document_version_id: {version.id}")
        print(f"filename:            {getattr(doc, 'filename', '-')}")
        print(f"layout_ref:          {layout_ref or '-'}")
        print(f"chunks_manifest:     {getattr(version, 'chunks_manifest_v2_ref', '-')}")
        print(f"pages requested:     {pages}")

        # ── 1. RAW LAYOUT PAGES ──────────────────────────────────────
        if layout_ref:
            layout = store.get_json(layout_ref)
            print_section("RAW LAYOUT TEXT BY PAGE")
            for page in pages:
                page_text = extract_layout_page_text(layout, page)
                print(f"\n--- PAGE {page} ---\n")
                if page_text:
                    print(clip_text(page_text, args.max_chars, args.full))
                else:
                    print("[NO TEXT FOUND]")
        else:
            print_section("RAW LAYOUT TEXT BY PAGE")
            print("No layout ref found on latest version.")

        # ── 2. CANONICAL CHUNKS (all layers) ─────────────────────────
        reader = ChunkCorpusReaderV2(
            session=session,
            artifact_store=store,
        )
        canonical_chunks = await reader.load(
            doc_id=doc_id,
            levels=["section", "clause", "subclause"],
        )

        canonical_hits = [ch for ch in canonical_chunks if intersects_pages(ch, wanted_pages)]

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for ch in canonical_hits:
            kind = (ch.get("metadata") or {}).get("chunk_kind") or "unknown"
            grouped[str(kind)].append(ch)

        print_section("CANONICAL CHUNKS INTERSECTING REQUESTED PAGES")
        if not canonical_hits:
            print("[NO CANONICAL CHUNKS FOUND]")
        else:
            for kind in ("section", "clause", "subclause", "unknown"):
                items = grouped.get(kind) or []
                if not items:
                    continue

                print(f"\n### {kind.upper()} ({len(items)}) ###\n")
                for idx, chunk in enumerate(items, start=1):
                    print(format_chunk_header(chunk, idx=idx, source="canonical"))
                    print(textwrap.indent(clip_text(chunk.get("text") or "", args.max_chars, args.full), prefix="    "))
                    print()

        # ── 3. RETRIEVAL-VISIBLE CHUNKS ──────────────────────────────
        content = DocumentContentService(
            session=session,
            artifact_store=store,
        )
        retrieval_chunks = await content.get_retrieval_chunks_for_checks(
            doc_id=doc_id,
            filter_unsafe_chunks=False,
        )
        retrieval_hits = [ch for ch in retrieval_chunks if intersects_pages(ch, wanted_pages)]

        grouped_r: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for ch in retrieval_hits:
            kind = (ch.get("metadata") or {}).get("chunk_kind") or "unknown"
            grouped_r[str(kind)].append(ch)

        print_section("RETRIEVAL-VISIBLE CHUNKS INTERSECTING REQUESTED PAGES")
        if not retrieval_hits:
            print("[NO RETRIEVAL CHUNKS FOUND]")
        else:
            for kind in ("section", "subclause", "clause", "unknown"):
                items = grouped_r.get(kind) or []
                if not items:
                    continue

                print(f"\n### {kind.upper()} ({len(items)}) ###\n")
                for idx, chunk in enumerate(items, start=1):
                    print(format_chunk_header(chunk, idx=idx, source="retrieval"))
                    print(textwrap.indent(clip_text(chunk.get("text") or "", args.max_chars, args.full), prefix="    "))
                    print()

    finally:
        await db_gen.aclose()


if __name__ == "__main__":
    asyncio.run(main())


    
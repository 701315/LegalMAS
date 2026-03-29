# scripts/debug_content_service.py

import asyncio
import uuid

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.core.config import settings
from src.engine.content.document_content_service import DocumentContentService


async def debug_document(doc_id_str: str) -> None:
    # 1. Настраиваем подключение к БД (берём URL из настроек)
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    doc_id = uuid.UUID(doc_id_str)

    async with async_session() as session:
        service = DocumentContentService(session=session)

        print(f"\n=== Debug for document {doc_id} ===")

        # 2. Базовые клауза-чанки
        clauses = await service.get_chunks(doc_id)
        print(f"\n[CLAUSE] total chunks: {len(clauses)}")
        for ch in clauses[:3]:
            meta = ch.get("metadata") or {}
            print(
                f"- id={ch.get('id')}, "
                f"clause_uid={meta.get('clause_uid')}, "
                f"pages={meta.get('start_page')}–{meta.get('end_page')}, "
                f"path={meta.get('path_titles')}"
            )
            print(f"  text sample: {repr((ch.get('text') or '')[:200])}\n")

        # 3. Sized-чанки
        sized = await service.get_sized_chunks(doc_id)
        print(f"\n[SUBCLAUSE / SIZED] total chunks: {len(sized)}")
        for ch in sized[:5]:
            meta = ch.get("metadata") or {}
            print(
                f"- id={ch.get('id')}, "
                f"clause_uid={meta.get('clause_uid')}, "
                f"token_count={meta.get('token_count')}, "
                f"pages={meta.get('start_page')}–{meta.get('end_page')}"
            )
            print(f"  text sample: {repr((ch.get('text') or '')[:200])}\n")

        # 4. Иерархические уровни
        hier = await service.get_hierarchical_chunks(doc_id)
        sections = hier.get("section") or []
        clauses_h = hier.get("clause") or []
        subclauses_h = hier.get("subclause") or []

        print(f"\n[HIERARCHY] sections={len(sections)}, clauses={len(clauses_h)}, subclauses={len(subclauses_h)}")

        print("\n[SECTION] examples:")
        for ch in sections[:3]:
            meta = ch.get("metadata") or {}
            print(
                f"- id={ch.get('id')}, "
                f"title={meta.get('title')}, "
                f"path={meta.get('path_titles')}, "
                f"token_count={meta.get('token_count')}, "
                f"pages={meta.get('start_page')}–{meta.get('end_page')}"
            )
            print(f"  summary: {meta.get('summary')}")
            print(f"  text sample: {repr((ch.get('text') or '')[:200])}\n")

        print("\n[CLAUSE] with summary examples:")
        for ch in clauses_h[:3]:
            meta = ch.get("metadata") or {}
            print(
                f"- id={ch.get('id')}, "
                f"clause_uid={meta.get('clause_uid')}, "
                f"path={meta.get('path_titles')}"
            )
            print(f"  summary: {meta.get('summary')}")
            print(f"  text sample: {repr((ch.get('text') or '')[:200])}\n")

        print("\n[SUBCLAUSE] with summary examples:")
        for ch in subclauses_h[:5]:
            meta = ch.get("metadata") or {}
            print(
                f"- id={ch.get('id')}, "
                f"clause_uid={meta.get('clause_uid')}, "
                f"token_count={meta.get('token_count')}"
            )
            print(f"  summary: {meta.get('summary')}")
            print(f"  text sample: {repr((ch.get('text') or '')[:200])}\n")

    await engine.dispose()


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python scripts/debug_content_service.py <document_uuid>")
        raise SystemExit(1)

    asyncio.run(debug_document(sys.argv[1]))
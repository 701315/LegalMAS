#!/usr/bin/env python
"""
Пересобрать CHUNKS v2 для конкретного документа.

Usage:
    PYTHONPATH=src python scripts/rebuild_chunks_for_doc.py \
        --doc-id c7b94b53-090a-4bb1-b734-fce961e46203

Что делает:
1. Находит latest DocumentVersion для указанного документа.
2. Резолвит tenant тем же способом, что production worker.
3. Вызывает _build_chunks_v2_async() — тот же код, что Celery worker.
4. Пишет новые snapshot'ы в MinIO и обновляет БД.
5. После этого get_retrieval_chunks_for_checks() сможет вернуть legal_unit chunks.

P8.8d:
- После writer-side patch SegmentChunkBuilderV2 теперь записывает
  chunks["legal_unit"] в segment snapshot.
- Этот скрипт позволяет пересобрать snapshot без полного pipeline re-run.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid

from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.uow import db_uow
from workers._tenant_resolver import resolve_artifact_tenant_id


async def rebuild(doc_id: uuid.UUID) -> None:
    from workers.chunk_builder import _build_chunks_v2_async

    async with db_uow() as uow:
        ver_repo = DocumentVersionRepository(uow.session)
        doc_repo = DocumentRepository(uow.session)

        version = await ver_repo.get_latest(doc_id)
        if not version:
            print(f"ERROR: No latest version found for document {doc_id}")
            return

        doc = await doc_repo.get_by_id(doc_id)
        if not doc:
            print(f"ERROR: Document {doc_id} not found")
            return

        deal_id = str(doc.deal_id)

        # Делаем ровно как production worker:
        # tenant берём через resolve_artifact_tenant_id(), а не из doc.tenant_id.
        tenant_id = await resolve_artifact_tenant_id(
            session=uow.session,
            deal_id=deal_id,
            document_id=str(doc_id),
            payload_tenant_id=None,
        )

        print(f"Document:  {doc_id}")
        print(f"Version:   {version.id}")
        print(f"Deal:      {deal_id}")
        print(f"Tenant:    {tenant_id}")
        print()
        print("Rebuilding CHUNKS v2...")

        result = await _build_chunks_v2_async(
            document_version_id=str(version.id),
            document_id=str(doc_id),
            deal_id=deal_id,
            tenant_id=str(tenant_id),
            run_id=None,
            uow=uow,
            stage_execution_id=None,
        )

        print()
        print("Result:")
        for k, v in sorted(result.items()):
            print(f"  {k}: {v}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild CHUNKS v2 for a document")
    parser.add_argument("--doc-id", required=True, help="Document UUID")
    args = parser.parse_args()

    doc_id = uuid.UUID(args.doc_id)
    asyncio.run(rebuild(doc_id))


if __name__ == "__main__":
    main()



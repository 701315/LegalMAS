# scripts/dump_clause_tree.py

import asyncio
import json
from pathlib import Path
from uuid import UUID

from db.uow import db_uow
from db.repositories.document_version_repo import DocumentVersionRepository
from engine.content.document_content_service import DocumentContentService

DOCUMENT_ID = UUID("f4c739be-4976-4bec-a3cc-a5194eb43fdd")


async def main() -> None:
    print("starting dump_clause_tree")

    async with db_uow() as uow:
        ver_repo = DocumentVersionRepository(uow.session)
        version = await ver_repo.get_latest(DOCUMENT_ID)
        if not version:
            raise RuntimeError(f"No latest DocumentVersion for doc {DOCUMENT_ID}")

        clause_tree_ref = getattr(version, "clause_tree_ref", None)
        if not clause_tree_ref:
            raise RuntimeError(
                f"No clause_tree_ref for version {version.id} of doc {DOCUMENT_ID}"
            )

        print(f"version_id={version.id}")
        print(f"clause_tree_ref={clause_tree_ref}")

        content = DocumentContentService(uow.session)
        store = content._artifact_store
        clause_tree = store.get_json(clause_tree_ref)

    out_dir = Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / "clause_tree.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(clause_tree, f, ensure_ascii=False, indent=2)

    print(f"written to {out_path.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
# scripts/dump_layout_primary_sanitized.py

import asyncio
import json
from pathlib import Path
from uuid import UUID

from db.uow import db_uow
from db.repositories.document_version_repo import DocumentVersionRepository
from engine.content.document_content_service import DocumentContentService

DOCUMENT_ID = UUID("f4c739be-4976-4bec-a3cc-a5194eb43fdd")


async def main() -> None:
    print("starting dump_layout_primary_sanitized")

    async with db_uow() as uow:
        ver_repo = DocumentVersionRepository(uow.session)
        version = await ver_repo.get_latest(DOCUMENT_ID)
        if not version:
            raise RuntimeError(f"No latest DocumentVersion for doc {DOCUMENT_ID}")

        layout_primary_ref = getattr(version, "layout_primary_ref", None)
        layout_primary_sanitized_ref = getattr(
            version, "layout_primary_sanitized_ref", None
        )

        if not layout_primary_ref and not layout_primary_sanitized_ref:
            raise RuntimeError(
                f"No layout_primary_ref / layout_primary_sanitized_ref "
                f"for version {version.id} of doc {DOCUMENT_ID}"
            )

        layout_ref = layout_primary_sanitized_ref or layout_primary_ref

        print(f"version_id={version.id}")
        print(f"layout_primary_ref={layout_primary_ref}")
        print(f"layout_primary_sanitized_ref={layout_primary_sanitized_ref}")
        print(f"using layout_ref={layout_ref}")

        content = DocumentContentService(uow.session)
        store = content._artifact_store
        layout = store.get_json(layout_ref)

    out_dir = Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / "layout_primary_sanitized.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(layout, f, ensure_ascii=False, indent=2)

    print(f"written to {out_path.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
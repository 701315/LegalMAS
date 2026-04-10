# scripts/dump_text_layout_raw.py

import asyncio
import json
from pathlib import Path
from uuid import UUID

from db.uow import db_uow
from db.repositories.document_version_repo import DocumentVersionRepository
from engine.content.document_content_service import DocumentContentService

DOCUMENT_ID = UUID("f4c739be-4976-4bec-a3cc-a5194eb43fdd")


async def main() -> None:
    print("starting dump_text_layout_raw")

    async with db_uow() as uow:
        ver_repo = DocumentVersionRepository(uow.session)
        version = await ver_repo.get_latest(DOCUMENT_ID)
        if not version:
            raise RuntimeError(f"No latest DocumentVersion for doc {DOCUMENT_ID}")

        raw_ref = getattr(version, "text_layout_raw_ref", None)
        if not raw_ref:
            raise RuntimeError(
                f"No text_layout_raw_ref for version {version.id} of doc {DOCUMENT_ID}"
            )

        print(f"version_id={version.id}")
        print(f"text_layout_raw_ref={raw_ref}")

        content = DocumentContentService(uow.session)
        store = content._artifact_store
        layout_raw = store.get_json(raw_ref)

    out_dir = Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / "text_layout_raw.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(layout_raw, f, ensure_ascii=False, indent=2)

    print(f"written to {out_path.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
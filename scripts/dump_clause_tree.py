# scripts/dump_clause_tree.py
# scripts/dump_clause_tree.py
# cd ~/projects/LegalMAS
# PYTHONPATH=./src python scripts/dump_clause_tree.py


import sys
import asyncio
import json
from pathlib import Path
from uuid import UUID

# Чтобы работало при запуске из корня репозитория:
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from db.uow import db_uow
from api.schemas.document_pipeline_view import PipelineStageCode, StageViewMode
from services.document_pipeline_view_service import DocumentPipelineViewService


DOC_ID = "be76f4a4-85e1-49ac-ad8c-a78fd25e7252"


async def main() -> None:
    async with db_uow() as uow:
        service = DocumentPipelineViewService(uow.session)

        # Вызов позиционно, чтобы не зависеть от имён параметров build()
        response = await service.build(
            UUID(DOC_ID),
            StageViewMode.friendly,
        )

        data = response.model_dump(mode="json")

        structure_stage = next(
            (s for s in data["stages"] if s["code"] == PipelineStageCode.STRUCTURE.value),
            None,
        )

        # На всякий случай поддерживаем оба варианта ключа
        view_mode_value = data["viewmode"] if "viewmode" in data else data.get("view_mode")
        print("view_mode:", view_mode_value)
        print("structure available:", structure_stage["available"] if structure_stage else None)

        if not structure_stage or not structure_stage.get("preview"):
            print("No structure preview")
            return

        preview = structure_stage["preview"]
        sections = preview.get("sections") or []

        print("sections_len:", len(sections))

        interesting: list[dict] = []
        for s in sections:
            uid = s.get("clause_uid")
            title = (s.get("title") or "").strip()

            if uid in {"2.2", "2.2.5", "2.2.11", "2.2.12"} or title.startswith(
                ("2.2", "2.2.5", "2.2.11", "2.2.12")
            ):
                interesting.append(
                    {
                        "id": s.get("id"),
                        "title": s.get("title"),
                        "level": s.get("level"),
                        "clause_uid": s.get("clause_uid"),
                        "page_from": s.get("page_from"),
                        "page_to": s.get("page_to"),
                        "text_preview": s.get("text_preview"),
                        "source_mapping": s.get("source_mapping"),
                    }
                )

        print(json.dumps(interesting, ensure_ascii=False, indent=2))

        out = PROJECT_ROOT / "pipeline_view_friendly.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"saved: {out.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())


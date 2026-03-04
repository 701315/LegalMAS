"""
Structure Builder Worker.
Reads textlayoutraw from MinIO, builds clause tree via StructureBuilder service,
saves result to MinIO and updates document status.

Status transition: sanitized -> structured.
Next step: classify_document.
"""

import asyncio
import time
import uuid

from core.config import settings
from core.constants import DocumentStatus
from core.exceptions import PermanentError
from core.logging import get_logger
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.uow import db_uow
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from services.structure.builder import StructureBuilder
from storage.artifact_store import ArtifactPath, ArtifactStore
from workers.classifier import classify_document

logger = get_logger(__name__)


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.build_structure",
    queue="default",
)
def build_structure(
    self,
    document_version_id: str,
    **kwargs,  # принимаем остальные аргументы (deal_id, run_id и т.д.) для совместимости
) -> dict:
    """Sync Celery entry point."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_build_structure_async(self, document_version_id, kwargs))
    finally:
        loop.close()


async def _build_structure_async(task, document_version_id: str, extra_args: dict) -> dict:
    store = ArtifactStore(settings)
    start = time.time()
    v_id = (
        uuid.UUID(document_version_id)
        if isinstance(document_version_id, str)
        else document_version_id
    )

    async with db_uow() as uow:
        ver_repo = DocumentVersionRepository(uow.session)
        doc_repo = DocumentRepository(uow.session)

        # 1. Загрузка версии и документа
        version = await ver_repo.get_by_id(v_id)
        if not version:
            raise PermanentError(f"DocumentVersion {v_id} not found")

        doc = await doc_repo.get_by_id(version.document_id)
        if not doc:
            raise PermanentError(f"Document {version.document_id} not found")

        # Идемпотентность: не перестраиваем, если уже готово
        if doc.status in (
            DocumentStatus.STRUCTURED.value,
            DocumentStatus.CLASSIFIED.value,
            "analyzing",
        ):
            logger.info("Already structured, skipping", document_id=str(doc.id))
            return {"document_id": str(doc.id), "skipped": True}

        # 2. Получение сырого макета из MinIO
        if not version.text_layout_raw_ref:
            raise PermanentError(f"text_layout_raw_ref missing for version {v_id}")

        raw_layout = await store.get_json(version.text_layout_raw_ref)
        elements = raw_layout.get("elements", [])
        if not elements:
            raise PermanentError(f"No elements in raw layout for version {v_id}")

        # 3. Вызов сервиса построения структуры
        builder = StructureBuilder()
        clause_tree = builder.build(
            document_id=str(doc.id),
            elements=elements,
        )

        # 4. Сохранение ClauseTree как отдельного артефакта
        clause_tree_path = ArtifactPath.clause_tree(
            tenant_id=str(doc.deal_id),
            deal_id=str(doc.deal_id),
            document_id=str(doc.id),
        )
        await store.put_json(clause_tree_path, clause_tree.to_dict())

        # 5. Обновление БД
        await ver_repo.update_refs(version_id=v_id, clause_tree_ref=clause_tree_path)
        await doc_repo.update_status(doc.id, DocumentStatus.STRUCTURED.value)

        # UoW зафиксирует изменения (commit) при выходе из блока

    # 6. Запуск следующего этапа (Классификация)

    # Передаем контекст дальше (run_id важен для аналитики)
    classify_document.delay(document_id=str(doc.id), run_id=extra_args.get("run_id"))

    return {
        "document_id": str(doc.id),
        "clause_tree_ref": clause_tree_path,
        "confidence": clause_tree.structure_confidence,
        "is_degraded": clause_tree.degraded,
        "duration": round(time.time() - start, 2),
    }

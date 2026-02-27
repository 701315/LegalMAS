"""
Classifier Worker.
4-level cascade: L1 (Rules) → L2 (Keywords) → L3 (Semantic) → L4 (LLM).

Updates document with:
  - doctype, language, jurisdiction, confidence, levels tried, applicable triggers.
  - Links correct playbook_version_id based on doctype and language.

Status: structured -> classified.
"""

import asyncio
import time
import uuid

from src.classifiers.hybrid_classifier import HybridClassifier
from src.classifiers.keyword_analyzer import KeywordAnalyzer
from src.classifiers.llm_classifier import create_llm_classifier
from src.classifiers.rule_based import RuleBasedClassifier
from src.classifiers.semantic_matcher import SemanticMatcher
from src.core.config import settings
from src.core.constants import DocumentStatus
from src.core.exceptions import PermanentError
from src.core.logging import get_logger
from src.db.repositories.document_repo import DocumentRepository
from src.db.repositories.document_version_repo import DocumentVersionRepository
from src.db.repositories.playbook_repo import PlaybookRepository
from src.db.uow import db_uow
from src.queue.base_task import MASBaseTask
from src.queue.celery_app import celery_app
from src.storage.artifact_store import ArtifactStore

logger = get_logger(__name__)

# Кэшируем экземпляр классификатора в рамках процесса воркера
_classifier_instance: HybridClassifier | None = None


def _get_classifier() -> HybridClassifier:
    """Lazy singleton: инициализирует тяжелые модели L3/L4 один раз."""
    global _classifier_instance
    if _classifier_instance is None:
        reg_path = settings.CLASSIFIER_REGISTRY_PATH
        _classifier_instance = HybridClassifier(
            rule_based=RuleBasedClassifier(registry_path=reg_path),
            keyword_analyzer=KeywordAnalyzer(registry_path=reg_path),
            semantic_matcher=SemanticMatcher(
                model_name=settings.CLASSIFIER_EMBEDDINGS_MODEL, registry_path=reg_path
            ),
            llm_classifier=create_llm_classifier(registry_path=reg_path),
            registry_path=reg_path,
        )
    return _classifier_instance


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.classify_document",
    queue="default",
)
def classify_document(self, document_id: str, **kwargs) -> dict:
    """Sync Celery entry point: обертка над асинхронным ядром."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_classify_document_async(self, document_id, kwargs))
    finally:
        loop.close()


async def _classify_document_async(task, document_id: str, extra_args: dict) -> dict:
    store = ArtifactStore(settings)
    start_time = time.time()
    doc_uuid = uuid.UUID(document_id) if isinstance(document_id, str) else document_id

    async with db_uow() as uow:
        doc_repo = DocumentRepository(uow.session)
        ver_repo = DocumentVersionRepository(uow.session)
        playbook_repo = PlaybookRepository(uow.session)

        # 1. Загрузка документа и версии
        doc = await doc_repo.get_by_id(doc_uuid)
        if not doc:
            raise PermanentError(f"Document {document_id} not found")

        # Идемпотентность
        if doc.status in (DocumentStatus.CLASSIFIED.value, "analyzing"):
            logger.info("Already classified, skipping", document_id=document_id)
            return {"document_id": document_id, "skipped": True}

        version = await ver_repo.get_latest(doc.id)
        if not version:
            raise PermanentError(f"No version found for document {document_id}")

        # 2. Получение текстов (Raw для L1-L3, Sanitized для L4)
        raw_layout = await store.get_json(version.text_layout_raw_ref)
        san_layout = raw_layout
        if version.text_layout_sanitized_ref:
            try:
                san_layout = await store.get_json(version.text_layout_sanitized_ref)
            except Exception as e:
                logger.warning("Failed to load sanitized layout, using raw", error=str(e))

        text_raw = _extract_text(raw_layout)
        text_san = _extract_text(san_layout)

        # 3. Запуск каскадной классификации
        classifier = _get_classifier()
        result = await classifier.classify(
            text=text_raw,
            text_sanitized=text_san,
            filename=doc.filename,
            folder_path=doc.folder_path or "",
        )

        # 4. Маршрутизация на плейбук
        playbook = await playbook_repo.get_for_doctype(
            doctype=result.doctype, language=result.language
        )

        # 5. Атомарное сохранение результатов
        await doc_repo.update_classification(
            doc_id=doc.id,
            doc_type=result.doctype,
            classification_confidence=result.confidence,
            classification_level=result.level.value,
            classification_details=result.details,
            applicable_triggers=result.applicable_triggers,
            language=result.language,
            jurisdiction=result.jurisdiction,
            playbook_version_id=playbook.id if playbook else None,
        )

        await doc_repo.update_status(doc.id, DocumentStatus.CLASSIFIED.value)

        # UoW зафиксирует транзакцию (commit)

    # 6. Запуск Runner (Stage 8) - передаем doctype для оптимизации
    run_id = extra_args.get("run_id")
    if run_id:
        from src.workers.runner import run_checks

        run_checks.delay(
            document_id=str(doc.id),
            deal_id=extra_args.get("deal_id"),
            tenant_id=extra_args.get("tenant_id"),
            run_id=run_id,
            doctype=result.doctype,
        )

    duration_ms = int((time.time() - start_time) * 1000)
    return {
        "document_id": document_id,
        "doctype": result.doctype,
        "confidence": result.confidence,
        "language": result.language,
        "jurisdiction": result.jurisdiction,
        "playbook_found": playbook is not None,
        "duration_ms": duration_ms,
    }


def _extract_text(layout: dict) -> str:
    """Извлекает весь текст из JSON макета."""
    if not layout or "elements" not in layout:
        return ""
    return " ".join([el.get("text", "") for el in layout.get("elements", []) if el.get("text")])

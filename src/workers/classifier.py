# src/workers/classifier.py

"""
Classifier Worker — каскадная классификация документов (Stage 6).

Позиция в пайплайне:
- import → extract → pii → structure → classify → run_checks.
- На вход получает структурированный документ (есть text_layout_raw / sanitized).

Что делает:
- Запускает 4‑уровневый каскад классификации:
  L1 (Rules) → L2 (Keywords) → L3 (Semantic) → L4 (LLM).
- Обновляет документ полями:
  - doc_type, language, jurisdiction, classification_confidence,
    classification_level, classification_details, applicable_triggers.
- Подбирает и привязывает подходящий playbook_version_id по doc_type и языку.
- Обновляет статус документа: structured → classified.
- Если передан run_id, ставит задачу workers.run_checks для этого документа.

Архитектура:
- Внешняя Celery‑таска classify_document — синхронная (def), её вызывает Celery.
- Внутри один раз выполняется переход sync → async через run_async
  в _classify_document_async.
- Вся работа с БД и хранилищем (ArtifactStore) выполняется под db_uow().
- Экземпляр HybridClassifier (_get_classifier) кэшируется на процесс воркера,
  чтобы тяжёлые модели L3/L4 инициализировались один раз.
"""

import time
import uuid

from ops.metrics import get_metrics

from classifiers.hybrid_classifier import HybridClassifier
from classifiers.keyword_analyzer import KeywordAnalyzer
from classifiers.llm_classifier import create_llm_classifier
from classifiers.rule_based import RuleBasedClassifier
from classifiers.semantic_matcher import SemanticMatcher
from core.config import settings
from core.constants import DocumentStatus
from core.exceptions import PermanentError
from core.logging import get_logger
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.repositories.playbook_repo import PlaybookRepository
from db.uow import db_uow, UnitOfWork
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from mas_queue.async_helpers import run_async
from storage.artifact_store import ArtifactStore

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
                model_name=settings.CLASSIFIER_EMBEDDINGS_MODEL,
                registry_path=reg_path,
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
    """
    Sync Celery entry point: обертка над асинхронным ядром.

    Паттерн:
    - Celery вызывает синхронную функцию.
    - Внутри один раз передаём управление в async‑мир через run_async.
    """
    async def _wrapper() -> dict:
        return await _classify_document_async(self, document_id, kwargs)

    return run_async(_wrapper())


async def _classify_document_async(task, document_id: str, extra_args: dict) -> dict:
    store = ArtifactStore(settings)
    start_time = time.time()
    doc_uuid = uuid.UUID(document_id) if isinstance(document_id, str) else document_id

    metrics = get_metrics()
    run_id_str = extra_args.get("run_id")
    run_uuid = uuid.UUID(run_id_str) if run_id_str else None

    try:
        async with db_uow() as uow:
            doc_repo = DocumentRepository(uow.session)
            ver_repo = DocumentVersionRepository(uow.session)
            playbook_repo = PlaybookRepository(uow.session)

            # 1. Загрузка документа и версии
            doc = await doc_repo.get_by_id(doc_uuid)
            if not doc:
                raise PermanentError(f"Document {document_id} not found")

            # Идемпотентность
            if doc.status in (
                DocumentStatus.CLASSIFIED.value,
                DocumentStatus.ANALYZING.value,
            ):
                logger.info("Already classified, skipping", document_id=document_id)
                return {"document_id": document_id, "skipped": True}

            version = await ver_repo.get_latest(doc.id)
            if not version:
                raise PermanentError(
                    f"No version found for document {document_id}"
                )

            # 2. Получение текстов (Raw для L1–L3, Sanitized для L4)
            if not version.text_layout_raw_ref:
                raise PermanentError(
                    f"text_layout_raw_ref missing for document {document_id}"
                )

            # ArtifactStore.get_json — синхронный метод, НЕ используем await
            raw_layout = store.get_json(version.text_layout_raw_ref)
            san_layout = raw_layout
            if version.text_layout_sanitized_ref:
                try:
                    san_layout = store.get_json(
                        version.text_layout_sanitized_ref
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to load sanitized layout, using raw",
                        error=str(e),
                    )


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

            # 4. Маршрутизация на плейбук (deal-level PlaybookVersion)
            # Берём playbook, привязанный к сделке, или глобальный default.
            playbook = await playbook_repo.get_for_deal(doc.deal_id)


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

            # --- Метрики классификации ---
            metrics.classification_duration.labels(
                level=result.level.value if hasattr(result, "level") else "L_manual",
            ).observe(time.time() - start_time)

            metrics.classification_level_distribution.labels(
                level=result.level.value if hasattr(result, "level") else "L_manual",
                doc_type=result.doctype or "UNKNOWN",
            ).inc()

            await doc_repo.update_status(
                doc.id,
                DocumentStatus.CLASSIFIED.value,
                processing_error_details=None,
            )
            # UoW зафиксирует транзакцию (commit)

    except PermanentError as e:
        # Обновляем статус документа на FAILED в отдельном простом UoW
        logger.error(
            "Permanent error during classification",
            document_id=document_id,
            error=str(e),
        )
        async with db_uow() as uow_status:
            await _mark_failed(
                uow_status,
                doc_uuid,
                message=str(e),
                run_id=run_uuid,
            )
        return {"status": DocumentStatus.FAILED.value, "error": str(e)}

    # 6. Запуск Runner (Stage 8) - передаем doctype для оптимизации
    run_id = extra_args.get("run_id")

    if run_id:
        deal_id = extra_args.get("deal_id")
        tenant_id = extra_args.get("tenant_id")

        # Fallback: если не передали, пробуем восстановить по документу.
        if deal_id is None or tenant_id is None:
            async with db_uow() as uow2:
                doc_repo2 = DocumentRepository(uow2.session)
                doc2 = await doc_repo2.get_by_id(doc_uuid)
                if not doc2:
                    raise PermanentError(
                        f"Document {document_id} not found when scheduling run_checks"
                    )

                if (
                    hasattr(doc2, "deal")
                    and doc2.deal
                    and hasattr(doc2.deal, "tenant_id")
                ):
                    tenant_id = str(doc2.deal.tenant_id)
                else:
                    tenant_id = str(doc2.deal_id)

                deal_id = str(doc2.deal_id)

        from mas_queue.celery_app import celery_app as _celery  # на случай циклов импорта

        _celery.send_task(
            "workers.run_checks",
            kwargs={
                "document_id": document_id,
                "deal_id": deal_id,
                "tenant_id": tenant_id,
                "run_id": run_id,
                "doctype": result.doctype,
            },
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


async def _mark_failed(
    uow: UnitOfWork,
    doc_id: uuid.UUID,
    *,
    message: str,
    run_id: uuid.UUID | None,
) -> None:
    """
    Отдельный простой UoW для перевода документа в статус FAILED
    с заполнением processing_error_details.
    """
    repo = DocumentRepository(uow.session)
    await repo.set_failed(
        doc_id,
        stage="classify",
        message=message,
        reason="classification_error",
        run_id=run_id,
    )


def _extract_text(layout: dict) -> str:
    """Извлекает весь текст из JSON макета."""
    if not layout or "elements" not in layout:
        return ""
    return " ".join(
        el.get("text", "") for el in layout.get("elements", []) if el.get("text")
    )

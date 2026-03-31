# src/workers/classifier.py

"""
Classifier Worker — каскадная классификация документов (Stage 6/7).

Позиция в пайплайне:
- import → extract → pii → structure → classify → run_deal_checks.
- На вход получает структурированный документ (есть text_layout_raw / sanitized).

Что делает:
- Запускает 3‑уровневый каскад классификации + L4-fallback внутри HybridClassifier:
  L1 (filename) → L2 (header) → L3 (semantic) → опционально L4 (LLM-fallback).
- Обновляет документ полями:
  - doc_type, language, jurisdiction, classification_confidence,
    classification_level, classification_details, applicable_triggers.
- Подбирает и привязывает подходящий playbook_version_id по сделке.
- Обновляет статус документа: structured → classified.

Архитектура:
- Внешняя Celery‑таска classify_document — синхронная (def), её вызывает Celery.
- Внутри один раз выполняется переход sync → async через run_async
  в _classify_document_async.
- Вся работа с БД выполняется под db_uow().
- Экземпляр HybridClassifier (_get_classifier) кэшируется на процесс воркера,
  чтобы тяжёлые модели L3/L4 инициализировались один раз.
"""

import time
import uuid

from ops.metrics import get_metrics
from services.run_checks_auto_starter import maybe_start_run_checks

from classifiers.stage8.hybrid_classifier import HybridClassifier
from core.config import settings
from core.constants import DocumentStatus
from core.exceptions import PermanentError
from core.logging import get_logger
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.repositories.playbook_repo import PlaybookRepository
from db.uow import db_uow, UnitOfWork
from engine.content.document_content_service import (
    DocumentContentService,
    ClauseTreeStorageClient,
)
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from mas_queue.async_helpers import run_async

logger = get_logger(__name__)

# Кэшируем экземпляр классификатора и контент‑сервиса
# в рамках процесса воркера.
#
# Для непрофессионального программиста:
# - Эти объекты создаются только один раз на процесс.
# - Это экономит время: тяжёлые модели инициализируются один раз,
#   а не для каждого документа.
_classifier_instance: HybridClassifier | None = None
_content_service_instance: DocumentContentService | None = None


def _get_classifier(uow: UnitOfWork) -> HybridClassifier:
    """
    Lazy singleton: инициализирует HybridClassifier один раз на процесс.

    Для непрофессионального программиста:
    - Эта функция создаёт объект HybridClassifier только при первом вызове.
    - Все последующие вызовы будут переиспользовать уже созданный объект.
    """
    global _classifier_instance, _content_service_instance

    if _classifier_instance is None:
        # content_service используется HybridClassifier для получения header/snippet
        # из clause tree. Теперь он требует:
        # - session: AsyncSession — для доступа к версиям документа;
        # - storage_client: клиент для чтения JSON из хранилища.
        if _content_service_instance is None:
            _content_service_instance = DocumentContentService(
                session=uow.session,
                storage_client=ClauseTreeStorageClient(),
            )

        _classifier_instance = HybridClassifier(
            uow=uow,
            content_service=_content_service_instance,
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
    Sync Celery entry point: обёртка над асинхронным ядром.

    Паттерн:
    - Celery вызывает синхронную функцию.
    - Внутри один раз передаём управление в async‑мир через run_async.
    """

    async def _wrapper() -> dict:
        return await _classify_document_async(self, document_id, kwargs)

    return run_async(_wrapper())


async def _classify_document_async(task, document_id: str, extra_args: dict) -> dict:
    """
    Асинхронное ядро классификации одного документа.

    Для непрофессионального программиста:
    - Здесь вся основная логика.
    - Функция работает с БД, классификатором и обновляет документ.
    """
    start_time = time.time()
    doc_uuid = uuid.UUID(document_id) if isinstance(document_id, str) else document_id

    metrics = get_metrics()
    run_id_str = extra_args.get("run_id")
    run_uuid = uuid.UUID(run_id_str) if run_id_str else None

    playbook = None
    classification_result: dict | None = None

    try:
        async with db_uow() as uow:
            doc_repo = DocumentRepository(uow.session)
            ver_repo = DocumentVersionRepository(uow.session)
            playbook_repo = PlaybookRepository(uow.session)

            # 1. Загрузка документа и версии
            doc = await doc_repo.get_by_id(doc_uuid)
            if not doc:
                raise PermanentError(f"Document {document_id} not found")

            # Идемпотентность: если документ уже классифицирован или в анализе — пропускаем
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

            # 2. Запуск HybridClassifier (L1–L3 + L4 внутри)
            classifier = _get_classifier(uow)
            classification_result = await classifier.classify_document(str(doc.id))


            # Формат classification_result:
            # - см. HybridClassifier.classify_document и FinalClassification в classifiers/base.py.
            # - финальные поля (final_type, final_confidence, level, language, jurisdiction,
            #   applicable_triggers, details) считаются стабильным контрактом.
            # - details содержит JSON-структуру с L1/L2/L3/L4, голосованием и зоной уверенности.
            # Ожидаемый формат classification_result см. в hybrid_classifier.py.
            raw_final_type = classification_result.get("final_type") or "UNKNOWN"

            final_conf = float(classification_result.get("final_confidence") or 0.0)
            level = classification_result.get("level")
            language = classification_result.get("language")
            jurisdiction = classification_result.get("jurisdiction")
            applicable_triggers = classification_result.get(
                "applicable_triggers", []
            )
            details = classification_result.get("details", {}) or {}

            # Флаг "нужна ручная проверка" приходит из HybridClassifier.
            # Для непрофессионального программиста:
            # - сам классификатор уже решил, попадает ли документ в зоны
            #   confident / low / unknown.
            # - если зона low или unknown, он ставит requires_manual_review=True.
            # - здесь мы только читаем этот флаг и сохраняем его в БД.
            classification_requires_review = bool(
                details.get("requires_manual_review", False)
            )

            # Нормализация типа документа:
            # - "UNKNOWN" не пишем в doc_type, вместо этого используем None.
            #   Это важно, чтобы "UNKNOWN" не воспринимался как реальный тип.
            final_type: str | None
            if isinstance(raw_final_type, str) and raw_final_type.upper() == "UNKNOWN":
                final_type = None
            elif isinstance(raw_final_type, str) and raw_final_type.strip():
                final_type = raw_final_type.strip()
            else:
                final_type = None

            # Нормализация уровня:
            # - если тип не определён (final_type is None),
            #   то уровень тоже считаем не определённым.
            if final_type is None:
                level = None

            # 3. Маршрутизация на плейбук (deal-level PlaybookVersion)
            # Берём playbook, привязанный к сделке, или глобальный default.
            playbook = await playbook_repo.get_for_deal(doc.deal_id)

            # 4. Атомарное сохранение результатов классификации
            await doc_repo.update_classification(
                doc_id=doc.id,
                doc_type=final_type,
                classification_confidence=final_conf,
                classification_level=level,
                classification_details=details,
                applicable_triggers=applicable_triggers,
                classification_requires_review=classification_requires_review,
                language=language,
                jurisdiction=jurisdiction,
                playbook_version_id=playbook.id if playbook else None,
            )

            # --- Метрики классификации ---
            # ВАЖНО: ошибки при обновлении метрик не должны ломать бизнес-логику.
            try:
                metrics.classification_duration.labels(
                    level=level or "UNKNOWN",
                ).observe(time.time() - start_time)

                metrics.classification_level_distribution.labels(
                    level=level or "UNKNOWN",
                    doc_type=final_type or "UNKNOWN",
                ).inc()
            except Exception:
                logger.exception("classify_document: failed to update classification metrics")

            # 5. Обновляем статус документа на CLASSIFIED
            await doc_repo.update_status(
                doc.id,
                DocumentStatus.CLASSIFIED.value,
                processing_error_details=None,
            )

            # 6. Проверяем, не пора ли запускать run_deal_checks для этого Run.
            # Для непрофессионального программиста:
            # - maybe_start_run_checks сам найдёт Run по run_id,
            #   возьмёт из него deal_id и проверит все документы сделки.
            # - Если все "живые" документы уже CLASSIFIED/COMPLETED,
            #   он один раз поставит задачу workers.run_deal_checks.
            if run_uuid is not None:
                await maybe_start_run_checks(
                    db=uow.session,
                    run_id=run_uuid,
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

    # Важно: здесь больше НЕТ запуска per-document checks.
    # Все проверки по сделке будет запускать отдельный воркер run_deal_checks
    # после того, как авто-стартер решит, что все документы классифицированы.

    duration_ms = int((time.time() - start_time) * 1000)
    return {
        "document_id": document_id,
        "doctype": classification_result.get("final_type")
        if classification_result
        else None,
        "confidence": classification_result.get("final_confidence")
        if classification_result
        else 0.0,
        "language": classification_result.get("language") if classification_result else None,
        "jurisdiction": classification_result.get("jurisdiction") if classification_result else None,
        "playbook_found": playbook is not None,
        "duration_ms": duration_ms,
        # Для внешнего кода: подсказка, нужен ли manual review.
        "classification_requires_review": classification_requires_review if classification_result else None,
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

    Для непрофессионального программиста:
    - Эта функция просто помечает документ как неуспешно обработанный.
    - Причина и сообщение сохраняются в базе для диагностики.
    """
    repo = DocumentRepository(uow.session)
    await repo.set_failed(
        doc_id,
        stage="classify",
        message=message,
        reason="classification_error",
        run_id=run_id,
    )


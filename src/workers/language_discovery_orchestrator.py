# src/workers/language_discovery_orchestrator.py

"""
Language Discovery Orchestrator.

Назначение:
- Определить, какие документы сделки нужно отправить на pre-run language discovery;
- Запускаться автоматически после импорта документов (import_bundle);
- Работать ДО запуска Run, чтобы UI мог показать пользователю список языков
  сделки и дать выбрать primary_language.

Важно:
- Это orchestration-only слой.
- Он НЕ выполняет сам language detection по PDF.
- Он только:
  1) валидирует сделку;
  2) выбирает нужные документы;
  3) находит их latest versions;
  4) ставит document-level tasks:
     - prepare_document_for_language_discovery
     - detect_document_languages_native
     - detect_document_languages_ocr
  5) синхронизирует deal-level aggregate state в processing-совместимое состояние.

Архитектурный принцип:
- fan-out orchestrator -> per-document worker tasks;
- без chord/barrier synchronization;
- aggregate state сделки считается идемпотентно через
  recompute_deal_language_discovery_state() после каждого document task
  и один раз после dispatch.

Согласование с MASBaseTask:
- orchestrator не пишет "failed" за transient broker/task-dispatch проблемы;
- deterministic data problems (например, нет latest version для документа)
  можно помечать как failed на document-level сразу;
- если enqueue шага падает неожиданно, исключение пробрасывается вверх,
  чтобы MASBaseTask выполнил retry.

Антидубль-логика:
- outbox + Celery дают at-least-once delivery;
- поэтому orchestrator должен быть безопасен к повторному запуску;
- duplicate guard реализован через атомарный compare-and-set transition:
  документ можно dispatch'ить только если он ещё в разрешённом состоянии
  language discovery (NULL / failed);
- если другой orchestrator уже успел "захватить" документ, повторный enqueue
  не выполняется.

Операционная оговорка:
- если DB claim прошёл успешно, а publish в broker не удался,
  документ может временно остаться в pending без реально доставленной task;
- это нужно закрывать отдельным reconcile / stuck-pending repair job.

Routing policy:
- office filetypes всегда идут через prepare_document_for_language_discovery;
- PDF идёт в native detector;
- image filetypes идут в OCR detector;
- pipeline_strategy / extraction_strategy / ocr_confidence используются
  только как secondary hints, если origin_filetype не даёт однозначный ответ;
- если route неоднозначен, предпочитаем prepare stage как safest path для
  conversion-first language discovery.

Важное правило работы с ORM (snapshot architecture):
- SQLAlchemy asyncpg не допускает синхронный lazy reload атрибутов ORM-объектов
  после await-границы (MissingGreenlet).
- Поэтому orchestration-слой снимает snapshots ORM-объектов сразу после загрузки
  и дальше работает только с примитивами.
- Shared snapshot-контракты живут в core.pipeline_snapshots.
- Все snapshot-типы используют shared контракт из core.pipeline_snapshots
  (DocumentSnapshot, VersionSnapshot). Локальных приватных snapshot-классов нет.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import PermanentError
from core.logging import get_logger
from core.pipeline_snapshots import (
    DocumentSnapshot,
    VersionSnapshot,
    snapshot_document,
    snapshot_version,
)
from db.repositories.audit_repo import AuditRepository
from db.repositories.deal_repo import DealRepository
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.uow import db_uow
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from mas_queue.task_dispatcher import send_task_with_context
from services.deal_language_discovery_service import (
    recompute_deal_language_discovery_state,
)

logger = get_logger(__name__)

PREPARE_LANGUAGE_DISCOVERY_TASK_NAME = "workers.prepare_document_for_language_discovery"
NATIVE_LANGUAGE_DISCOVERY_TASK_NAME = "workers.detect_document_languages_native"
OCR_LANGUAGE_DISCOVERY_TASK_NAME = "workers.detect_document_languages_ocr"

LANGUAGE_DISCOVERY_STARTED = "LANGUAGE_DISCOVERY_STARTED"
LANGUAGE_DISCOVERY_COMPLETED = "LANGUAGE_DISCOVERY_COMPLETED"
LANGUAGE_DISCOVERY_FAILED = "LANGUAGE_DISCOVERY_FAILED"

REDISTRIBUTABLE_LANGUAGE_STATES: list[str | None] = [None, "failed"]

OCR_FILETYPES = {
    "png",
    "jpg",
    "jpeg",
    "tif",
    "tiff",
    "bmp",
    "webp",
}

OFFICE_FILETYPES = {
    "doc",
    "docx",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "odt",
    "ods",
    "odp",
    "rtf",
    "csv",
    "html",
    "htm",
}

OCR_PIPELINE_STRATEGIES = {
    "pdf_ocr",
    "docx_via_pdf_ocr",
    "image_ocr",
    "ocr_only",
    "hybrid_ocr",
}

NATIVE_PIPELINE_STRATEGIES = {
    "pdf_native",
    "docx_via_pdf_native",
}

OCR_EXTRACTION_STRATEGIES = {
    "ocr_only",
    "hybrid",
}

NATIVE_EXTRACTION_STRATEGIES = {
    "pdfplumber",
}

DEFAULT_OCR_CONFIDENCE_THRESHOLD = 0.70


# ─── Route helpers ────────────────────────────────────────────────────────────


def _select_language_discovery_task_name(
    ver_snap: VersionSnapshot,
) -> str:
    """
    Выбрать worker для language discovery на уровне документа.

    Принимает VersionSnapshot из core.pipeline_snapshots, а не ORM-объект,
    чтобы гарантировать отсутствие обращений к expired ORM-атрибутам
    через await-границу.

    Production contract:
    1) Office filetypes -> prepare_document_for_language_discovery;
    2) PDF -> native detector;
    3) image filetypes -> OCR detector;
    4) strategy hints используются только как secondary fallback;
    5) если route всё ещё неоднозначен, выбираем prepare stage как safest path.
    """
    if ver_snap.origin_filetype in OFFICE_FILETYPES:
        return PREPARE_LANGUAGE_DISCOVERY_TASK_NAME

    if ver_snap.origin_filetype == "pdf":
        return NATIVE_LANGUAGE_DISCOVERY_TASK_NAME

    if ver_snap.origin_filetype in OCR_FILETYPES:
        return OCR_LANGUAGE_DISCOVERY_TASK_NAME

    if ver_snap.pipeline_strategy in OCR_PIPELINE_STRATEGIES:
        return OCR_LANGUAGE_DISCOVERY_TASK_NAME

    if ver_snap.pipeline_strategy in NATIVE_PIPELINE_STRATEGIES:
        return NATIVE_LANGUAGE_DISCOVERY_TASK_NAME

    if ver_snap.extraction_strategy in OCR_EXTRACTION_STRATEGIES:
        return OCR_LANGUAGE_DISCOVERY_TASK_NAME

    if ver_snap.extraction_strategy in NATIVE_EXTRACTION_STRATEGIES:
        return NATIVE_LANGUAGE_DISCOVERY_TASK_NAME

    if (
        ver_snap.ocr_confidence is not None
        and ver_snap.ocr_confidence < DEFAULT_OCR_CONFIDENCE_THRESHOLD
    ):
        return OCR_LANGUAGE_DISCOVERY_TASK_NAME

    return PREPARE_LANGUAGE_DISCOVERY_TASK_NAME


# ─── Audit helper ─────────────────────────────────────────────────────────────


async def _write_deal_audit(
    *,
    db: AsyncSession,
    action: str,
    deal_id: uuid.UUID,
    tenant_id: uuid.UUID,
    details: dict[str, Any],
) -> None:
    audit_repo = AuditRepository(db)
    try:
        await audit_repo.log(
            tenant_id=tenant_id,
            deal_id=deal_id,
            action=action,
            actor="system",
            actor_role="worker",
            details=details,
        )
    except Exception:
        logger.exception(
            "Language discovery orchestrator: failed to write audit log",
            deal_id=str(deal_id),
            tenant_id=str(tenant_id),
            action=action,
        )


# ─── Celery task entrypoint ───────────────────────────────────────────────────


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.start_language_discovery",
    track_job=False,
    queue="default",
)
def start_language_discovery(
    self,
    deal_id: str,
    tenant_id: str,
    document_ids: list[str] | None = None,
    stage_execution_id: str | None = None,
    orchestration_strategy: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Sync Celery entrypoint для запуска pre-run language discovery по сделке.

    Для непрофессионального программиста:
    - этот worker не анализирует PDF сам;
    - он только определяет, какие документы нужно обработать,
      и ставит по одному document-level worker'у на каждый документ.

    Параметры:
    - deal_id: UUID сделки;
    - tenant_id: UUID арендатора;
    - document_ids: опционально ограничивает запуск конкретными документами.

    Возвращает:
    - агрегированную информацию о том, сколько задач поставлено в очередь
      и сколько документов было пропущено duplicate guard'ом.
    """
    _ = self

    async def _wrapper() -> dict[str, Any]:
        async with db_uow() as uow:
            return await _start_language_discovery_async(
                deal_id=deal_id,
                tenant_id=tenant_id,
                document_ids=document_ids,
                db=uow.session,
            )

    return run_async(_wrapper())


# ─── Async core ───────────────────────────────────────────────────────────────


async def _start_language_discovery_async(
    *,
    deal_id: str,
    tenant_id: str,
    document_ids: list[str] | None,
    db: AsyncSession,
) -> dict[str, Any]:
    """
    Async-ядро orchestration-only language discovery.

    Архитектура read / snapshot / decision / write:
    - READ:     загружаем ORM-объекты (Deal, Documents, Versions);
    - SNAPSHOT: немедленно снимаем snapshots через core.pipeline_snapshots;
    - DECISION: выбираем task routing по snapshot-данным;
    - WRITE:    claim document + enqueue Celery task.

    Алгоритм:
    1) валидируем deal;
    2) переводим deal-level discovery в processing;
    3) выбираем документы-кандидаты и снимаем snapshots;
    4) для каждого документа пытаемся атомарно "захватить" его под dispatch;
    5) находим latest version snapshot и ставим document-level task;
    6) пересчитываем aggregate state сделки.
    """
    deal_uuid = uuid.UUID(deal_id)
    tenant_uuid = uuid.UUID(tenant_id)
    requested_doc_ids: list[uuid.UUID] = (
        [uuid.UUID(x) for x in document_ids] if document_ids else []
    )

    logger.info(
        "Starting language discovery orchestration",
        deal_id=deal_id,
        tenant_id=str(tenant_uuid),
        requested_document_ids=(
            [str(x) for x in requested_doc_ids] if requested_doc_ids else None
        ),
    )

    deal_repo = DealRepository(db)
    doc_repo = DocumentRepository(db)
    ver_repo = DocumentVersionRepository(db)

    # ── READ + validate: Deal ─────────────────────────────────────────────────

    deal = await deal_repo.get_by_id(deal_uuid)
    if not deal:
        raise PermanentError(f"Deal {deal_id} not found for language discovery orchestration")
    # deal ORM-объект больше не используется после этой точки

    await _write_deal_audit(
        db=db,
        action=LANGUAGE_DISCOVERY_STARTED,
        deal_id=deal_uuid,
        tenant_id=tenant_uuid,
        details={
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "requested_document_ids": (
                [str(x) for x in requested_doc_ids] if requested_doc_ids else []
            ),
            "documents_requested_count": len(requested_doc_ids) if requested_doc_ids else None,
            "source": "language_discovery_orchestrator",
        },
    )

    try:
        await deal_repo.update_language_discovery_status(
            deal_uuid,
            "processing",
        )

        # ── READ + SNAPSHOT: Documents ────────────────────────────────────────

        docs = await doc_repo.get_for_language_discovery(
            deal_id=deal_uuid,
            document_ids=requested_doc_ids or None,
            include_statuses=REDISTRIBUTABLE_LANGUAGE_STATES,
        )

        if not docs:
            recomputed = await recompute_deal_language_discovery_state(
                db=db,
                deal_id=deal_uuid,
            )

            result = {
                "deal_id": deal_id,
                "tenant_id": tenant_id,
                "documents_total": 0,
                "documents_enqueued": 0,
                "documents_skipped": 0,
                "documents_skipped_as_duplicate": 0,
                "documents_failed_pre_dispatch": 0,
                "status": str(recomputed.get("language_discovery_status", "completed")),
                "languages": list(recomputed.get("languages", [])),
                "enqueued_document_ids": [],
                "skipped_document_ids": [],
                "duplicate_guard_skipped_document_ids": [],
                "failed_pre_dispatch_document_ids": [],
            }

            await _write_deal_audit(
                db=db,
                action=LANGUAGE_DISCOVERY_COMPLETED,
                deal_id=deal_uuid,
                tenant_id=tenant_uuid,
                details={
                    "deal_id": deal_id,
                    "tenant_id": tenant_id,
                    "documents_total": result["documents_total"],
                    "documents_enqueued": result["documents_enqueued"],
                    "documents_skipped": result["documents_skipped"],
                    "documents_skipped_as_duplicate": result["documents_skipped_as_duplicate"],
                    "documents_failed_pre_dispatch": result["documents_failed_pre_dispatch"],
                    "detected_languages": result["languages"],
                    "language_discovery_status": result["status"],
                    "source": "language_discovery_orchestrator",
                },
            )

            logger.info(
                "Language discovery orchestration completed: no documents selected",
                **result,
            )
            return result

        # Снимаем DocumentSnapshot сразу после batch-read через shared контракт.
        # detected_languages нам нужен для preserve_detected_languages ниже —
        # он есть в DocumentSnapshot.detected_languages.
        doc_snaps: list[DocumentSnapshot] = [snapshot_document(doc) for doc in docs]

        # ── READ + SNAPSHOT: Versions ─────────────────────────────────────────

        latest_versions_orm = await ver_repo.get_latest_for_documents(
            [ds.document_id for ds in doc_snaps]
        )

        # Снимаем VersionSnapshot сразу после batch-read через shared контракт.
        # VersionSnapshot содержит все нужные поля для routing:
        # origin_filetype, pipeline_strategy, extraction_strategy, ocr_confidence.
        version_snaps: dict[uuid.UUID, VersionSnapshot] = {
            doc_id: snapshot_version(ver) for doc_id, ver in latest_versions_orm.items()
        }

        # ── DECISION + WRITE: per-document loop ──────────────────────────────

        enqueued_document_ids: list[str] = []
        duplicate_guard_skipped_document_ids: list[str] = []
        failed_pre_dispatch_document_ids: list[str] = []

        for doc_snap in doc_snaps:
            ver_snap = version_snaps.get(doc_snap.document_id)

            if ver_snap is None:
                logger.warning(
                    "Language discovery orchestration: latest version not found, document marked failed",
                    deal_id=deal_id,
                    tenant_id=tenant_id,
                    document_id=doc_snap.document_id_str,
                )

                await doc_repo.update_language_discovery(
                    doc_snap.document_id,
                    detected_languages=[],
                    status="failed",
                )
                failed_pre_dispatch_document_ids.append(doc_snap.document_id_str)
                continue

            # detected_languages берём из DocumentSnapshot.
            # tuple → list для совместимости с API repo-метода.
            preserve_languages: list[str] | None = (
                list(doc_snap.detected_languages) if doc_snap.detected_languages else None
            )

            claimed_doc = await doc_repo.try_mark_language_discovery_pending(
                doc_snap.document_id,
                allowed_current_statuses=REDISTRIBUTABLE_LANGUAGE_STATES,
                preserve_detected_languages=preserve_languages,
            )

            if not claimed_doc:
                duplicate_guard_skipped_document_ids.append(doc_snap.document_id_str)
                logger.info(
                    "Language discovery orchestration: document already claimed by another worker",
                    deal_id=deal_id,
                    tenant_id=tenant_id,
                    document_id=doc_snap.document_id_str,
                )
                continue

            task_name = _select_language_discovery_task_name(ver_snap)

            try:
                send_task_with_context(
                    task_name,
                    kwargs={
                        "document_id": doc_snap.document_id_str,
                        "document_version_id": ver_snap.version_id_str,
                        "deal_id": deal_id,
                        "tenant_id": tenant_id,
                    },
                    retry=True,
                    retry_policy={
                        "max_retries": 3,
                        "interval_start": 1,
                        "interval_step": 2,
                        "interval_max": 5,
                    },
                )
            except Exception as e:
                logger.exception(
                    "Failed to enqueue language detection task",
                    deal_id=deal_id,
                    tenant_id=tenant_id,
                    document_id=doc_snap.document_id_str,
                    document_version_id=ver_snap.version_id_str,
                    task_name=task_name,
                    pipeline_strategy=ver_snap.pipeline_strategy,
                    extraction_strategy=ver_snap.extraction_strategy,
                    ocr_confidence=ver_snap.ocr_confidence,
                    origin_filetype=ver_snap.origin_filetype,
                    error=str(e),
                )
                raise

            enqueued_document_ids.append(doc_snap.document_id_str)

            logger.info(
                "Language discovery orchestration: detection task enqueued",
                deal_id=deal_id,
                tenant_id=tenant_id,
                document_id=doc_snap.document_id_str,
                document_version_id=ver_snap.version_id_str,
                task_name=task_name,
                pipeline_strategy=ver_snap.pipeline_strategy,
                extraction_strategy=ver_snap.extraction_strategy,
                ocr_confidence=ver_snap.ocr_confidence,
                origin_filetype=ver_snap.origin_filetype,
            )

        recomputed = await recompute_deal_language_discovery_state(
            db=db,
            deal_id=deal_uuid,
        )

        skipped_document_ids = (
            duplicate_guard_skipped_document_ids + failed_pre_dispatch_document_ids
        )

        result = {
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "documents_total": len(doc_snaps),
            "documents_enqueued": len(enqueued_document_ids),
            "documents_skipped": len(skipped_document_ids),
            "documents_skipped_as_duplicate": len(duplicate_guard_skipped_document_ids),
            "documents_failed_pre_dispatch": len(failed_pre_dispatch_document_ids),
            "status": str(recomputed.get("language_discovery_status", "pending")),
            "languages": list(recomputed.get("languages", [])),
            "enqueued_document_ids": enqueued_document_ids,
            "skipped_document_ids": skipped_document_ids,
            "duplicate_guard_skipped_document_ids": duplicate_guard_skipped_document_ids,
            "failed_pre_dispatch_document_ids": failed_pre_dispatch_document_ids,
        }

        await _write_deal_audit(
            db=db,
            action=LANGUAGE_DISCOVERY_COMPLETED,
            deal_id=deal_uuid,
            tenant_id=tenant_uuid,
            details={
                "deal_id": deal_id,
                "tenant_id": tenant_id,
                "documents_total": result["documents_total"],
                "documents_enqueued": result["documents_enqueued"],
                "documents_skipped": result["documents_skipped"],
                "documents_skipped_as_duplicate": result["documents_skipped_as_duplicate"],
                "documents_failed_pre_dispatch": result["documents_failed_pre_dispatch"],
                "detected_languages": result["languages"],
                "language_discovery_status": result["status"],
                "source": "language_discovery_orchestrator",
            },
        )

        logger.info(
            "Language discovery orchestration completed",
            **result,
        )

        return result

    except Exception as exc:
        await _write_deal_audit(
            db=db,
            action=LANGUAGE_DISCOVERY_FAILED,
            deal_id=deal_uuid,
            tenant_id=tenant_uuid,
            details={
                "deal_id": deal_id,
                "tenant_id": tenant_id,
                "requested_document_ids": (
                    [str(x) for x in requested_doc_ids] if requested_doc_ids else []
                ),
                "error": str(exc),
                "error_type": exc.__class__.__name__,
                "workflow_outcome": "failed_before_completion",
                "source": "language_discovery_orchestrator",
            },
        )
        raise

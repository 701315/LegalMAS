# src/services/import_bundle_use_case.py

"""
ImportBundleUseCase — application service для первичного импорта файлов в систему.

Назначение:
- Реализует бизнес-логику импорта документов в рамках сделки.
- Принимает ImportBundleCommand, выполняет импорт, возвращает ImportBundleResult.
- Работает как первый этап пайплайна: import -> language_discovery -> ...
- НЕ запускает downstream-задачи напрямую — только пишет outbox events.

Что делает use case:
- Проверка идемпотентности (если ключ уже был — вернуть кэшированный результат).
- Проверка tenant ownership для deal (security boundary).
- Распаковка ZIP или приём одиночного файла.
- Валидация файлов (расширение, размер, сигнатура / magic bytes).
- Дедупликация по SHA-256 внутри одной сделки.
- Создание Document + DocumentVersion в БД.
- Загрузка оригиналов в MinIO (artifact store).
- Карантин для некорректных / повреждённых / неподдерживаемых файлов.
- Запись audit events (IMPORT, IMPORT_FILE_QUARANTINED, IMPORT_FILE_UNSUPPORTED).
- Запись outbox event для workers.start_language_discovery (transactional outbox).

Архитектура:
- Use case живёт в services layer — это application orchestration.
- Не зависит от Celery worker context.
- Использует repositories для DB access.
- Использует OutboxService для durable task enqueue.
- Использует ArtifactStore для MinIO upload.
- Helpers (SHA-256, ZIP extraction) вынесены в import_helpers.

Транзакционность:
- Use case выполняется внутри активной DB transaction, предоставленной вызывающим кодом.
- Outbox event пишется в той же транзакции.
- Если транзакция откатывается — outbox event тоже откатывается.
- Публикация outbox events в Celery делается отдельным relay процессом после commit.

Идемпотентность:
- Если idempotency_key передан и уже есть в БД со status=completed — возвращается
  кэшированный result без повторного импорта.
- Если idempotency_key передан и есть в БД со status=processing — выбрасывается
  IdempotencyConflictError (защита от параллельного выполнения).

Для непрофессионального программиста:
- Use case — это «сценарий использования», то есть что должно произойти,
  когда пользователь загружает файлы.
- Функция execute(...) принимает команду на импорт и делает всё необходимое:
  проверку прав, распаковку ZIP, проверку файлов, сохранение в БД и MinIO.
- Если что-то пошло не так — откатывает всё, что успело записаться в БД.
- Если всё хорошо — сохраняет результат и создаёт событие для следующего этапа
  (language discovery).
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
import zipfile
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.constants import DocumentStatus
from core.exceptions import IdempotencyConflictError, PermanentError
from core.logging import get_logger
from db.repositories import (
    AuditRepository,
    BundleRepository,
    DealRepository,
    DocumentRepository,
    DocumentVersionRepository,
    IdempotencyRepository,
)
from ops.metrics import get_metrics
from services.extract_router import (
    ExtractRoutingDecision,
    decide_extraction_strategy,
)
from services.file_validator import (
    FileStatus,
    validate_file,
)
from services.import_helpers import (
    _build_language_discovery_outbox_dedup_key,
    _extract_zip_safe,
    _get_content_type,
    compute_sha256,
)
from services.import_types import ImportBundleCommand, ImportBundleResult
from services.outbox_service import OutboxService
from storage.artifact_store import ArtifactPath, ArtifactStore

logger = get_logger(__name__)


class ImportBundleUseCase:
    """
    Application service для выполнения импорта bundle в рамках сделки.

    Use case инкапсулирует полную бизнес-логику импорта:
    - idempotency check;
    - tenant ownership validation;
    - file processing (ZIP extraction, validation, deduplication);
    - DB persistence (Bundle, Document, DocumentVersion);
    - artifact storage (MinIO);
    - audit logging;
    - outbox event creation для downstream tasks.

    Для непрофессионального программиста:
    - Это главный координатор процесса импорта.
    - Он знает, в каком порядке делать операции и как обрабатывать ошибки.
    - Celery worker только вызывает этот use case, а сам use case управляет всем.
    """

    def __init__(self, db: AsyncSession):
        """
        Инициализировать use case с активной DB session.

        Параметры:
        - db: AsyncSession из db_uow(), в рамках которой выполняется весь импорт.
        """
        self.db = db

    async def execute(self, command: ImportBundleCommand) -> ImportBundleResult:
        """
        Выполнить импорт bundle для указанной сделки.

        Параметры:
        - command: ImportBundleCommand с параметрами импорта.

        Возвращает:
        - ImportBundleResult с итогами импорта.

        Исключения:
        - PermanentError если файл не найден, ZIP повреждён, или deal не существует.
        - IdempotencyConflictError если idempotency_key уже используется активной операцией.
        """
        return await _import_bundle_async(
            command=command,
            db=self.db,
        )


async def _check_idempotency(
    tenant_id: str,
    key: str,
    db: AsyncSession,
) -> ImportBundleResult | None:
    """
    Проверка идемпотентности импорта.

    Если idempotency_key уже был использован и операция завершилась успешно —
    вернуть кэшированный типизированный результат.

    Параметры:
    - tenant_id: ID tenant'а (для namespace idempotency keys).
    - key: idempotency key.
    - db: AsyncSession.

    Возвращает:
    - ImportBundleResult, если операция уже выполнялась и status=completed;
    - None, если это первое выполнение с таким ключом или прошлый запуск был failed.

    Исключения:
    - IdempotencyConflictError если операция с таким ключом уже в процессе выполнения.

    Для непрофессионального программиста:
    - Если пользователь дважды кликнул «Импортировать» с одним и тем же ключом,
      второй раз мы не будем делать импорт заново, а вернём результат первого.
    - Если первый импорт ещё не закончился, второй запрос получит ошибку «уже выполняется».
    """
    expires_at = datetime.now(UTC) + timedelta(days=7)

    repo = IdempotencyRepository(db)
    record, is_new = await repo.get_or_create(
        tenant_id=uuid.UUID(tenant_id),
        endpoint="import",
        key=key,
        expires_at=expires_at,
    )
    if is_new:
        return None
    if record.status == "completed":
        return ImportBundleResult.from_dict(record.result)
    if record.status == "processing":
        raise IdempotencyConflictError(
            f"Import with key '{key}' is already in progress"
        )
    if record.status == "failed":
        return None
    return None


async def _import_bundle_async(
    command: ImportBundleCommand,
    db: AsyncSession,
) -> ImportBundleResult:
    """
    Координирующая функция для импорта bundle.

    Выполняет:
    - idempotency check;
    - проверку существования source_path;
    - распаковку ZIP (если это ZIP) или приём одиночного файла;
    - вызов _async_import для обработки файлов.

    Параметры:
    - command: ImportBundleCommand.
    - db: AsyncSession.

    Возвращает:
    - ImportBundleResult.

    Для непрофессионального программиста:
    - Это главная функция, которая решает, что делать:
      - если это ZIP — распаковать;
      - если одиночный файл — обработать как есть;
      - если уже был импорт с таким ключом — вернуть результат того импорта.
    """
    logger.info(
        "Starting import",
        extra={
            "deal_id": command.deal_id,
            "tenant_id": command.tenant_id,
            "source_path": command.source_path,
            "idempotency_key": command.idempotency_key,
            "run_id": command.run_id,
        },
    )

    metrics = get_metrics()

    if command.idempotency_key:
        cached = await _check_idempotency(
            tenant_id=command.tenant_id,
            key=command.idempotency_key,
            db=db,
        )
        if cached is not None:
            logger.info(
                "Idempotent replay — returning cached result",
                extra={"idempotency_key": command.idempotency_key},
            )
            return cached

    if not os.path.exists(command.source_path):
        metrics.import_fail.labels(reason="source_not_found").inc()
        raise PermanentError(
            f"Source file not found: {command.source_path}",
            details={"source_path": command.source_path},
        )

    if zipfile.is_zipfile(command.source_path):
        with tempfile.TemporaryDirectory(prefix="mas_import_") as tmp_dir:
            file_list = _extract_zip_safe(command.source_path, tmp_dir)
            result = await _async_import(
                deal_id=command.deal_id,
                tenant_id=command.tenant_id,
                file_list=file_list,
                db=db,
                run_id=command.run_id,
                idempotency_key=command.idempotency_key,
            )
    else:
        result = await _async_import(
            deal_id=command.deal_id,
            tenant_id=command.tenant_id,
            file_list=[("", command.source_path)],
            db=db,
            run_id=command.run_id,
            idempotency_key=command.idempotency_key,
        )

    logger.info(
        "Import completed",
        extra={
            "deal_id": command.deal_id,
            "tenant_id": command.tenant_id,
            "imported": result.imported_count,
            "quarantined": result.quarantine_count,
            "duplicates": result.duplicate_count,
            "skipped": result.skipped_count,
            "committed": result.committed,
        },
    )
    return result


async def _async_import(
    deal_id: str,
    tenant_id: str,
    file_list: list[tuple[str, str]],
    db: AsyncSession,
    run_id: str | None = None,
    idempotency_key: str | None = None,
) -> ImportBundleResult:
    """
    Основная логика импорта файлов.

    Для каждого файла в file_list:
    - валидация (расширение, размер, magic bytes);
    - дедупликация по SHA-256 внутри сделки;
    - создание Document + DocumentVersion в БД;
    - загрузка оригинала в MinIO;
    - quarantine для невалидных / неподдерживаемых файлов;
    - audit logging.

    После обработки всех файлов:
    - финализация Bundle (mark_completed);
    - запись outbox event для workers.start_language_discovery (если есть импортированные документы);
    - сохранение idempotency result.

    Параметры:
    - deal_id: ID сделки.
    - tenant_id: ID tenant'а (для ownership check и namespace).
    - file_list: список (folder_path, filepath) для обработки.
    - db: AsyncSession.
    - run_id: опциональный ID Run'а (для audit trail).
    - idempotency_key: опциональный ключ идемпотентности.

    Возвращает:
    - ImportBundleResult с итогами импорта.

    Важно:
    - Эта функция НЕ отправляет сообщения напрямую в брокер.
    - Все downstream actions фиксируются через outbox в той же транзакции.
    - Relay/dispatcher публикует outbox events в Celery уже после commit.

    Для непрофессионального программиста:
    - Это самая «рабочая» функция, которая обрабатывает каждый файл по очереди:
      проверяет его, считает хэш, сохраняет в БД и MinIO.
    - Если файл битый или неподдерживаемый — помещает его в карантин.
    - Если файл дубликат — пропускает.
    - В конце создаёт событие для следующего этапа (определение языка).
    """
    metrics = get_metrics()

    store = ArtifactStore(settings)
    imported_ids: list[str] = []
    quarantine_ids: list[str] = []
    duplicate_count = 0
    skipped_count = 0
    language_discovery_requested = False

    bundle_repo = BundleRepository(db)
    doc_repo = DocumentRepository(db)
    ver_repo = DocumentVersionRepository(db)
    audit_repo = AuditRepository(db)
    outbox = OutboxService(db)

    deal_uuid = uuid.UUID(deal_id)
    tenant_uuid = uuid.UUID(tenant_id)
    run_uuid = uuid.UUID(run_id) if run_id else None

    deal_repo = DealRepository(db)
    await deal_repo.assert_tenant_owns_deal(
        deal_id=deal_uuid,
        tenant_id=tenant_uuid,
    )

    bundle = await bundle_repo.create(
        deal_id=deal_uuid,
        source_type="zip" if len(file_list) > 1 else "local",
        idempotency_key=idempotency_key,
        status="processing",
        file_count=0,
    )

    for folder_path, filepath in file_list:
        filename = os.path.basename(filepath)
        validation = validate_file(filepath)

        if validation.status == FileStatus.SKIP:
            skipped_count += 1
            logger.debug(
                "File skipped",
                extra={
                    "filename": filename,
                    "reason": validation.reason,
                },
            )
            continue

        if validation.status == FileStatus.QUARANTINE:
            q_doc = await doc_repo.create(
                deal_id=deal_uuid,
                bundle_id=bundle.id,
                filename=filename,
                folder_path=folder_path or None,
                status=DocumentStatus.QUARANTINE.value,
            )
            await ver_repo.create(
                document_id=q_doc.id,
                version_num=1,
                original_ref=None,
                origin_filetype=validation.filetype,
                origin_extension=validation.original_extension,
            )

            try:
                with open(filepath, "rb") as f:
                    file_bytes = f.read()
                artifact_path = ArtifactPath.original(tenant_id, deal_id, str(q_doc.id))
                store.put_file(
                    artifact_path + (validation.original_extension or ".bin"),
                    file_bytes,
                )
            except Exception:
                logger.warning(
                    "Import worker: failed to store quarantined original",
                    extra={
                        "filename": filename,
                        "doc_id": str(q_doc.id),
                    },
                )

            quarantine_ids.append(str(q_doc.id))
            logger.warning(
                "File quarantined",
                extra={
                    "filename": filename,
                    "reason": validation.reason,
                    "doc_id": str(q_doc.id),
                },
            )

            metrics.quarantine.labels(
                reason=validation.reason or "import_quarantine"
            ).inc()

            try:
                await audit_repo.log(
                    tenant_id=tenant_uuid,
                    deal_id=deal_uuid,
                    action="IMPORT_FILE_QUARANTINED",
                    actor="system",
                    actor_role="worker",
                    details={
                        "bundle_id": str(bundle.id),
                        "document_id": str(q_doc.id),
                        "filename": filename,
                        "folder_path": folder_path or None,
                        "reason": validation.reason,
                        "filetype": validation.filetype,
                        "source_extension": validation.original_extension,
                        "run_id": str(run_uuid) if run_uuid else None,
                    },
                )
            except Exception:
                logger.warning(
                    "Import worker: failed to write audit log for IMPORT_FILE_QUARANTINED",
                    extra={
                        "doc_id": str(q_doc.id),
                        "filename": filename,
                    },
                )

            continue

        sha256 = compute_sha256(filepath)
        existing = await doc_repo.get_by_sha256(deal_uuid, sha256)
        if existing:
            duplicate_count += 1
            logger.info(
                "Duplicate file detected",
                extra={
                    "filename": filename,
                    "sha256": sha256[:16],
                    "existing_doc": str(existing.id),
                },
            )
            continue

        try:
            with open(filepath, "rb") as f:
                file_bytes = f.read()
        except Exception as e:
            metrics.import_fail.labels(reason="read_error").inc()
            logger.error(
                "Failed to read file during import",
                extra={
                    "filename": filename,
                    "error": str(e),
                },
            )
            continue

        source_ext = validation.original_extension
        doc = await doc_repo.create(
            deal_id=deal_uuid,
            bundle_id=bundle.id,
            filename=filename,
            folder_path=folder_path or None,
            sha256_file=sha256,
            status=DocumentStatus.PENDING.value,
            source_extension=source_ext,
            source_filetype=validation.filetype,
        )

        ext = source_ext or ".pdf"

        artifact_path = ArtifactPath.original(tenant_id, deal_id, str(doc.id))
        original_ref = store.put_file(
            artifact_path + ext,
            file_bytes,
            content_type=_get_content_type(validation.filetype),
        )

        version = await ver_repo.create(
            document_id=doc.id,
            version_num=1,
            original_ref=original_ref,
            origin_filetype=validation.filetype,
            origin_extension=source_ext,
        )

        imported_ids.append(str(doc.id))

        logger.info(
            "Document imported",
            extra={
                "doc_id": str(doc.id),
                "document_version_id": str(version.id),
                "filename": filename,
                "folder_path": folder_path,
                "filetype": validation.filetype,
                "sha256": sha256[:16],
            },
        )

        decision: ExtractRoutingDecision = decide_extraction_strategy(validation.filetype)

        if decision.action in ("extract", "convert_then_extract") and decision.extractor_task:
            logger.info(
                "Document ready for analysis pipeline",
                extra={
                    "doc_id": str(doc.id),
                    "filetype": validation.filetype,
                    "decision_action": decision.action,
                    "reason": decision.reason,
                },
            )
        else:
            await doc_repo.set_quarantined(
                doc.id,
                stage="import",
                message=(
                    "Тип файла не поддерживается пайплайном анализа: "
                    f"{validation.filetype or 'unknown'}"
                ),
                reason=decision.reason or "unsupported_filetype",
                run_id=run_uuid,
            )
            quarantine_ids.append(str(doc.id))
            imported_ids.remove(str(doc.id))

            logger.info(
                "File type not supported by analysis pipeline — quarantined",
                extra={
                    "filename": filename,
                    "filetype": validation.filetype,
                    "reason": decision.reason,
                    "doc_id": str(doc.id),
                },
            )

            metrics.quarantine.labels(
                reason=decision.reason or "unsupported_filetype"
            ).inc()

            try:
                await audit_repo.log(
                    tenant_id=tenant_uuid,
                    deal_id=deal_uuid,
                    action="IMPORT_FILE_UNSUPPORTED",
                    actor="system",
                    actor_role="worker",
                    details={
                        "bundle_id": str(bundle.id),
                        "document_id": str(doc.id),
                        "filename": filename,
                        "folder_path": folder_path or None,
                        "filetype": validation.filetype,
                        "source_extension": source_ext,
                        "decision_action": decision.action,
                        "reason": decision.reason or "unsupported_filetype",
                        "run_id": str(run_uuid) if run_uuid else None,
                    },
                )
            except Exception:
                logger.warning(
                    "Import worker: failed to write audit log for IMPORT_FILE_UNSUPPORTED",
                    extra={
                        "doc_id": str(doc.id),
                        "filename": filename,
                    },
                )

            continue

    bundle = await bundle_repo.mark_completed(
        bundle.id,
        file_count=len(imported_ids) + len(quarantine_ids),
    )

    try:
        await audit_repo.log(
            tenant_id=tenant_uuid,
            deal_id=deal_uuid,
            action="IMPORT",
            actor="system",
            actor_role="worker",
            details={
                "bundle_id": str(bundle.id),
                "total_files": len(file_list),
                "imported_count": len(imported_ids),
                "quarantine_count": len(quarantine_ids),
                "duplicate_count": duplicate_count,
                "skipped_count": skipped_count,
                "run_id": str(run_uuid) if run_uuid else None,
                "source_type": bundle.source_type,
            },
        )
    except Exception:
        logger.warning(
            "Import worker: failed to write audit log for IMPORT",
            extra={
                "deal_id": deal_id,
                "bundle_id": str(bundle.id),
            },
        )

    if imported_ids:
        await outbox.enqueue_task(
            task_name="workers.start_language_discovery",
            payload={
                "deal_id": deal_id,
                "tenant_id": tenant_id,
                "document_ids": imported_ids,
            },
            aggregate_type="deal",
            aggregate_id=str(deal_uuid),
            dedup_key=_build_language_discovery_outbox_dedup_key(
                deal_id=deal_id,
                bundle_id=str(bundle.id),
                document_ids=imported_ids,
            ),
            headers={
                "event_type": "LANGUAGE_DISCOVERY_REQUESTED",
                "source": "workers.import_bundle",
                "bundle_id": str(bundle.id),
            },
        )
        language_discovery_requested = True

        logger.info(
            "Language discovery outbox event recorded",
            extra={
                "deal_id": deal_id,
                "tenant_id": tenant_id,
                "bundle_id": str(bundle.id),
                "document_ids": imported_ids,
            },
        )
    else:
        logger.info(
            "Language discovery outbox event skipped: no imported documents",
            extra={
                "deal_id": deal_id,
                "tenant_id": tenant_id,
                "bundle_id": str(bundle.id),
            },
        )

    result = ImportBundleResult(
        bundle_id=str(bundle.id),
        document_ids=imported_ids,
        quarantined_ids=quarantine_ids,
        imported_count=len(imported_ids),
        quarantine_count=len(quarantine_ids),
        duplicate_count=duplicate_count,
        skipped_count=skipped_count,
        committed=True,
        language_discovery_requested=language_discovery_requested,
    )

    if idempotency_key:
        idem_repo = IdempotencyRepository(db)
        record, _ = await idem_repo.get_or_create(
            tenant_uuid,
            "import",
            idempotency_key,
        )
        response_hash = hashlib.sha256(str(result.to_dict()).encode()).hexdigest()
        await idem_repo.mark_completed(
            record.id,
            response_hash=response_hash,
            result=result.to_dict(),
        )

    return result



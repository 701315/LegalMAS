# src/workers/import_worker.py

"""
Import Worker — production.

Назначение:
- Первичный импорт файлов в систему.
- Работает как первый этап пайплайна: import -> …, но
  НЕ запускает последующие стадии напрямую — только создаёт документы и версии.

Основные функции:
- Распаковка ZIP с сохранением структуры папок (folder_path).
- Безопасная распаковка ZIP без path traversal / Zip Slip.
- Валидация файлов (расширение, размер, сигнатура / magic bytes).
- Дедупликация по SHA-256 внутри одной сделки.
- Идемпотентность через IdempotencyKey.
- Карантин для некорректных / повреждённых / неподдерживаемых файлов.
- Загрузка оригиналов в MinIO и создание Document + DocumentVersion.
- Определение исходного формата файла (source_extension, source_filetype).
- Подготовка документов к дальнейшему пайплайну без прямого запуска downstream-воркеров.
- Вместо прямого enqueue downstream задач пишет outbox-событие
  LANGUAGE_DISCOVERY_REQUESTED в той же транзакции.

Архитектура:
- Внешняя Celery-таска import_bundle — синхронная (def), её вызывает Celery.
- Внутри таски один раз происходит переход sync -> async через run_async.
- Всё взаимодействие с БД и MinIO реализовано в _import_bundle_async() и _async_import()
  под управлением db_uow().
- Import Worker НЕ вызывает Celery-задачи напрямую для discovery/analysis.
- Для надёжной интеграции с брокером используется transactional outbox pattern:
  в рамках той же транзакции пишется outbox event, а отдельный dispatcher/relay
  публикует его в Celery уже после коммита.

Audit trail:
- На успешном завершении бандла пишет IMPORT.
- На quarantine при валидации пишет IMPORT_FILE_QUARANTINED.
- На unsupported filetype пишет IMPORT_FILE_UNSUPPORTED.
- Audit logging best-effort: проблемы аудита не должны ломать импорт.

Важно:
- Этот файл предполагает наличие:
  - services.outbox_service.OutboxService
  - outbox event type / contract для workers.start_language_discovery
- Это сознательный production design: импорт и публикация задач
  развязаны через durable DB-backed outbox.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import uuid
import zipfile
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.constants import DocumentStatus
from core.exceptions import IdempotencyConflictError, PermanentError
from core.logging import get_logger
from db.models.bundle import Bundle
from db.repositories import (
    AuditRepository,
    DocumentRepository,
    DocumentVersionRepository,
    IdempotencyRepository,
)
from db.uow import db_uow
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from ops.metrics import get_metrics
from services.extract_router import (
    ExtractRoutingDecision,
    decide_extraction_strategy,
)
from services.file_validator import (
    FileStatus,
    validate_file,
)
from services.outbox_service import OutboxService
from storage.artifact_store import ArtifactPath, ArtifactStore

logger = get_logger(__name__)


def compute_sha256(filepath: str) -> str:
    """Посчитать SHA-256 хэш файла для дедупликации."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.import_bundle",
    track_job=False,
    queue="default",
)
def import_bundle(
    self,
    deal_id: str,
    tenant_id: str,
    source_path: str,
    idempotency_key: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """
    Синхронная точка входа Celery-таски импорта.

    Важно:
    - Эта таска НЕ шлёт downstream-задачи напрямую.
    - Она только выполняет import и пишет outbox events.
    - Публикация в Celery выполняется отдельно relay/dispatcher процессом.
    """
    _ = self

    async def _wrapper() -> dict[str, Any]:
        async with db_uow() as uow:
            return await _import_bundle_async(
                deal_id=deal_id,
                tenant_id=tenant_id,
                source_path=source_path,
                idempotency_key=idempotency_key,
                run_id=run_id,
                db=uow.session,
            )

    result = run_async(_wrapper())

    logger.info(
        "Import bundle task finished",
        extra={
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "source_path": source_path,
            "imported_count": result.get("imported_count"),
            "quarantine_count": result.get("quarantine_count"),
            "duplicate_count": result.get("duplicate_count"),
            "skipped_count": result.get("skipped_count"),
            "bundle_id": result.get("bundle_id"),
        },
    )

    return result


async def _import_bundle_async(
    deal_id: str,
    tenant_id: str,
    source_path: str,
    db: AsyncSession,
    idempotency_key: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    logger.info(
        "Starting import",
        extra={
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "source_path": source_path,
            "idempotency_key": idempotency_key,
            "run_id": run_id,
        },
    )

    metrics = get_metrics()

    if idempotency_key:
        cached = await _check_idempotency(
            tenant_id=tenant_id,
            key=idempotency_key,
            db=db,
        )
        if cached is not None:
            logger.info(
                "Idempotent replay — returning cached result",
                extra={"idempotency_key": idempotency_key},
            )
            return cached

    if not os.path.exists(source_path):
        metrics.import_fail.labels(reason="source_not_found").inc()
        raise PermanentError(
            f"Source file not found: {source_path}",
            details={"source_path": source_path},
        )

    if zipfile.is_zipfile(source_path):
        with tempfile.TemporaryDirectory(prefix="mas_import_") as tmp_dir:
            file_list = _extract_zip_safe(source_path, tmp_dir)
            result = await _async_import(
                deal_id=deal_id,
                tenant_id=tenant_id,
                file_list=file_list,
                db=db,
                run_id=run_id,
                idempotency_key=idempotency_key,
            )
    else:
        result = await _async_import(
            deal_id=deal_id,
            tenant_id=tenant_id,
            file_list=[("", source_path)],
            db=db,
            run_id=run_id,
            idempotency_key=idempotency_key,
        )

    logger.info(
        "Import completed",
        extra={
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "imported": result["imported_count"],
            "quarantined": result["quarantine_count"],
            "duplicates": result["duplicate_count"],
            "skipped": result["skipped_count"],
            "committed": result.get("committed"),
        },
    )
    return result


def _extract_zip_safe(zip_path: str, tmp_dir: str) -> list[tuple[str, str]]:
    """
    Безопасно распаковать ZIP и вернуть список (folder_path, filepath).

    Защита:
    - запрещаем absolute paths;
    - запрещаем '..' traversal;
    - игнорируем directory entries;
    - нормализуем POSIX path внутри ZIP;
    - не используем extractall().
    """
    metrics = get_metrics()
    file_list: list[tuple[str, str]] = []

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.infolist():
                if member.is_dir():
                    continue

                archive_name = member.filename
                safe_rel_path = _validate_zip_member_path(archive_name)
                destination = Path(tmp_dir) / safe_rel_path

                destination.parent.mkdir(parents=True, exist_ok=True)

                with zf.open(member, "r") as src, open(destination, "wb") as dst:
                    shutil.copyfileobj(src, dst)

                folder_path = str(safe_rel_path.parent).replace("\\", "/")
                if folder_path == ".":
                    folder_path = ""

                file_list.append((folder_path, str(destination)))
    except zipfile.BadZipFile:
        metrics.import_fail.labels(reason="bad_zip").inc()
        raise PermanentError(
            "Invalid or corrupted ZIP file",
            details={"source_path": zip_path},
        )

    logger.info(
        "ZIP extracted safely",
        extra={"total_files": len(file_list), "tmp_dir": tmp_dir},
    )
    return file_list


def _validate_zip_member_path(member_name: str) -> Path:
    """
    Провалидировать путь файла внутри ZIP и вернуть безопасный относительный Path.

    Запрещаем:
    - пустые имена;
    - абсолютные пути;
    - traversal через '..';
    - Windows drive paths;
    - нормализованные пути, уходящие вверх.
    """
    normalized = member_name.replace("\\", "/").strip()

    if not normalized:
        raise PermanentError(
            "Invalid ZIP entry: empty path",
            details={"zip_member": member_name},
        )

    pure_path = PurePosixPath(normalized)

    if pure_path.is_absolute():
        raise PermanentError(
            "Invalid ZIP entry: absolute paths are not allowed",
            details={"zip_member": member_name},
        )

    if pure_path.parts and ":" in pure_path.parts[0]:
        raise PermanentError(
            "Invalid ZIP entry: drive paths are not allowed",
            details={"zip_member": member_name},
        )

    if any(part in ("..", "") for part in pure_path.parts):
        raise PermanentError(
            "Invalid ZIP entry: path traversal detected",
            details={"zip_member": member_name},
        )

    safe_path = Path(*pure_path.parts)

    if str(safe_path).startswith(".."):
        raise PermanentError(
            "Invalid ZIP entry: unsafe normalized path",
            details={"zip_member": member_name},
        )

    return safe_path


async def _check_idempotency(
    tenant_id: str,
    key: str,
    db: AsyncSession,
) -> dict[str, Any] | None:
    """
    Проверка идемпотентности.
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
        return record.result
    if record.status == "processing":
        raise IdempotencyConflictError(
            f"Import with key '{key}' is already in progress"
        )
    if record.status == "failed":
        return None
    return None


async def _async_import(
    deal_id: str,
    tenant_id: str,
    file_list: list[tuple[str, str]],
    db: AsyncSession,
    run_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """
    Основная логика импорта.

    Важно:
    - Здесь нельзя отправлять сообщения напрямую в брокер.
    - Все побочные действия для асинхронной обработки фиксируются через outbox
      в той же транзакции, что и import.
    """
    metrics = get_metrics()

    store = ArtifactStore(settings)
    imported_ids: list[str] = []
    quarantine_ids: list[str] = []
    duplicate_count = 0
    skipped_count = 0
    language_discovery_requested = False

    doc_repo = DocumentRepository(db)
    ver_repo = DocumentVersionRepository(db)
    audit_repo = AuditRepository(db)
    outbox = OutboxService(db)

    deal_uuid = uuid.UUID(deal_id)
    tenant_uuid = uuid.UUID(tenant_id)
    run_uuid = uuid.UUID(run_id) if run_id else None

    bundle = Bundle(
        deal_id=deal_uuid,
        source_type="zip" if len(file_list) > 1 else "local",
        status="processing",
        idempotency_key=idempotency_key,
        file_count=0,
    )
    db.add(bundle)
    await db.flush()

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

    bundle.file_count = len(imported_ids) + len(quarantine_ids)
    bundle.status = "completed"
    bundle.completed_at = datetime.now(UTC)
    await db.flush()

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

    result = {
        "bundle_id": str(bundle.id),
        "document_ids": imported_ids,
        "quarantined_ids": quarantine_ids,
        "imported_count": len(imported_ids),
        "quarantine_count": len(quarantine_ids),
        "duplicate_count": duplicate_count,
        "skipped_count": skipped_count,
        "committed": True,
        "language_discovery_requested": language_discovery_requested,
    }

    if idempotency_key:
        idem_repo = IdempotencyRepository(db)
        record, _ = await idem_repo.get_or_create(
            tenant_uuid,
            "import",
            idempotency_key,
        )
        response_hash = hashlib.sha256(str(result).encode()).hexdigest()
        await idem_repo.mark_completed(
            record.id,
            response_hash=response_hash,
            result=result,
        )

    return result


def _build_language_discovery_outbox_dedup_key(
    *,
    deal_id: str,
    bundle_id: str,
    document_ids: list[str],
) -> str:
    """
    Построить стабильный dedup key для outbox-события запуска language discovery.

    Смысл:
    - один import bundle -> одна durable команда на discovery для этого набора документов;
    - relay может использовать dedup_key для защиты от повторной публикации.
    """
    normalized_doc_ids = sorted(set(document_ids))
    payload = f"{deal_id}:{bundle_id}:{','.join(normalized_doc_ids)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _get_content_type(filetype: str) -> str:
    """Преобразовать тип файла во вполне разумный MIME-тип."""
    content_types = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls": "application/vnd.ms-excel",
        "image": "image/png",
    }
    return content_types.get(filetype, "application/octet-stream")




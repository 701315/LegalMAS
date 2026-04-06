# src/workers/import_worker.py

"""
Import Worker — production.

Назначение:
- Первичный импорт файлов в систему.
- Работает как первый этап пайплайна: import → …, но
  НЕ запускает последующие стадии напрямую — только создаёт документы и версии.

Основные функции:
  - Распаковка ZIP с сохранением структуры папок (folder_path).
  - Валидация файлов (расширение, размер, сигнатура / magic bytes).
  - Дедупликация по SHA‑256 внутри одной сделки.
  - Идемпотентность через IdempotencyKey.
  - Карантин для некорректных / повреждённых / неподдерживаемых файлов.
  - Загрузка оригиналов в MinIO и создание Document + DocumentVersion.
  - Определение исходного формата файла (source_extension, source_filetype).
  - Подготовка документов к дальнейшему пайплайну без прямого запуска downstream‑воркеров.
  - Загрузка оригиналов в MinIO и создание Document + DocumentVersion.
  - Определение исходного формата файла (source_extension, source_filetype).
  - (Больше не ставит downstream‑таски — дальнейшая обработка решается оркестратором.)

Архитектура:
- Внешняя Celery‑таска import_bundle — синхронная (def), её вызывает Celery.
- Внутри таски один раз происходит переход sync → async через run_async.
- Всё взаимодействие с БД и MinIO реализовано в _import_bundle_async() и _async_import()
  под управлением db_uow().
- Import Worker не запускает последующие воркеры (build_primary_language_source, extract и т.д.).
  Дальнейшие стадии запускаются через централизованный оркестратор по статусу документа.
"""

import hashlib
import os
import tempfile
import uuid
import zipfile
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ops.metrics import get_metrics
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
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from mas_queue.async_helpers import run_async
from services.file_validator import (
    FileStatus,
    validate_file,
)
from services.extract_router import (
    ExtractRoutingDecision,
    decide_extraction_strategy,
)
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
) -> dict:
    """
    Синхронная точка входа Celery‑таски импорта.
    """

    async def _wrapper() -> dict:
        # db_uow() создаёт AsyncSession и управляет транзакцией.
        async with db_uow() as uow:
            return await _import_bundle_async(
                deal_id=deal_id,
                tenant_id=tenant_id,
                source_path=source_path,
                idempotency_key=idempotency_key,
                run_id=run_id,
                db=uow.session,
            )

    # Запускаем асинхронную часть через общий мост run_async
    result = run_async(_wrapper())

    return result


async def _import_bundle_async(
    deal_id: str,
    tenant_id: str,
    source_path: str,
    db: AsyncSession,
    idempotency_key: str | None = None,
    run_id: str | None = None,
) -> dict:
    logger.info(
        "Starting import",
        deal_id=deal_id,
        source_path=source_path,
        idempotency_key=idempotency_key,
    )

    metrics = get_metrics()

    # Idempotency check
    if idempotency_key:
        cached = await _check_idempotency(
            tenant_id=tenant_id,
            key=idempotency_key,
            db=db,
        )
        if cached is not None:
            logger.info(
                "Idempotent replay — returning cached result",
                idempotency_key=idempotency_key,
            )
            return cached

    if not os.path.exists(source_path):
        metrics.import_fail.labels(reason="source_not_found").inc()
        raise PermanentError(
            f"Source file not found: {source_path}",
            details={"source_path": source_path},
        )

    # Распаковываем ZIP или работаем с одиночным файлом
    if zipfile.is_zipfile(source_path):
        file_list = _extract_zip(source_path)
    else:
        folder = ""
        file_list = [(folder, source_path)]

    result = await _async_import(
        deal_id=deal_id,
        tenant_id=tenant_id,
        file_list=file_list,
        db=db,
        run_id=run_id,
        idempotency_key=idempotency_key,
    )

    logger.info(
        "Import completed",
        deal_id=deal_id,
        imported=result["imported_count"],
        quarantined=result["quarantine_count"],
        duplicates=result["duplicate_count"],
        skipped=result["skipped_count"],
    )
    return result


def _extract_zip(zip_path: str) -> list[tuple[str, str]]:
    """
    Распаковать ZIP и вернуть список (folder_path, filepath).
    """
    metrics = get_metrics()

    tmp_dir = tempfile.mkdtemp(prefix="mas_import_")
    file_list: list[tuple[str, str]] = []
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp_dir)
    except zipfile.BadZipFile:
        metrics.import_fail.labels(reason="bad_zip").inc()
        raise PermanentError(
            "Invalid or corrupted ZIP file",
            details={"source_path": zip_path},
        )

    for root, dirs, files in os.walk(tmp_dir):
        for fname in files:
            full_path = os.path.join(root, fname)
            rel_dir = os.path.relpath(root, tmp_dir)
            folder_path = rel_dir if rel_dir != "." else ""
            file_list.append((folder_path, full_path))

    logger.info("ZIP extracted", total_files=len(file_list), tmp_dir=tmp_dir)
    return file_list


async def _check_idempotency(
    tenant_id: str,
    key: str,
    db: AsyncSession,
) -> dict | None:
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
        raise IdempotencyConflictError(f"Import with key '{key}' is already in progress")
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
) -> dict:
    """
    Основная логика импорта.
    """
    metrics = get_metrics()

    store = ArtifactStore()
    imported_ids: list[str] = []
    quarantine_ids: list[str] = []
    duplicate_count = 0
    skipped_count = 0

    doc_repo = DocumentRepository(db)
    ver_repo = DocumentVersionRepository(db)

    # Создаём Bundle
    bundle = Bundle(
        deal_id=uuid.UUID(deal_id),
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

        # 1. Skip
        if validation.status == FileStatus.SKIP:
            skipped_count += 1
            logger.debug(
                "File skipped",
                filename=filename,
                reason=validation.reason,
            )
            continue

        # 2. Quarantine invalid
        if validation.status == FileStatus.QUARANTINE:
            q_doc = await doc_repo.create(
                deal_id=uuid.UUID(deal_id),
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
            # Бест‑эффорт: загружаем оригинал для ручного разбора
            try:
                with open(filepath, "rb") as f:
                    file_bytes = f.read()
                artifact_path = ArtifactPath.original(tenant_id, deal_id, str(q_doc.id))
                store.put_file(
                    artifact_path + (validation.original_extension or ".bin"),
                    file_bytes,
                )
            except Exception:
                pass

            quarantine_ids.append(str(q_doc.id))
            logger.warning(
                "File quarantined",
                filename=filename,
                reason=validation.reason,
                doc_id=str(q_doc.id),
            )

            metrics.quarantine.labels(
                reason=validation.reason or "import_quarantine"
            ).inc()
            continue

        # 3. SHA-256 deduplication
        sha256 = compute_sha256(filepath)
        existing = await doc_repo.get_by_sha256(uuid.UUID(deal_id), sha256)
        if existing:
            duplicate_count += 1
            logger.info(
                "Duplicate file detected",
                filename=filename,
                sha256=sha256[:16],
                existing_doc=str(existing.id),
            )
            continue

        # 4. Читаем файл
        try:
            with open(filepath, "rb") as f:
                file_bytes = f.read()
        except Exception as e:
            metrics.import_fail.labels(reason="read_error").inc()
            logger.error(
                "Failed to read file during import",
                filename=filename,
                error=str(e),
            )
            continue

        # 5. Создаём Document
        source_ext = validation.original_extension  # например, ".pdf", ".docx"
        doc = await doc_repo.create(
            deal_id=uuid.UUID(deal_id),
            bundle_id=bundle.id,
            filename=filename,
            folder_path=folder_path or None,
            sha256_file=sha256,
            status=DocumentStatus.PENDING.value,
            source_extension=source_ext,
            source_filetype=validation.filetype,
        )

        # Определяем расширение для сохранения в MinIO
        ext = source_ext or ".pdf"

        artifact_path = ArtifactPath.original(tenant_id, deal_id, str(doc.id))
        original_ref = store.put_file(
            artifact_path + ext,
            file_bytes,
            content_type=_get_content_type(validation.filetype),
        )

        # 6. DocumentVersion
        doc_version = await ver_repo.create(
            document_id=doc.id,
            version_num=1,
            original_ref=original_ref,
            origin_filetype=validation.filetype,
            origin_extension=source_ext,
        )
        imported_ids.append(str(doc.id))
        logger.info(
            "Document imported",
            doc_id=str(doc.id),
            filename=filename,
            folder_path=folder_path,
            filetype=validation.filetype,
            sha256=sha256[:16],
        )

        # 7. Решаем, что делать дальше по типу файла через централизованный роутер
        decision: ExtractRoutingDecision = decide_extraction_strategy(validation.filetype)

        if decision.action in ("extract", "convert_then_extract") and decision.extractor_task:
            # На этом этапе мы ничего не ставим в очередь.
            # Документ остаётся в статусе PENDING — оркестратор позже решит, что запускать,
            # исходя из source_filetype, origin_filetype и т.п.
            logger.info(
                "Document ready for analysis pipeline",
                doc_id=str(doc.id),
                filetype=validation.filetype,
                decision_action=decision.action,
                reason=decision.reason,
            )
        else:
            # unsupported: честно отправляем в карантин с понятной причиной
            await doc_repo.set_quarantined(
                doc.id,
                stage="import",
                message=(
                    "Тип файла не поддерживается пайплайном анализа: "
                    f"{validation.filetype or 'unknown'}"
                ),
                reason=decision.reason or "unsupported_filetype",
                run_id=uuid.UUID(run_id) if run_id else None,
            )
            quarantine_ids.append(str(doc.id))
            imported_ids.remove(str(doc.id))
            logger.info(
                "File type not supported by analysis pipeline — quarantined",
                filename=filename,
                filetype=validation.filetype,
                reason=decision.reason,
            )

            metrics.quarantine.labels(
                reason=decision.reason or "unsupported_filetype"
            ).inc()
            continue

    # Финализируем bundle
    bundle.file_count = len(imported_ids) + len(quarantine_ids)
    bundle.status = "completed"
    bundle.completed_at = datetime.now(UTC)
    await db.flush()

    # Аудит‑лог
    audit_repo = AuditRepository(db)
    await audit_repo.log(
        tenant_id=uuid.UUID(tenant_id),
        deal_id=uuid.UUID(deal_id),
        action="IMPORT",
        actor="system",
        actor_role="system",
        details={
            "bundle_id": str(bundle.id),
            "total_files": len(file_list),
            "imported_count": len(imported_ids),
            "quarantine_count": len(quarantine_ids),
            "duplicate_count": duplicate_count,
            "skipped_count": skipped_count,
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
    }

    # Идемпотентность: помечаем ключ как завершённый
    if idempotency_key:
        idem_repo = IdempotencyRepository(db)
        record, _ = await idem_repo.get_or_create(
            uuid.UUID(tenant_id),
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


def _get_content_type(filetype: str) -> str:
    """Преобразовать тип файла во вполне разумный MIME‑тип."""
    content_types = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls": "application/vnd.ms-excel",
        "image": "image/png",
    }
    return content_types.get(filetype, "application/octet-stream")


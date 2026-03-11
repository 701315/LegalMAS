# src/workers/import_worker.py


"""
Import Worker — production.

Загружает документы из ZIP-архива или одиночного файла в пайплайн.

Функции:
  - Распаковка ZIP с сохранением структуры папок
  - Валидация файлов: расширение, размер, сигнатура (magic bytes)
  - Дедупликация по SHA-256 внутри сделки
  - Идемпотентность через IdempotencyKey
  - Карантин для некорректных/повреждённых файлов
  - Аудит-логирование
  - Постановка задач extract_document для валидных PDF

Важно про folder_path:
  - Document.folder_path заполняется из структуры папок в ZIP, например:
      "02. Contracts/SPA/spa_main.pdf" → folder_path = "02. Contracts/SPA"
  - Это поле дальше использует L1 Rule-Based Classifier (Stage 6)
    через folder_patterns в playbooks/document_types/registry.yaml.
  - Import Worker НЕ делает классификацию, он только честно сохраняет folder_path.
"""

import asyncio
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
from services.file_validator import (
    FileStatus,
    can_process_directly,
    is_image,
    is_spreadsheet,
    needs_conversion,
    validate_file,
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

    Паттерн:
    - Внешняя функция синхронная (def), чтобы Celery мог сериализовать результат.
    - Внутри создаём event loop и запускаем асинхронное ядро под db_uow().
    """
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)

        async def _wrapper() -> dict:
            async with db_uow() as uow:
                return await _import_bundle_async(
                    deal_id=deal_id,
                    tenant_id=tenant_id,
                    source_path=source_path,
                    idempotency_key=idempotency_key,
                    run_id=run_id,
                    db=uow.session,
                )

        return loop.run_until_complete(_wrapper())
    finally:
        asyncio.set_event_loop(None)
        loop.close()


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

    Сохраняет структуру папок Data Room.
    Пример:
      путь внутри ZIP: "02. Contracts/SPA/spa_main.pdf"
      → folder_path = "02. Contracts/SPA"
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

    Возвращает:
    - кэшированный результат, если импорт уже завершён;
    - None, если это новый запуск;
    - выбрасывает IdempotencyConflictError, если импорт ещё идёт.
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
        # позволяем повторить
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
    Основная логика импорта. Для каждого файла:

      1. Валидация (расширение, размер, сигнатура).
      2. Пропуск скрытых/системных файлов.
      3. Карантин невалидных файлов.
      4. Дедупликация по SHA-256 внутри сделки.
      5. Загрузка оригинала в MinIO.
      6. Создание Document + DocumentVersion.
      7. Постановка extract_document (PDF) или карантин для других типов.

    folder_path сохраняется как есть и потом используется L1‑классификатором.
    """
    metrics = get_metrics()

    store = ArtifactStore()
    imported_ids: list[str] = []
    quarantine_ids: list[str] = []
    duplicate_count = 0
    skipped_count = 0
    tasks_to_dispatch: list[dict] = []

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
            await ver_repo.create(document_id=q_doc.id, version_num=1)
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
        doc = await doc_repo.create(
            deal_id=uuid.UUID(deal_id),
            bundle_id=bundle.id,
            filename=filename,
            folder_path=folder_path or None,
            sha256_file=sha256,
            status=DocumentStatus.PENDING.value,
        )
        ext = validation.original_extension or ".pdf"
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

        # 7. Решаем, что делать дальше по типу файла
        if can_process_directly(validation.filetype):
            # PDF → Extractor (Stage 4)
            tasks_to_dispatch.append(
                {
                    "document_version_id": str(doc_version.id),
                    "document_id": str(doc.id),
                    "deal_id": deal_id,
                    "tenant_id": tenant_id,
                    "run_id": run_id,
                }
            )
        elif needs_conversion(validation.filetype):
            # DOCX/DOC → пока в карантин
            await doc_repo.update_status(
                doc.id,
                DocumentStatus.QUARANTINE.value,
            )
            quarantine_ids.append(str(doc.id))
            imported_ids.remove(str(doc.id))
            logger.info(
                "File needs conversion — quarantined for now",
                filename=filename,
                filetype=validation.filetype,
            )
        elif is_spreadsheet(validation.filetype):
            # XLSX/XLS → сохраняем, обработка будет позже
            await doc_repo.update_status(
                doc.id,
                DocumentStatus.QUARANTINE.value,
            )
            quarantine_ids.append(str(doc.id))
            imported_ids.remove(str(doc.id))
            logger.info(
                "Spreadsheet stored — processing not yet supported",
                filename=filename,
            )
        elif is_image(validation.filetype):
            # Изображения → будущее OCR
            await doc_repo.update_status(
                doc.id,
                DocumentStatus.QUARANTINE.value,
            )
            quarantine_ids.append(str(doc.id))
            imported_ids.remove(str(doc.id))
            logger.info(
                "Image stored — OCR processing in future stages",
                filename=filename,
            )

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

    # Транзакция закоммичена — можно публиковать downstream‑таски
    for kw in tasks_to_dispatch:
        celery_app.send_task(
            "workers.extract_document",
            kwargs=kw,
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

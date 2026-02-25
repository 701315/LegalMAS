"""
Import Worker — production.

Loads documents from a ZIP archive or a single file into the pipeline.

Features:
  - ZIP extraction with folder hierarchy preservation
  - File validation: extension, size, magic bytes
  - SHA256 deduplication within deal
  - Idempotency via IdempotencyKey
  - Quarantine for invalid/corrupted files
  - Audit logging
  - Triggers extract_document for each valid PDF

Folder path routing note:
  Document.folder_path is populated from the ZIP folder structure, e.g.:
    "02. Contracts/SPA/spa_main.pdf" → folder_path = "02. Contracts/SPA"
  This value is used downstream by the L1 Rule-Based Classifier (Stage 6)
  via folder_patterns in playbooks/document_types/registry.yaml.
  Example registry entry:
    folder_patterns:
      - r'(?i)SPA'
      - r'(?i)основной.{0,10}договор'
  A match boosts the classification score for type contract1.1spa.
  Import Worker's only responsibility here is to PRESERVE the folder_path
  faithfully — no classification happens at this stage.
"""

import hashlib
import os
import tempfile
import uuid
import zipfile
from datetime import UTC, datetime, timedelta

from src.core.constants import DocumentStatus
from src.core.exceptions import IdempotencyConflictError, PermanentError
from src.core.logging import get_logger
from src.db.models.bundle import Bundle
from src.db.repositories import (
    AuditRepository,
    DocumentRepository,
    DocumentVersionRepository,
    IdempotencyRepository,
)
from src.db.session import get_session
from src.queue.base_task import MASBaseTask
from src.queue.celery_app import celery_app
from src.services.file_validator import (
    FileStatus,
    can_process_directly,
    is_image,
    is_spreadsheet,
    needs_conversion,
    validate_file,
)
from src.storage.artifact_store import ArtifactPath, ArtifactStore
from src.workers.extract_worker import extract_document

logger = get_logger(__name__)


def compute_sha256(filepath: str) -> str:
    """Compute SHA-256 hash of a file for deduplication."""
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
async def import_bundle(
    self,
    deal_id: str,
    tenant_id: str,
    source_path: str,
    idempotency_key: str = None,
    run_id: str = None,
) -> dict:
    return await _import_bundle_async(
        deal_id=deal_id,
        tenant_id=tenant_id,
        source_path=source_path,
        idempotency_key=idempotency_key,
        run_id=run_id,
    )


async def _import_bundle_async(
    deal_id: str,
    tenant_id: str,
    source_path: str,
    idempotency_key: str | None = None,
    run_id: str | None = None,
) -> dict:
    logger.info(
        "Starting import",
        deal_id=deal_id,
        source_path=source_path,
        idempotency_key=idempotency_key,
    )

    # Idempotency check
    if idempotency_key:
        cached = await _check_idempotency(
            tenant_id=tenant_id,
            key=idempotency_key,
        )
        if cached is not None:
            logger.info(
                "Idempotent replay — returning cached result",
                idempotency_key=idempotency_key,
            )
            return cached

    if not os.path.exists(source_path):
        raise PermanentError(
            f"Source file not found: {source_path}",
            details={"source_path": source_path},
        )

    # Extract files from ZIP or treat as single file
    if zipfile.is_zipfile(source_path):
        file_list = _extract_zip(source_path)
    else:
        folder = ""
        file_list = [(folder, source_path)]

    result = await _async_import(
        deal_id=deal_id,
        tenant_id=tenant_id,
        file_list=file_list,
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


def _extract_zip(zip_path: str) -> list:
    """
    Extract ZIP and return list of (folder_path, filepath) tuples.

    Preserves Data Room folder hierarchy.
    folder_path is the relative directory path inside the ZIP, e.g.:
      "02. Contracts/SPA" for a file at "02. Contracts/SPA/spa_main.pdf"

    This folder_path is stored on Document and used by the L1 Classifier
    (Stage 6) for folder_patterns routing in registry.yaml.
    """
    tmp_dir = tempfile.mkdtemp(prefix="mas_import_")
    file_list = []
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp_dir)
    except zipfile.BadZipFile:
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


async def _check_idempotency(tenant_id: str, key: str) -> dict | None:
    """
    Check idempotency key.
    Returns cached result if already completed, None if new.
    Raises IdempotencyConflictError if currently being processed.
    """
    from src.db.repositories import IdempotencyRepository

    expires_at = datetime.now(UTC) + timedelta(days=7)

    async with get_session() as session:
        repo = IdempotencyRepository(session)
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
            # Allow retry
            return None
    return None


async def _async_import(
    deal_id: str,
    tenant_id: str,
    file_list: list,
    run_id: str = None,
    idempotency_key: str = None,
) -> dict:
    """
    Main import logic. For each file:
      1. Validate (extension, size, magic bytes)
      2. Skip hidden/system files
      3. Quarantine invalid files
      4. Check for duplicates (SHA-256 within deal)
      5. Upload original to MinIO
      6. Create Document + DocumentVersion
      7. Queue extraction (PDF → Extractor, Stage 4)
         or quarantine (DOCX/DOC/XLSX/image — conversion deferred)

    folder_path is preserved faithfully for downstream use by
    L1 Classifier (Stage 6) folder_patterns in registry.yaml.
    """

    store = ArtifactStore()
    imported_ids = []
    quarantine_ids = []
    duplicate_count = 0
    skipped_count = 0
    tasks_to_dispatch = []

    async with get_session() as session:
        doc_repo = DocumentRepository(session)
        ver_repo = DocumentVersionRepository(session)

        # Create Bundle
        bundle = Bundle(
            deal_id=uuid.UUID(deal_id),
            source_type="zip" if len(file_list) > 1 else "local",
            status="processing",
            idempotency_key=idempotency_key,
            file_count=0,
        )
        session.add(bundle)
        await session.flush()

        for folder_path, filepath in file_list:
            filename = os.path.basename(filepath)
            validation = validate_file(filepath)

            # Step 1: Skip
            if validation.status == FileStatus.SKIP:
                skipped_count += 1
                logger.debug("File skipped", filename=filename, reason=validation.reason)
                continue

            # Step 2: Quarantine invalid files
            if validation.status == FileStatus.QUARANTINE:
                q_doc = await doc_repo.create(
                    deal_id=uuid.UUID(deal_id),
                    bundle_id=bundle.id,
                    filename=filename,
                    folder_path=folder_path or None,
                    status=DocumentStatus.QUARANTINE.value,
                )
                await ver_repo.create(document_id=q_doc.id, version_num=1)
                # Best-effort upload for manual review
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
                continue

            # Step 3: SHA-256 deduplication within deal
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

            # Step 4: Upload original to MinIO
            with open(filepath, "rb") as f:
                file_bytes = f.read()

            doc = await doc_repo.create(
                deal_id=uuid.UUID(deal_id),
                bundle_id=bundle.id,
                filename=filename,
                folder_path=folder_path or None,  # ← preserved for L1 Classifier
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

            # Step 5: Create DocumentVersion
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
                folder_path=folder_path,  # logged for traceability → L1 routing
                filetype=validation.filetype,
                sha256=sha256[:16],
            )

            # Step 6: Queue next step based on file type
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
                # DOCX/DOC → quarantine with needs_conversion reason
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
                # XLSX/XLS → stored, processing deferred
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
                # Image → OCR pipeline in future stages
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

        # Finalize bundle
        bundle.file_count = len(imported_ids) + len(quarantine_ids)
        bundle.status = "completed"
        bundle.completed_at = datetime.now(UTC)
        await session.flush()

        # Audit log
        audit_repo = AuditRepository(session)
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

        # Mark idempotency key as completed
        if idempotency_key:
            idem_repo = IdempotencyRepository(session)
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

    # Транзакция закоммичена — теперь безопасно публиковать задачи
    for kw in tasks_to_dispatch:
        extract_document.delay(**kw)

    return result


def _get_content_type(filetype: str) -> str:
    """Map file type to MIME content type."""
    content_types = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls": "application/vnd.ms-excel",
        "image": "image/png",
    }
    return content_types.get(filetype, "application/octet-stream")

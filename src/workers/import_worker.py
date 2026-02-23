"""
Import Worker — loads documents from ZIP or local files into the system.

Simplified version for vertical slice:
- Supports single PDF files and ZIP archives
- Creates Document + DocumentVersion records
- Uploads originals to MinIO
- Triggers extract_document for each file
"""

import hashlib
import os
import tempfile
import uuid
import zipfile

from src.core.constants import DocumentStatus
from src.core.exceptions import PermanentError
from src.core.logging import get_logger
from src.queue.async_helpers import get_worker_session, run_async
from src.queue.base_task import MASBaseTask
from src.queue.celery_app import celery_app
from src.storage.artifact_store import ArtifactPath, ArtifactStore

logger = get_logger(__name__)


def _compute_sha256(file_path: str) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
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
    run_id: str | None = None,
) -> dict:
    """Import documents from a file or ZIP archive."""
    logger.info("Starting import", deal_id=deal_id, source_path=source_path)

    if not os.path.exists(source_path):
        raise PermanentError(
            f"Source file not found: {source_path}",
            details={"source_path": source_path},
        )

    if zipfile.is_zipfile(source_path):
        file_list = _extract_zip(source_path)
    else:
        file_list = [("", source_path)]

    result = run_async(
        _async_import(
            deal_id=deal_id,
            tenant_id=tenant_id,
            file_list=file_list,
            run_id=run_id,
        )
    )

    from src.workers.extract_worker import extract_document

    for v in result.pop("versions_to_extract", []):
        extract_document.delay(**v)

    return result


def _extract_zip(zip_path: str) -> list[tuple[str, str]]:
    """Extract ZIP and return list of (folder_path, file_path) tuples."""
    tmp_dir = tempfile.mkdtemp(prefix="mas_import_")
    file_list = []

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(tmp_dir)
        for root, _dirs, files in os.walk(tmp_dir):
            for fname in files:
                if fname.lower().endswith(".pdf") and not fname.startswith("."):
                    full_path = os.path.join(root, fname)
                    rel_dir = os.path.relpath(root, tmp_dir)
                    folder = rel_dir if rel_dir != "." else ""
                    file_list.append((folder, full_path))

    return file_list


async def _async_import(
    deal_id: str,
    tenant_id: str,
    file_list: list[tuple[str, str]],
    run_id: str | None,
) -> dict:
    """Async import logic."""
    from src.db.models.bundle import Bundle
    from src.db.repositories import DocumentRepository, DocumentVersionRepository

    store = ArtifactStore()
    document_ids = []
    versions_to_extract = []

    async with get_worker_session() as session:
        doc_repo = DocumentRepository(session)
        ver_repo = DocumentVersionRepository(session)

        bundle = Bundle(
            deal_id=uuid.UUID(deal_id),
            source_type="local",
            status="completed",
            file_count=len(file_list),
        )
        session.add(bundle)
        await session.flush()

        for folder_path, file_path in file_list:
            filename = os.path.basename(file_path)
            sha256 = _compute_sha256(file_path)

            existing = await doc_repo.get_by_sha256(uuid.UUID(deal_id), sha256)
            if existing:
                logger.info("Duplicate file skipped", filename=filename, sha256=sha256)
                continue

            doc = await doc_repo.create(
                deal_id=uuid.UUID(deal_id),
                bundle_id=bundle.id,
                filename=filename,
                folder_path=folder_path or None,
                sha256_file=sha256,
                status=DocumentStatus.PENDING.value,
            )

            with open(file_path, "rb") as f:
                file_bytes = f.read()

            artifact_path = ArtifactPath.original(tenant_id, deal_id, str(doc.id))
            original_ref = store.put_file(
                artifact_path + ".pdf",
                file_bytes,
                content_type="application/pdf",
            )

            doc_version = await ver_repo.create(
                document_id=doc.id,
                version_num=1,
                original_ref=original_ref,
            )

            document_ids.append(str(doc.id))

            logger.info(
                "Document imported",
                doc_id=str(doc.id),
                filename=filename,
                version_id=str(doc_version.id),
            )

            # ДОБАВЬ ЭТО (внутри сессии, вместо delay):
            versions_to_extract.append(
                {
                    "document_version_id": str(doc_version.id),
                    "document_id": str(doc.id),
                    "deal_id": deal_id,
                    "tenant_id": tenant_id,
                    "run_id": run_id,
                }
            )

    return {
        "bundle_id": str(bundle.id),
        "document_ids": document_ids,
        "count": len(document_ids),
        "versions_to_extract": versions_to_extract,
    }

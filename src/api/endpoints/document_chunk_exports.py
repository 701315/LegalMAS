# src/api/endpoints/document_chunk_exports.py

"""
Endpoints for document chunk exporting.

Important: This endpoint does not modify anything in the database or the document itself.
It only:
- Retrieves already computed document chunks;
- Assembles them into a single markdown text;
- Persists it in the internal artifact storage (MinIO / S3);
- Returns a stable backend download URL.

The browser never accesses MinIO directly.
The file is delivered via a backend streaming endpoint.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from core.exceptions import PermanentError, TransientError
from core.logging import get_logger
from db.repositories.deal_repo import DealRepository
from db.repositories.document_repo import DocumentRepository
from db.session import get_db
from engine.content.chunk_exporter import ChunkExportService
from storage.artifact_store import ArtifactStore

logger = get_logger(__name__)

router = APIRouter(
    prefix="/documents",
    tags=["document-exports"],
)


@router.get(
    "/{document_id}/chunk-view",
    summary="Get download URL for chunk-view file",
    response_model=dict,
)
async def get_document_chunk_view(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Return a stable backend download URL for the chunk-view markdown file.

    The browser does not access MinIO directly.
    The file is delivered via the /chunk-view/download streaming endpoint.
    """
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(document_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            headers={"X-Error-Code": "DOCUMENT_NOT_FOUND"},
            detail="Document not found",
        )

    await require_project_role(
        db=db,
        user=user,
        deal_id=doc.deal_id,
        allowed_roles=("admin", "editor", "reviewer", "viewer"),
    )

    deal_repo = DealRepository(db)
    deal = await deal_repo.get_by_id(doc.deal_id, tenant_id=user.tenant_id)
    if deal is None:
        logger.error(
            "Deal not found for document when preparing chunk view",
            extra={
                "document_id": str(document_id),
                "deal_id": str(doc.deal_id),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            headers={"X-Error-Code": "DEAL_NOT_FOUND"},
            detail="Internal error: deal not found for this document.",
        )

    exporter = ChunkExportService(db)
    try:
        await exporter.export_sized_chunks_markdown(
            doc_id=document_id,
            deal_id=deal.id,
            tenant_id=deal.tenant_id,
        )
    except ValueError as e:
        logger.warning(
            "Chunk export failed with ValueError",
            extra={"document_id": str(document_id), "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            headers={"X-Error-Code": "CHUNK_VIEW_NOT_AVAILABLE"},
            detail="Chunk view is not available for this document yet",
        )
    except Exception as e:
        logger.exception(
            "Unexpected error during chunk export",
            extra={"document_id": str(document_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            headers={"X-Error-Code": "CHUNK_EXPORT_FAILED"},
            detail="Internal error while preparing chunk view for this document.",
        ) from e

    # Return a stable backend URL.
    # The browser does not know about MinIO and does not fetch from there directly.
    download_url = f"/api/v1/documents/{document_id}/chunk-view/download"
    return {"url": download_url}


@router.get(
    "/{document_id}/chunk-view/download",
    summary="Download chunk-view file via backend streaming",
)
async def download_document_chunk_view(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    """
    Download the chunk-view markdown file via backend streaming.

    MinIO remains private. Browser retrieves file from backend.
    """
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(document_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            headers={"X-Error-Code": "DOCUMENT_NOT_FOUND"},
            detail="Document not found",
        )

    await require_project_role(
        db=db,
        user=user,
        deal_id=doc.deal_id,
        allowed_roles=("admin", "editor", "reviewer", "viewer"),
    )

    deal_repo = DealRepository(db)
    deal = await deal_repo.get_by_id(doc.deal_id, tenant_id=user.tenant_id)
    if deal is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            headers={"X-Error-Code": "DEAL_NOT_FOUND"},
            detail="Internal error: deal not found.",
        )

    exporter = ChunkExportService(db)
    try:
        s3_uri = await exporter.export_sized_chunks_markdown(
            doc_id=document_id,
            deal_id=deal.id,
            tenant_id=deal.tenant_id,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            headers={"X-Error-Code": "CHUNK_VIEW_NOT_AVAILABLE"},
            detail="Chunk view is not available for this document yet",
        )
    except Exception as e:
        logger.exception(
            "Unexpected error during chunk export for streaming",
            extra={"document_id": str(document_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            headers={"X-Error-Code": "CHUNK_EXPORT_FAILED"},
            detail="Internal error while preparing chunk view.",
        ) from e

    store = ArtifactStore()
    try:
        metadata = store.get_file_metadata(s3_uri)
        storage_response = store.open_file_stream(s3_uri)
    except PermanentError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            headers={"X-Error-Code": "CHUNK_VIEW_FILE_NOT_FOUND"},
            detail="Chunk view file not found in storage",
        ) from e
    except TransientError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            headers={"X-Error-Code": "STORAGE_UNAVAILABLE"},
            detail="Storage temporarily unavailable",
        ) from e

    filename = f"{document_id}__chunks_view.md"
    size = metadata.get("size")
    headers: dict[str, str] = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    }
    if isinstance(size, int) and size >= 0:
        headers["Content-Length"] = str(size)

    CHUNK = 1024 * 1024

    def _iter(resp):
        try:
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                yield chunk
        finally:
            try:
                resp.close()
            finally:
                resp.release_conn()

    return StreamingResponse(
        _iter(storage_response),
        media_type="text/markdown; charset=utf-8",
        headers=headers,
    )

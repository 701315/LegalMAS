"""
Document structure and viewer endpoints.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from core.exceptions import PermanentError, TransientError
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.session import get_db
from engine.content.document_content_service import DocumentContentService
from storage.artifact_store import ArtifactStore

logger = logging.getLogger(__name__)


router = APIRouter()


class ViewerLayoutElement(BaseModel):
    element_id: str
    page: int
    bbox: list[float]


class ViewerLayoutResponse(BaseModel):
    document_id: str
    elements: list[ViewerLayoutElement]


class ViewerSizedChunkMeta(BaseModel):
    id: str
    element_ids: list[str]
    clause_uids: list[str] = Field(default_factory=list)
    raw_uids: list[str] = Field(default_factory=list)


class ViewerSizedChunksResponse(BaseModel):
    document_id: str
    chunks: list[ViewerSizedChunkMeta]


class DocumentLayoutsDebugResponse(BaseModel):
    document_id: str
    deal_id: str
    raw_layout_ref: str | None = None
    sanitized_layout_ref: str | None = None
    raw_layout: dict | None = None
    sanitized_layout: dict | None = None


@router.get(
    "/{doc_id}/layout-for-viewer",
    response_model=ViewerLayoutResponse,
    summary="Get compact layout (elements with bbox) for viewer overlay",
)
async def get_document_layout_for_viewer(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    await require_project_role(
        db=db,
        user=user,
        deal_id=doc.deal_id,
        allowed_roles=("viewer", "editor", "admin"),
    )

    ver_repo = DocumentVersionRepository(db)
    version = await ver_repo.get_latest(doc_id)
    if not version:
        raise HTTPException(status_code=404, detail="DocumentVersion not found")

    # ИЗМЕНЕНО: читаем layout по v2-контракту.
    # Приоритет:
    #   1) layout_primary_sanitized_ref — основной source of truth после PII-фильтрации;
    #   2) layout_primary_ref           — fallback, если PII ещё не выполнен.
    # Старые поля text_layout_sanitized_ref / text_layout_raw_ref — legacy,
    # у новых v2-документов они не заполняются.
    layout_ref = getattr(version, "layout_primary_sanitized_ref", None) or getattr(
        version, "layout_primary_ref", None
    )
    if not layout_ref:
        raise HTTPException(
            status_code=404,
            detail="Layout not available for this document",
        )

    store = ArtifactStore()
    try:
        layout_json = store.get_json(layout_ref)
    except PermanentError:
        raise HTTPException(status_code=404, detail="Layout artifact missing")
    except TransientError:
        raise HTTPException(
            status_code=503,
            detail="Storage temporarily unavailable",
        )
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Layout temporarily unavailable",
        )

    elements = layout_json.get("elements") or []
    viewer_elements: list[ViewerLayoutElement] = []

    for el in elements:
        element_id = el.get("element_id")
        page = el.get("page")
        bbox = el.get("bbox")

        if not element_id or not isinstance(page, int) or not bbox:
            continue

        try:
            x0, top, x1, bottom = bbox
            viewer_elements.append(
                ViewerLayoutElement(
                    element_id=str(element_id),
                    page=page,
                    bbox=[float(x0), float(top), float(x1), float(bottom)],
                )
            )
        except Exception:
            continue

    return ViewerLayoutResponse(
        document_id=str(doc_id),
        elements=viewer_elements,
    )


@router.get(
    "/{doc_id}/structured-data",
    summary="Get structured clause tree for document",
)
async def get_document_structured_data(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "DOCUMENT_NOT_FOUND",
                "message": "Document not found",
            },
        )

    await require_project_role(
        db=db,
        user=user,
        deal_id=doc.deal_id,
        allowed_roles=("viewer", "editor", "admin"),
    )

    ver_repo = DocumentVersionRepository(db)
    version = await ver_repo.get_latest(doc_id)

    if not version or not version.clause_tree_ref:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "STRUCTURED_NOT_READY",
                "message": "Structured data not available",
            },
        )

    store = ArtifactStore()
    try:
        payload = store.get_json(version.clause_tree_ref)
    except PermanentError:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "STRUCTURED_MISSING",
                "message": "Structured data not found",
            },
        )
    except TransientError:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "STORAGE_UNAVAILABLE",
                "message": "Storage temporarily unavailable",
            },
        )
    except Exception:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "STRUCTURED_UNKNOWN_ERROR",
                "message": "Structured data temporarily unavailable",
            },
        )

    return payload


@router.get(
    "/{doc_id}/sized-chunks",
    response_model=ViewerSizedChunksResponse,
    summary="Get sized chunks for viewer overlay (clause/subclause with element_ids)",
)
async def get_document_sized_chunks_for_viewer(
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    await require_project_role(
        db=db,
        user=user,
        deal_id=doc.deal_id,
        allowed_roles=("viewer", "editor", "admin"),
    )

    service = DocumentContentService(session=db)
    try:
        sized_chunks = await service.get_sized_chunks(doc_id=doc_id)
    except Exception as e:
        logger.exception(
            "Failed to build sized_chunks for viewer",
            extra={"doc_id": str(doc_id), "error": str(e)},
        )
        raise HTTPException(
            status_code=503,
            detail="Sized chunks temporarily unavailable",
        )

    viewer_chunks: list[ViewerSizedChunkMeta] = []
    for ch in sized_chunks:
        ch_id = ch.get("id")
        meta = ch.get("metadata") or {}
        element_ids = meta.get("element_ids") or []

        # canonical identity после Sprint 3 — effective_uid,
        # raw_uid — human-readable "7.3.2" для отображения в UI.
        # Поле clause_uid в canonical metadata не заполняется,
        # оставлено как fallback для legacy-чанков.
        effective_uid = meta.get("effective_uid") or meta.get("clause_uid")
        raw_uid = meta.get("raw_uid")

        clause_uids = [str(effective_uid)] if effective_uid else []
        raw_uids = [str(raw_uid)] if raw_uid else []

        if not ch_id:
            continue

        viewer_chunks.append(
            ViewerSizedChunkMeta(
                id=str(ch_id),
                element_ids=[str(eid) for eid in element_ids],
                clause_uids=clause_uids,
                raw_uids=raw_uids,
            )
        )

    return ViewerSizedChunksResponse(
        document_id=str(doc_id),
        chunks=viewer_chunks,
    )


@router.get(
    "/{doc_id}/debug/layouts",
    response_model=DocumentLayoutsDebugResponse,
    summary="Debug: raw vs sanitized layout for document",
)
async def get_document_layouts_debug(
    doc_id: UUID,
    include_raw: bool = Query(False, description="Вернуть ли полный raw layout JSON"),
    include_sanitized: bool = Query(
        False,
        description="Вернуть ли полный sanitized layout JSON",
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    await require_project_role(
        db=db,
        user=user,
        deal_id=doc.deal_id,
        allowed_roles=("viewer", "editor", "admin"),
    )

    ver_repo = DocumentVersionRepository(db)
    version = await ver_repo.get_latest(doc_id)
    if not version:
        raise HTTPException(status_code=404, detail="DocumentVersion not found")

    # ИЗМЕНЕНО: оба рефа теперь берём по v2-контракту.
    # raw_ref   — layout до PII-фильтрации (layout_primary_ref).
    # sanitized_ref — layout после PII-фильтрации (layout_primary_sanitized_ref).
    # Старые поля text_layout_raw_ref / text_layout_sanitized_ref — legacy,
    # у новых v2-документов они не заполняются и здесь не используются.
    raw_ref = getattr(version, "layout_primary_ref", None) or getattr(
        version, "text_layout_raw_ref", None
    )
    sanitized_ref = getattr(version, "layout_primary_sanitized_ref", None) or getattr(
        version, "text_layout_sanitized_ref", None
    )

    store = ArtifactStore()

    raw_layout: dict | None = None
    sanitized_layout: dict | None = None

    if include_raw and raw_ref:
        try:
            raw_layout = store.get_json(raw_ref)
        except Exception as e:
            logger.warning(
                "Failed to load raw layout for debug",
                extra={
                    "doc_id": str(doc_id),
                    "version_id": str(version.id),
                    "error": str(e),
                },
            )

    if include_sanitized and sanitized_ref:
        try:
            sanitized_layout = store.get_json(sanitized_ref)
        except Exception as e:
            logger.warning(
                "Failed to load sanitized layout for debug",
                extra={
                    "doc_id": str(doc_id),
                    "version_id": str(version.id),
                    "error": str(e),
                },
            )

    return DocumentLayoutsDebugResponse(
        document_id=str(doc_id),
        deal_id=str(doc.deal_id),
        raw_layout_ref=raw_ref,
        sanitized_layout_ref=sanitized_ref,
        raw_layout=raw_layout,
        sanitized_layout=sanitized_layout,
    )

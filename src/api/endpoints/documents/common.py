# src/api/endpoints/documents/common.py

"""
Shared helpers for documents endpoints.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.mappers.documents import map_document_to_response
from api.mappers.document_versions import map_document_version_to_response
from api.schemas.documents import (
    ClassificationMetadata,
    DocumentDetailResponse,
    DocumentVersionResponse,
)
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.repositories.relation_repo import RelationRepository


async def load_document_detail(
    db: AsyncSession,
    doc_id: uuid.UUID,
) -> DocumentDetailResponse:
    """
    Собрать DocumentDetailResponse из Document.

    Сейчас:
    - грузим сам документ,
    - строим DocumentResponse,
    - собираем блок ClassificationMetadata,
    - подтягиваем последнюю версию,
    - family_id.
    """
    doc_repo = DocumentRepository(db)
    version_repo = DocumentVersionRepository(db)
    relation_repo = RelationRepository(db)

    doc = await doc_repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    latest_version_obj = await version_repo.get_latest(doc_id)
    latest_version: DocumentVersionResponse | None = None
    if latest_version_obj:
        latest_version = map_document_version_to_response(latest_version_obj)

    family_id = await relation_repo.get_document_family_id(doc_id)

    yaml_instruction_available = False
    if doc.doc_type:
        yaml_path = Path(f"playbooks/document_types/{doc.doc_type}.yaml")
        yaml_instruction_available = yaml_path.exists()

    low_confidence = False
    if doc.classification_confidence is not None:
        low_confidence = 0 < doc.classification_confidence < 0.6

    document_response = map_document_to_response(doc)

    classification_block = None
    if doc.doc_type:
        classification_block = ClassificationMetadata(
            doc_type=doc.doc_type,
            classification_level=doc.classification_level or "",
            classification_confidence=doc.classification_confidence or 0.0,
            applicable_triggers=doc.applicable_triggers or [],
            yaml_instruction_available=yaml_instruction_available,
            low_confidence=low_confidence,
        )

    return DocumentDetailResponse(
        document=document_response,
        latest_version=latest_version,
        family_id=family_id,
        classification=classification_block,
    )
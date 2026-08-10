# src/services/pipeline_view/stage_primary.py

"""
Stage builder: PRIMARY — одноязычный source после выбора основного языка.
"""

from __future__ import annotations

from api.schemas.document_pipeline_view import (
    PdfPreviewDTO,
    PipelineStageCode,
    PipelineStageKind,
    PipelineStageStatus,
    PipelineStageViewDTO,
    StageMetaDTO,
)
from core.exceptions import TransientError
from storage.artifact_store import ArtifactStore


def build_primary_stage(
    doc,
    version,
    base_meta: StageMetaDTO,
    store: ArtifactStore,
) -> PipelineStageViewDTO:
    """Строит стадию PRIMARY."""
    artifact_ref = version.primary_source_ref

    if not artifact_ref:
        return PipelineStageViewDTO(
            code=PipelineStageCode.PRIMARY,
            title="PRIMARY: одноязычный source",
            description=(
                "Документ после выбора основного языка сделки, "
                "используемый как основной вход в downstream-пайплайн."
            ),
            available=False,
            kind=PipelineStageKind.pdf,
            status=PipelineStageStatus.pending,
            artifact_ref=None,
            meta=base_meta,
            preview=None,
        )

    # Проверяем существование артефакта без генерации presigned URL.
    # Browser-facing URL строится как backend streaming endpoint —
    # MinIO остаётся приватным, браузер не ходит в storage напрямую.
    try:
        artifact_exists = store.exists(artifact_ref)
    except TransientError:
        return PipelineStageViewDTO(
            code=PipelineStageCode.PRIMARY,
            title="PRIMARY: одноязычный source",
            description="Primary-source PDF временно недоступен.",
            available=False,
            kind=PipelineStageKind.pdf,
            status=PipelineStageStatus.pending,
            artifact_ref=artifact_ref,
            meta=base_meta,
            preview=None,
        )

    if not artifact_exists:
        return PipelineStageViewDTO(
            code=PipelineStageCode.PRIMARY,
            title="PRIMARY: одноязычный source",
            description="Primary-source PDF ожидается, но отсутствует в сторедже.",
            available=False,
            kind=PipelineStageKind.pdf,
            status=PipelineStageStatus.missing,
            artifact_ref=artifact_ref,
            meta=base_meta,
            preview=None,
        )

    doc_id = doc.id
    inline_url = f"/api/v1/documents/{doc_id}/primary-pdf-content"
    download_url = f"/api/v1/documents/{doc_id}/primary-pdf-content"

    preview = PdfPreviewDTO(
        type="pdf",
        inline_url=inline_url,
        download_url=download_url,
    )

    return PipelineStageViewDTO(
        code=PipelineStageCode.PRIMARY,
        title="PRIMARY: одноязычный source",
        description=(
            "Документ после выбора основного языка сделки, "
            "используемый как основной вход в downstream-пайплайн."
        ),
        available=True,
        kind=PipelineStageKind.pdf,
        status=PipelineStageStatus.ready,
        artifact_ref=artifact_ref,
        meta=base_meta,
        preview=preview,
    )

# src/services/pipeline_view/stage_source.py

"""
Stage builder: SOURCE — исходный документ (оригинал или сконвертированный PDF).
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
from core.exceptions import PermanentError, TransientError
from storage.artifact_store import ArtifactStore


def build_source_stage(
    doc,
    version,
    base_meta: StageMetaDTO,
    store: ArtifactStore,
) -> PipelineStageViewDTO:
    """Строит стадию SOURCE."""
    artifact_ref = version.converted_pdf_ref or version.original_ref

    if not artifact_ref:
        return PipelineStageViewDTO(
            code=PipelineStageCode.SOURCE,
            title="SOURCE: исходный документ",
            description=(
                "Исходный документ для обработки: оригинал или PDF после "
                "конвертации офисного формата."
            ),
            available=False,
            kind=PipelineStageKind.pdf,
            status=PipelineStageStatus.pending,
            artifact_ref=None,
            meta=base_meta,
            preview=None,
        )

    try:
        url = store.get_presigned_get_url(artifact_ref)
    except PermanentError:
        return PipelineStageViewDTO(
            code=PipelineStageCode.SOURCE,
            title="SOURCE: исходный документ",
            description="Исходный PDF ожидается, но отсутствует в сторедже.",
            available=False,
            kind=PipelineStageKind.pdf,
            status=PipelineStageStatus.missing,
            artifact_ref=artifact_ref,
            meta=base_meta,
            preview=None,
        )
    except TransientError:
        return PipelineStageViewDTO(
            code=PipelineStageCode.SOURCE,
            title="SOURCE: исходный документ",
            description="Исходный PDF временно недоступен.",
            available=False,
            kind=PipelineStageKind.pdf,
            status=PipelineStageStatus.pending,
            artifact_ref=artifact_ref,
            meta=base_meta,
            preview=None,
        )

    preview = PdfPreviewDTO(
        type="pdf",
        inline_url=url,
        download_url=url,
    )

    return PipelineStageViewDTO(
        code=PipelineStageCode.SOURCE,
        title="SOURCE: исходный документ",
        description=(
            "Исходный документ для обработки: оригинал или PDF после "
            "конвертации офисного формата."
        ),
        available=True,
        kind=PipelineStageKind.pdf,
        status=PipelineStageStatus.ready,
        artifact_ref=artifact_ref,
        meta=base_meta,
        preview=preview,
    )


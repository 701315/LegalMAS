# src/services/pipeline_view/stage_pii.py

"""
Stage builder: PII — sanitized layout после PII-маскирования.
"""

from __future__ import annotations

from api.schemas.document_pipeline_view import (
    PipelineStageCode,
    PipelineStageKind,
    PipelineStageStatus,
    PipelineStageViewDTO,
    StageMetaDTO,
)
from core.exceptions import PermanentError, TransientError
from services.pipeline_view.stage_layout import build_layout_stage_from_payload
from storage.artifact_store import ArtifactStore


def build_pii_stage(
    doc,
    version,
    base_meta: StageMetaDTO,
    store: ArtifactStore,
) -> PipelineStageViewDTO:
    """Строит стадию PII."""
    artifact_ref = (
        version.layout_primary_sanitized_ref
        or version.text_layout_sanitized_ref
    )

    if not artifact_ref:
        return PipelineStageViewDTO(
            code=PipelineStageCode.PII,
            title="PII: sanitized layout",
            description=(
                "Layout после PII-санитизации. Это основной downstream-layout "
                "для структуры, chunking и checks."
            ),
            available=False,
            kind=PipelineStageKind.layout,
            status=PipelineStageStatus.pending,
            artifact_ref=None,
            meta=base_meta,
            preview=None,
        )

    try:
        layout = store.get_json(artifact_ref)
    except PermanentError:
        return PipelineStageViewDTO(
            code=PipelineStageCode.PII,
            title="PII: sanitized layout",
            description="Артефакт sanitized layout ожидается, но отсутствует в сторедже.",
            available=False,
            kind=PipelineStageKind.layout,
            status=PipelineStageStatus.missing,
            artifact_ref=artifact_ref,
            meta=base_meta,
            preview=None,
        )
    except TransientError:
        return PipelineStageViewDTO(
            code=PipelineStageCode.PII,
            title="PII: sanitized layout",
            description="Sanitized layout временно недоступен.",
            available=False,
            kind=PipelineStageKind.layout,
            status=PipelineStageStatus.pending,
            artifact_ref=artifact_ref,
            meta=base_meta,
            preview=None,
        )

    return build_layout_stage_from_payload(
        code=PipelineStageCode.PII,
        title="PII: sanitized layout",
        description=(
            "Layout после PII-санитизации. Это основной downstream-layout "
            "для структуры, chunking и checks."
        ),
        artifact_ref=artifact_ref,
        layout=layout,
        base_meta=base_meta,
    )


# src/services/pipeline_view/stage_extract.py

"""
Stage builder: EXTRACT — text layout после извлечения.
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


def build_extract_stage(
    doc,
    version,
    base_meta: StageMetaDTO,
    store: ArtifactStore,
) -> PipelineStageViewDTO:
    """Строит стадию EXTRACT."""
    artifact_ref = version.layout_primary_ref or version.text_layout_raw_ref

    if not artifact_ref:
        return PipelineStageViewDTO(
            code=PipelineStageCode.EXTRACT,
            title="EXTRACT: layout после извлечения",
            description=(
                "Текстовый layout после extract: primary-language layout "
                "или raw multilingual layout."
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
            code=PipelineStageCode.EXTRACT,
            title="EXTRACT: layout после извлечения",
            description="Артефакт extract-layout ожидается, но отсутствует в сторедже.",
            available=False,
            kind=PipelineStageKind.layout,
            status=PipelineStageStatus.missing,
            artifact_ref=artifact_ref,
            meta=base_meta,
            preview=None,
        )
    except TransientError:
        return PipelineStageViewDTO(
            code=PipelineStageCode.EXTRACT,
            title="EXTRACT: layout после извлечения",
            description="Артефакт extract-layout временно недоступен.",
            available=False,
            kind=PipelineStageKind.layout,
            status=PipelineStageStatus.pending,
            artifact_ref=artifact_ref,
            meta=base_meta,
            preview=None,
        )

    return build_layout_stage_from_payload(
        code=PipelineStageCode.EXTRACT,
        title="EXTRACT: layout после извлечения",
        description=(
            "Текстовый layout после extract: primary-language layout "
            "или raw multilingual layout."
        ),
        artifact_ref=artifact_ref,
        layout=layout,
        base_meta=base_meta,
    )


# src/services/pipeline_view/representation.py

"""
Логика построения StageRepresentationDTO для pipeline view.

Определяет, как стадия отображается в UI в зависимости от view_mode.
"""

from __future__ import annotations

from api.schemas.document_pipeline_view import (
    PipelineStageCode,
    PipelineStageViewDTO,
    StageProvenanceDTO,
    StageRepresentationDTO,
    StageViewMode,
)


def build_stage_representation(
    *,
    stage_code: PipelineStageCode,
    view_mode: StageViewMode,
    friendly_supported: bool = False,
    friendly_description: str | None = None,
    canonical_description: str | None = None,
    derived_from_stages: list[PipelineStageCode] | None = None,
    preview_source_label: str | None = None,
) -> StageRepresentationDTO:
    """
    Строит единое описание режима представления стадии для UI.

    Логика:
    - canonical: всегда "Результат этапа";
    - friendly:
        - если у стадии реально есть отдельный friendly-режим,
          помечаем её как производное представление;
        - если friendly пока не поддержан, используем тот же результат,
          но явно говорим, что это friendly-режим без отдельного источника данных.
    """
    derived = derived_from_stages or []

    if view_mode == StageViewMode.canonical:
        return StageRepresentationDTO(
            view_mode=view_mode,
            is_canonical=True,
            label="Результат этапа",
            description=canonical_description
            or "Показывается точный результат этого этапа.",
            provenance=StageProvenanceDTO(
                primary_source_stage=stage_code,
                derived_from_stages=[],
                preview_source_label=None,
            ),
        )

    if friendly_supported:
        return StageRepresentationDTO(
            view_mode=view_mode,
            is_canonical=False,
            label="Удобный вид",
            description=friendly_description
            or "Показывается более удобное для чтения представление.",
            provenance=StageProvenanceDTO(
                primary_source_stage=stage_code,
                derived_from_stages=derived,
                preview_source_label=preview_source_label,
            ),
        )

    return StageRepresentationDTO(
        view_mode=view_mode,
        is_canonical=False,
        label="Удобный вид",
        description=(
            friendly_description
            or "Для этого этапа отдельный friendly-режим не поддержан; "
               "показывается тот же результат этапа в режиме удобного просмотра."
        ),
        provenance=StageProvenanceDTO(
            primary_source_stage=stage_code,
            derived_from_stages=[],
            preview_source_label="Тот же результат этапа",
        ),
    )


def with_representation(
    stage: PipelineStageViewDTO,
    *,
    stage_code: PipelineStageCode,
    view_mode: StageViewMode,
    friendly_supported: bool = False,
    friendly_description: str | None = None,
    canonical_description: str | None = None,
    derived_from_stages: list[PipelineStageCode] | None = None,
    preview_source_label: str | None = None,
) -> PipelineStageViewDTO:
    """
    Возвращает копию стадии с заполненным полем representation.
    Исходный DTO не мутируется.
    """
    return stage.model_copy(
        update={
            "representation": build_stage_representation(
                stage_code=stage_code,
                view_mode=view_mode,
                friendly_supported=friendly_supported,
                friendly_description=friendly_description,
                canonical_description=canonical_description,
                derived_from_stages=derived_from_stages,
                preview_source_label=preview_source_label,
            )
        }
    )


# src/services/pipeline_view/stage_layout.py

"""
Общий builder для layout-стадий (EXTRACT, PII).

Разделяет layout-payload на страницы и строит LayoutPreviewDTO.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from api.schemas.document_pipeline_view import (
    LayoutPagePreviewDTO,
    LayoutPreviewDTO,
    PipelineStageCode,
    PipelineStageKind,
    PipelineStageStatus,
    PipelineStageViewDTO,
    StageMetaDTO,
)


def build_layout_stage_from_payload(
    *,
    code: PipelineStageCode,
    title: str,
    description: str,
    artifact_ref: str,
    layout: dict[str, Any] | list[Any],
    base_meta: StageMetaDTO,
) -> PipelineStageViewDTO:
    """Строит layout-стадию из загруженного JSON-payload."""
    if not isinstance(layout, dict):
        layout = {"raw": layout, "elements": []}

    elements = layout.get("elements") or []
    by_page: dict[int, list[str]] = defaultdict(list)
    count_by_page: dict[int, int] = defaultdict(int)

    for el in elements:
        if not isinstance(el, dict):
            continue
        page = el.get("page")
        text = el.get("text") or ""
        if not isinstance(page, int):
            continue
        count_by_page[page] += 1
        if text:
            by_page[page].append(str(text))

    pages: list[LayoutPagePreviewDTO] = []
    all_pages = sorted(set(count_by_page.keys()) | set(by_page.keys()))
    for page_num in all_pages:
        pages.append(
            LayoutPagePreviewDTO(
                page=page_num,
                text="\n".join(by_page.get(page_num, [])),
                element_count=count_by_page.get(page_num, 0),
            )
        )

    preview = LayoutPreviewDTO(
        type="layout",
        pages=pages,
        raw_json=layout,
    )

    meta = StageMetaDTO(
        page_count=base_meta.page_count,
        element_count=len(elements),
        chunk_count=base_meta.chunk_count,
        section_count=base_meta.section_count,
        source_file_name=base_meta.source_file_name,
        mime_type=base_meta.mime_type,
    )

    return PipelineStageViewDTO(
        code=code,
        title=title,
        description=description,
        available=True,
        kind=PipelineStageKind.layout,
        status=PipelineStageStatus.ready,
        artifact_ref=artifact_ref,
        meta=meta,
        preview=preview,
    )


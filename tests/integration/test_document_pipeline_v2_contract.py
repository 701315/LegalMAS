from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

import pytest

from src.api.schemas.document_pipeline_view import (
    ChunksPreviewDTO,
    DocumentPipelineViewResponseDTO,
    PipelineStageCode,
    StageViewMode,
    StructurePreviewDTO,
)
from src.services.document_pipeline_view_service import DocumentPipelineViewService


@dataclass
class ValidationReport:
    ok: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add_ok(self, msg: str) -> None:
        self.ok.append(msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)

    def assert_valid(self) -> None:
        if self.errors:
            details = "\n".join(f"- {msg}" for msg in self.errors)
            pytest.fail(f"Pipeline v2 contract validation failed:\n{details}")


def _get_stage(response: DocumentPipelineViewResponseDTO, code: PipelineStageCode):
    return next((stage for stage in response.stages if stage.code == code), None)


def _validate_root(
    response: DocumentPipelineViewResponseDTO,
    expected_view_mode: StageViewMode,
    report: ValidationReport,
) -> None:
    if response.view_mode == expected_view_mode:
        report.add_ok(f"root.view_mode={expected_view_mode.value}")
    else:
        report.add_error(
            f"root.view_mode mismatch: expected={expected_view_mode.value}, actual={response.view_mode.value}"
        )

    actual_codes = {stage.code for stage in response.stages}
    expected_codes = {
        PipelineStageCode.SOURCE,
        PipelineStageCode.PRIMARY,
        PipelineStageCode.EXTRACT,
        PipelineStageCode.PII,
        PipelineStageCode.STRUCTURE,
        PipelineStageCode.CHUNKS,
    }
    missing = expected_codes - actual_codes
    if missing:
        report.add_warning(
            f"missing expected stages: {[code.value for code in sorted(missing, key=lambda x: x.value)]}"
        )
    else:
        report.add_ok("all expected stages are present")


def _validate_representation(stage, expected_view_mode: StageViewMode, report: ValidationReport) -> None:
    code = stage.code.value
    representation = stage.representation

    if representation.view_mode == expected_view_mode:
        report.add_ok(f"{code}: representation.view_mode={expected_view_mode.value}")
    else:
        report.add_error(
            f"{code}: representation.view_mode mismatch: "
            f"expected={expected_view_mode.value}, actual={representation.view_mode.value}"
        )

    if expected_view_mode == StageViewMode.canonical and representation.is_canonical is not True:
        report.add_error(f"{code}: canonical stage must have is_canonical=True")
    else:
        report.add_ok(f"{code}: representation.is_canonical is valid")

    if representation.provenance is None:
        report.add_warning(f"{code}: representation.provenance is missing")
    else:
        report.add_ok(f"{code}: representation.provenance is present")


def _index_chunks(preview: ChunksPreviewDTO) -> tuple[dict[int, object], dict[tuple[str, str], object]]:
    by_index = {}
    by_segment_and_chunk_id = {}

    for chunk in preview.chunks:
        by_index[chunk.index] = chunk
        if chunk.segment_id and chunk.chunk_id:
            by_segment_and_chunk_id[(chunk.segment_id, chunk.chunk_id)] = chunk

    return by_index, by_segment_and_chunk_id


def _validate_chunks_stage(stage, report: ValidationReport) -> ChunksPreviewDTO | None:
    if not isinstance(stage.preview, ChunksPreviewDTO):
        report.add_error("CHUNKS.preview is missing or has invalid type")
        return None

    preview = stage.preview

    report.add_ok(f"CHUNKS chunk_count={len(preview.chunks)}")
    report.add_ok(f"CHUNKS segment_count={len(preview.segments)}")

    if preview.segments:
        total_segmented_chunks = 0
        for seg_preview in preview.segments:
            segment = seg_preview.segment
            if not segment.segment_id:
                report.add_error("CHUNKS segment without segment_id")
                continue

            for chunk in seg_preview.chunks:
                if chunk.segment_id != segment.segment_id:
                    report.add_error(
                        f"CHUNKS chunk.segment_id mismatch: "
                        f"segment={segment.segment_id}, chunk={chunk.segment_id}"
                    )
                total_segmented_chunks += 1

        report.add_ok(f"CHUNKS segmented corpus validated, grouped_chunks={total_segmented_chunks}")
    else:
        report.add_warning("CHUNKS is in legacy flat mode: segments[] is empty")

    return preview


def _validate_structure_stage(
    stage,
    chunks_preview: ChunksPreviewDTO | None,
    expected_view_mode: StageViewMode,
    report: ValidationReport,
) -> None:
    if not isinstance(stage.preview, StructurePreviewDTO):
        report.add_error("STRUCTURE.preview is missing or has invalid type")
        return

    preview = stage.preview
    report.add_ok(f"STRUCTURE section_count={len(preview.sections)}")
    report.add_ok(f"STRUCTURE segment_count={len(preview.segments)}")

    chunks_by_index = {}
    chunks_by_seg_chunk_id = {}
    if chunks_preview is not None:
        chunks_by_index, chunks_by_seg_chunk_id = _index_chunks(chunks_preview)

    mapped_sections = 0
    matched_refs = 0

    for section in preview.sections:
        if not section.id:
            report.add_error("STRUCTURE section has empty id")

        if expected_view_mode == StageViewMode.canonical:
            if section.text_preview != section.structure_text:
                report.add_error(
                    f"STRUCTURE section {section.id}: canonical text_preview must equal structure_text"
                )
            else:
                report.add_ok(f"STRUCTURE section {section.id}: canonical text preview OK")
        else:
            expected_preview = section.enriched_text or section.structure_text
            if section.text_preview != expected_preview:
                report.add_error(
                    f"STRUCTURE section {section.id}: friendly text_preview mismatch"
                )
            else:
                report.add_ok(f"STRUCTURE section {section.id}: friendly text preview OK")

        if preview.segments and section.segment_id is None:
            report.add_warning(
                f"STRUCTURE section {section.id}: segments[] present but section.segment_id is empty"
            )

        mapping = section.source_mapping
        if mapping is None:
            continue

        mapped_sections += 1

        if mapping.chunk_indices and mapping.chunk_indices != sorted(set(mapping.chunk_indices)):
            report.add_error(
                f"STRUCTURE section {section.id}: chunk_indices are not unique/sorted"
            )

        if mapping.match_strategy == "chunk_refs" and not (mapping.chunk_refs or mapping.chunk_indices):
            report.add_error(
                f"STRUCTURE section {section.id}: match_strategy=chunk_refs but no refs/indices"
            )

        for ref in mapping.chunk_refs:
            matched = False

            if ref.segment_id and ref.chunk_id:
                if (ref.segment_id, ref.chunk_id) in chunks_by_seg_chunk_id:
                    matched = True

            if not matched and ref.chunk_index is not None:
                if ref.chunk_index in chunks_by_index:
                    matched = True

            if matched:
                matched_refs += 1
            else:
                report.add_error(
                    f"STRUCTURE section {section.id}: chunk_ref not found in CHUNKS "
                    f"(segment_id={ref.segment_id}, chunk_index={ref.chunk_index}, chunk_id={ref.chunk_id})"
                )

    report.add_ok(f"STRUCTURE mapped_sections={mapped_sections}")
    if chunks_preview is not None:
        report.add_ok(f"STRUCTURE matched_chunk_refs={matched_refs}")


async def _build_response(
    *,
    session,
    artifact_store,
    document_id: UUID,
    view_mode: StageViewMode,
) -> DocumentPipelineViewResponseDTO:
    service = DocumentPipelineViewService(
        session=session,
        store=artifact_store,
    )
    return await service.build(
        doc_id=document_id,
        view_mode=view_mode,
    )


async def _validate_response(
    *,
    session,
    artifact_store,
    document_id: UUID,
    view_mode: StageViewMode,
) -> ValidationReport:
    report = ValidationReport()
    response = await _build_response(
        session=session,
        artifact_store=artifact_store,
        document_id=document_id,
        view_mode=view_mode,
    )

    _validate_root(response, view_mode, report)

    structure_stage = _get_stage(response, PipelineStageCode.STRUCTURE)
    chunks_stage = _get_stage(response, PipelineStageCode.CHUNKS)

    if structure_stage is None:
        report.add_error("STRUCTURE stage is missing")
        return report
    if chunks_stage is None:
        report.add_error("CHUNKS stage is missing")
        return report

    _validate_representation(structure_stage, view_mode, report)
    _validate_representation(chunks_stage, view_mode, report)

    chunks_preview = _validate_chunks_stage(chunks_stage, report)
    _validate_structure_stage(structure_stage, chunks_preview, view_mode, report)

    return report


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize(
    "view_mode",
    [StageViewMode.canonical, StageViewMode.friendly],
)
async def test_document_pipeline_v2_contract_for_single_document(
    db_session,
    artifact_store,
    pipeline_test_document_id,
    view_mode: StageViewMode,
):
    report = await _validate_response(
        session=db_session,
        artifact_store=artifact_store,
        document_id=UUID(str(pipeline_test_document_id)),
        view_mode=view_mode,
    )
    report.assert_valid()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_document_pipeline_v2_contract_summary_for_single_document(
    db_session,
    artifact_store,
    pipeline_test_document_id,
):
    canonical = await _validate_response(
        session=db_session,
        artifact_store=artifact_store,
        document_id=UUID(str(pipeline_test_document_id)),
        view_mode=StageViewMode.canonical,
    )
    friendly = await _validate_response(
        session=db_session,
        artifact_store=artifact_store,
        document_id=UUID(str(pipeline_test_document_id)),
        view_mode=StageViewMode.friendly,
    )

    canonical.assert_valid()
    friendly.assert_valid()

    
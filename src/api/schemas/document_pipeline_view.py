# src/api/schemas/document_pipeline_view.py

"""
Pydantic DTO schemas for representing the document processing pipeline
in the UI (Document Pipeline View).

Used in APIs that expose step-by-step progress of a document:
- Which stages are completed (SOURCE, PRIMARY, EXTRACT, PII, STRUCTURE, CHUNKS);
- Status of each stage (ready/missing/pending) and artifact type (pdf/layout/structure/chunks);
- Stage metadata (number of pages/elements/chunks, source filename, MIME type);
- Artifact previews: PDF, layout (pages with text and element counters),
  structure (headers/sections), and chunks (text fragments bound to pages).

Core models:
- PipelineStageCode, PipelineStageStatus, PipelineStageKind — stage and status enum codes;
- StageMetaDTO — aggregated stage metadata;
- PdfPreviewDTO / LayoutPreviewDTO / StructurePreviewDTO / ChunksPreviewDTO —
  strongly-typed previews of various artifacts;
- PipelineStageViewDTO — a single pipeline stage with metadata and preview;
- DocumentPipelineViewResponseDTO — API response containing all stage states for a single document.

Additional:
- StageViewMode — stage presentation mode for the UI;
- StageProvenanceDTO — data provenance information for the current view;
- StageRepresentationDTO — details on whether the current view is canonical
  or a more convenient derived representation.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class PipelineStageCode(str, Enum):
    SOURCE = "SOURCE"
    PRIMARY = "PRIMARY"
    EXTRACT = "EXTRACT"
    PII = "PII"
    STRUCTURE = "STRUCTURE"
    CHUNKS = "CHUNKS"


class PipelineStageStatus(str, Enum):
    ready = "ready"
    missing = "missing"
    pending = "pending"


class PipelineStageKind(str, Enum):
    pdf = "pdf"
    layout = "layout"
    structure = "structure"
    chunks = "chunks"


class StageViewMode(str, Enum):
    """
    Stage rendering mode in the UI.

    canonical:
        Shows the exact result of this stage without any additional
        derived representations.

    friendly:
        Shows a more readable view. It can utilize data from adjacent stages,
        but must be explicitly flagged as a derived mode.
    """

    canonical = "canonical"
    friendly = "friendly"


class StageMetaDTO(BaseModel):
    page_count: int | None = None
    element_count: int | None = None
    chunk_count: int | None = None
    section_count: int | None = None
    source_file_name: str | None = None
    mime_type: str | None = None
    # Flag indicating whether the STRUCTURE section text is enriched
    # with data from the canonical snapshot CHUNKS (friendly mode).
    text_enriched: bool | None = None


class StageProvenanceDTO(BaseModel):
    """
    Information about data provenance in the current stage view.

    primary_source_stage:
        The stage acting as the primary source of truth for this view.
        Examples:
        - canonical STRUCTURE: STRUCTURE
        - friendly STRUCTURE: STRUCTURE (base), but enriched from CHUNKS
        - canonical CHUNKS: CHUNKS

    derived_from_stages:
        Additional stages used to enrich or build the "friendly view".
        Examples:
        - friendly STRUCTURE: [CHUNKS]
        - friendly layout/text (if introduced): [SOURCE, PRIMARY]

    preview_source_label:
        Short human-readable label for the UI.
        Examples:
        - "STRUCTURE clause tree"
        - "Section text enriched from CHUNKS"
        - "Canonical snapshot CHUNKS"
    """

    primary_source_stage: PipelineStageCode | None = None
    derived_from_stages: list[PipelineStageCode] = Field(default_factory=list)
    preview_source_label: str | None = None


class StageRepresentationDTO(BaseModel):
    """
    Description of the current stage presentation mode.

    view_mode:
        Technical presentation mode ("canonical" or "friendly").

    is_canonical:
        Explicit flag for the frontend. Ensures the UI does not have to compute this.
        Examples:
        - canonical STRUCTURE: view_mode="canonical", is_canonical=True
        - friendly STRUCTURE: view_mode="friendly", is_canonical=False
        - canonical CHUNKS: view_mode="canonical", is_canonical=True

    label:
        Short user-facing label of the mode.
        Examples:
        - "Stage Result" (canonical)
        - "Friendly View" (friendly)

    description:
        Brief explanation of what is currently displayed on the screen.
        Examples:
        - "Canonical clause tree from STRUCTURE"
        - "Section text enriched from CHUNKS"
        - "Canonical snapshot of text chunks"

    provenance:
        Data provenance details for the current view (StageProvenanceDTO).
    """

    view_mode: StageViewMode = StageViewMode.canonical
    is_canonical: bool = True
    label: str = "Stage Result"
    description: str | None = None
    provenance: StageProvenanceDTO = Field(default_factory=StageProvenanceDTO)


class PdfPreviewDTO(BaseModel):
    type: Literal["pdf"] = "pdf"
    inline_url: str | None = None
    download_url: str | None = None


class LayoutPagePreviewDTO(BaseModel):
    page: int
    text: str
    element_count: int = 0


class LayoutPreviewDTO(BaseModel):
    type: Literal["layout"] = "layout"
    pages: list[LayoutPagePreviewDTO] = Field(default_factory=list)
    raw_json: dict[str, Any] | list[Any] | None = None


class PipelineSegmentDTO(BaseModel):
    segment_id: str
    segment_type: str
    segment_title: str | None = None
    segment_order: int
    is_primary: bool = False
    page_from: int | None = None
    page_to: int | None = None


class ChunkRefDTO(BaseModel):
    segment_id: str
    chunk_index: int | None = None
    chunk_id: str | None = None


class SectionSourceMappingDTO(BaseModel):
    """
    Binding of a STRUCTURE section to the original document text layer.

    This is not about friendly text, but rather where this section was "sliced" from:
    - from which chunks;
    - on which pages;
    - with which text quote, so the frontend can highlight the original.
    """

    # Which text layer is considered the "source" for the right column
    # (PRIMARY pdf, EXTRACT layout/text, CHUNKS text chunks).
    source_stage: PipelineStageCode = PipelineStageCode.CHUNKS

    # Fallback binding by pages (if a more precise one is missing).
    page_from: int | None = None
    page_to: int | None = None

    # legacy
    chunk_indices: list[int] = Field(default_factory=list)

    # v2 canonical
    chunk_refs: list[ChunkRefDTO] = Field(default_factory=list)
    segment_id: str | None = None

    # Optional text quote to find/highlight inside the source text.
    # E.g., first paragraph of a section or a characteristic fragment.
    match_text: str | None = None

    # How the anchor was resolved:
    # - "chunk_refs": via clause_uid -> chunks
    # - "text_quote": from raw source text
    # - "page_window": bound only by pages
    match_strategy: Literal["chunk_refs", "text_quote", "page_window"] = "chunk_refs"


class StructureSectionPreviewDTO(BaseModel):
    """
    Representation of a single document section/item for STRUCTURE-view.

    Text layers:

    - structure_text:
        Canonical node text from the clause tree (STRUCTURE stage).
        Populated during the _flatten_clause_tree phase and MUST NOT
        be overwritten by enrichment logic.

    - enriched_text:
        Enriched section text assembled on top of the canonical snapshot CHUNKS
        (friendly-STRUCTURE and/or inherited from child sections).
        Remains empty if enrichment was not executed or failed.

    - text_preview:
        Legacy/UI-oriented field for a brief preview of section text,
        kept for backward compatibility with old frontend and external clients.

        For the new UI, a V2-ONLY contract applies:

        * canonical-STRUCTURE:
            UI reads structure_text and ignores text_preview.

        * friendly-STRUCTURE:
            UI reads enriched_text (if present), falls back to structure_text,
            while text_preview does not participate in display logic.
    """

    # Stable technical node identifier for UI.
    # Needed for React keys, section selection, and other UI logic.
    id: str

    # Domain clause identifier of the document.
    # Needed to link structure -> canonical chunks -> checks/results.
    clause_uid: str | None = None

    title: str
    level: int = 1
    page_from: int | None = None
    page_to: int | None = None

    # v2 segment provenance
    segment_id: str | None = None
    segment_type: str | None = None
    segment_title: str | None = None
    segment_order: int | None = None
    is_primary_segment: bool | None = None

    # 1) Clean text from the clause tree (STRUCTURE stage).
    #    This text is set during the _flatten_clause_tree phase
    #    and must not be overwritten by enrichment logic.
    structure_text: str = ""

    # 2) Enriched section text from the canonical snapshot CHUNKS
    #    (friendly-STRUCTURE and/or inherited from child sections).
    #    Remains empty if enrichment was not executed or failed.
    enriched_text: str = ""

    # 3) Legacy/UI-oriented field for a brief preview.
    #
    #    For external clients, the old contract is preserved:
    #
    #    canonical:
    #        text_preview = structure_text
    #    friendly:
    #        text_preview = enriched_text (if present) else structure_text.
    #
    #    The new UI in V2_ONLY mode does NOT use text_preview.
    text_preview: str = ""

    # Section binding to original text (pages, chunks, quote).
    source_mapping: SectionSourceMappingDTO | None = None


class StructureSegmentPreviewDTO(BaseModel):
    segment: PipelineSegmentDTO
    sections: list[StructureSectionPreviewDTO] = Field(default_factory=list)
    raw_json: dict[str, Any] | list[Any] | None = None


class StructurePreviewDTO(BaseModel):
    type: Literal["structure"] = "structure"
    # legacy flattened view
    sections: list[StructureSectionPreviewDTO] = Field(default_factory=list)

    # v2 canonical view
    segments: list[StructureSegmentPreviewDTO] = Field(default_factory=list)

    raw_json: dict[str, Any] | list[Any] | None = None


class ChunkPreviewDTO(BaseModel):
    index: int
    clause_uid: str = ""
    page_from: int | None = None
    page_to: int | None = None
    text: str

    # v2 segment provenance
    segment_id: str | None = None
    segment_type: str | None = None
    segment_title: str | None = None
    segment_order: int | None = None
    is_primary_segment: bool | None = None

    # optional stable ids/provenance
    chunk_id: str | None = None

    # ── true chunk identity ──────────────────────────────────────────
    # Real chunk level from backend truth.
    # "section" | "clause" | "subclause" | None (if unknown)
    # Never computed on the frontend — populated by the backend from metadata.
    chunk_kind: str | None = None

    # Canonical identity of the chunk in the retrieval pipeline.
    # This is the resolved uid — exactly what is used in retrieval/checks.
    # clause_uid might be raw/display uid and differ from effective_uid.
    effective_uid: str | None = None

    # Retrieval safety flag.
    # True  = chunk is actively used in retrieval/checks.
    # False = chunk exists in artifact but is filtered out (unsafe).
    # None  = information unavailable (legacy artifact or not enriched).
    retrieval_safe: bool | None = None

    # ── backend-driven presentation DTO ───────────────────────────────
    display_title: str = ""
    display_subtitle: str = ""
    role: Literal["evidence", "context"] = "evidence"


class ChunksSegmentPreviewDTO(BaseModel):
    segment: PipelineSegmentDTO
    chunks: list[ChunkPreviewDTO] = Field(default_factory=list)
    reconstructed_text: str = ""
    raw_json: dict[str, Any] | list[Any] | None = None


class ChunksPreviewDTO(BaseModel):
    """
    Representation of document text chunks for CHUNKS-view.

    Two presentation layers:

    - legacy flattened view (chunks):
        Flat list of chunks without segment division. Kept for
        backward compatibility with the old frontend and external clients.

    - v2 canonical view (segments):
        Segment-aware body of chunks (ChunksSegmentPreviewDTO), which
        is used as the single source of truth in the new UI.

    The new UI in V2_ONLY mode:
    - builds the chunk list ONLY from segments[].chunks;
    - does not use the flattened chunks list as a data source.
    """

    type: Literal["chunks"] = "chunks"
    # legacy flattened view (legacy contract, not used by canonical UI)
    chunks: list[ChunkPreviewDTO] = Field(default_factory=list)

    # v2 canonical view (single source of truth for the UI)
    segments: list[ChunksSegmentPreviewDTO] = Field(default_factory=list)
    reconstructed_text: str = ""
    raw_json: dict[str, Any] | list[Any] | None = None


PipelinePreviewDTO = PdfPreviewDTO | LayoutPreviewDTO | StructurePreviewDTO | ChunksPreviewDTO


class PipelineStageViewDTO(BaseModel):
    code: PipelineStageCode
    title: str
    description: str
    available: bool
    kind: PipelineStageKind
    status: PipelineStageStatus
    artifact_ref: str | None = None
    meta: StageMetaDTO = Field(default_factory=StageMetaDTO)
    preview: PipelinePreviewDTO | None = None

    # Explains in which mode the stage is displayed
    # and the provenance of the current view's data.
    representation: StageRepresentationDTO = Field(
        default_factory=StageRepresentationDTO,
    )


class DocumentPipelineViewResponseDTO(BaseModel):
    document_id: str
    document_version_id: str
    document_status: str

    # Global view mode used to compile the response.
    # Convenient for the frontend to initialize toggles.
    view_mode: StageViewMode

    stages: list[PipelineStageViewDTO] = Field(default_factory=list)

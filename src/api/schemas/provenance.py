# src/api/schemas/provenance.py

"""
Pydantic schemas для Decision Provenance API (Этап 4).

Три endpoint'а:
1. GET /documents/{doc_id}/processing-trace  — stage execution traces
2. GET /documents/{doc_id}/classification-decision — classification explainability
3. GET /checks/{check_result_id}/provenance  — check result provenance
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel


# ─── Processing Trace ─────────────────────────────────────────────────────────


class StageTraceDTO(BaseModel):
    """
    Trace одной стадии pipeline.
    Содержимое result_details из document_stage_executions.
    """
    task_name: str
    status: str                       # succeeded | failed | started | cancelled
    schema_version: int | None = None
    stage: str | None = None
    trace_status: str | None = None   # succeeded | failed | skipped | partial
    strategy: str | None = None
    started_at: str | None = None     # ISO из БД
    finished_at: str | None = None    # ISO из result_details
    duration_ms: int | None = None
    input_summary: dict[str, Any] | None = None
    output_summary: dict[str, Any] | None = None
    warnings: list[Any] | None = None
    artifact_refs: dict[str, Any] | None = None
    decision_details: dict[str, Any] | None = None
    error_details: dict[str, Any] | None = None


class ProcessingTraceResponseDTO(BaseModel):
    """
    Полная трасса pipeline обработки одного документа.
    """
    document_id: str
    document_version_id: str | None = None
    document_status: str
    stages: list[StageTraceDTO]


# ─── Classification Decision ──────────────────────────────────────────────────


class ClassificationCandidateDTO(BaseModel):
    """Один кандидат классификации."""
    type_code: str | None = None
    doctype: str | None = None
    confidence: float | None = None
    level: str | None = None
    method: str | None = None
    evidence: str | None = None


class ClassificationDecisionDTO(BaseModel):
    """
    Explainability для решения о типе документа.
    Читается из Document.classification_details и Document.doc_type.
    """
    document_id: str
    doc_type: str | None = None
    classification_outcome: str | None = None   # typed | unknown | failed | pending
    confidence: float | None = None
    classification_level: str | None = None     # L1 | L2 | L3 | L4 | HYBRID
    language: str | None = None
    jurisdiction: str | None = None
    requires_manual_review: bool = False
    applicable_triggers: list[str] = []
    playbook_version_id: str | None = None

    # Decision explainability (из classification_details)
    decided_by: str | None = None
    levels_tried: list[str] = []
    confidence_zone: str | None = None         # confident | low | unknown
    candidates: list[ClassificationCandidateDTO] = []
    unknown_corridor_applied: bool | None = None
    voting_score: float | None = None
    l4_triggered: bool | None = None


# ─── Check Provenance ─────────────────────────────────────────────────────────


class ContextTraceItemDTO(BaseModel):
    """
    Один элемент retrieval provenance trace (из context_trace JSONB).
    """
    rank: int | None = None
    score: float | None = None
    score_breakdown: dict[str, Any] | None = None
    chunk_id: str | None = None
    chunk_index: int | None = None
    clause_uid: str | None = None
    element_id: str | None = None
    page: int | None = None
    segment_id: str | None = None
    segment_type: str | None = None
    segment_title: str | None = None
    segment_order: int | None = None
    is_primary_segment: bool | None = None


class CheckProvenanceDTO(BaseModel):
    """
    Полный provenance для одного check result.
    """
    result_id: str
    check_id: str
    check_name: str
    document_id: str
    run_id: str

    # Outcome
    result: str                        # fail | pass | unclear
    severity: str
    confidence: float | None = None
    detector_used: str | None = None
    execution_status: str | None = None

    # User-facing semantics
    display_text: str | None = None
    review_status: str | None = None
    review_message: str | None = None
    needs_manual_review: bool = False
    ui_mode: str | None = None

    # Primary evidence
    evidence_ref: str | None = None
    page: int | None = None
    clause_uid: str | None = None
    element_id: str | None = None
    bbox: dict[str, Any] | None = None

    # Retrieval provenance
    chunk_id: str | None = None
    chunk_index: int | None = None
    context_trace: list[ContextTraceItemDTO] = []

    # Segment provenance
    segment_id: str | None = None
    segment_type: str | None = None
    segment_title: str | None = None
    segment_order: int | None = None
    is_primary_segment: bool | None = None

    # Structured extraction
    structured_data: dict[str, Any] | None = None

    # Diagnostics
    quality_flags: dict[str, Any] | None = None
    error_details: dict[str, Any] | None = None


    
// frontend/src/api/provenance.ts

import { useQuery } from "@tanstack/react-query";
import client from "./client";

// ─── Types ───────────────────────────────────────────────────

export interface StageTraceDTO {
  task_name: string;
  status: string;
  schema_version?: number | null;
  stage?: string | null;
  trace_status?: string | null;
  strategy?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms?: number | null;
  input_summary?: Record<string, unknown> | null;
  output_summary?: Record<string, unknown> | null;
  warnings?: unknown[] | null;
  artifact_refs?: Record<string, unknown> | null;
  decision_details?: Record<string, unknown> | null;
  error_details?: Record<string, unknown> | null;
}

export interface ProcessingTraceResponse {
  document_id: string;
  document_version_id?: string | null;
  document_status: string;
  stages: StageTraceDTO[];
}

export interface ContextTraceItemDTO {
  rank?: number | null;
  score?: number | null;
  score_breakdown?: Record<string, unknown> | null;
  chunk_id?: string | null;
  chunk_index?: number | null;
  clause_uid?: string | null;
  element_id?: string | null;
  page?: number | null;
  segment_id?: string | null;
  segment_type?: string | null;
  segment_title?: string | null;
  segment_order?: number | null;
  is_primary_segment?: boolean | null;
}

export interface CheckProvenance {
  result_id: string;
  check_id: string;
  check_name: string;
  document_id: string;
  run_id: string;
  result: string;
  severity: string;
  confidence?: number | null;
  detector_used?: string | null;
  execution_status?: string | null;
  display_text?: string | null;
  review_status?: string | null;
  review_message?: string | null;
  needs_manual_review: boolean;
  ui_mode?: string | null;
  evidence_ref?: string | null;
  page?: number | null;
  clause_uid?: string | null;
  element_id?: string | null;
  bbox?: Record<string, unknown> | null;
  chunk_id?: string | null;
  chunk_index?: number | null;
  context_trace: ContextTraceItemDTO[];
  segment_id?: string | null;
  segment_type?: string | null;
  segment_title?: string | null;
  segment_order?: number | null;
  is_primary_segment?: boolean | null;
  structured_data?: Record<string, unknown> | null;
  quality_flags?: Record<string, unknown> | null;
  error_details?: Record<string, unknown> | null;
}

// ─── API ─────────────────────────────────────────────────────

export const provenanceApi = {
  getProcessingTrace: (documentId: string) =>
    client
      .get<ProcessingTraceResponse>(
        `/api/v1/documents/${documentId}/processing-trace`,
      )
      .then((r) => r.data),

  getCheckProvenance: (checkResultId: string) =>
    client
      .get<CheckProvenance>(`/api/v1/checks/${checkResultId}/provenance`)
      .then((r) => r.data),
};

// ─── Hooks ───────────────────────────────────────────────────

export function useProcessingTrace(documentId: string | null) {
  return useQuery({
    queryKey: ["processing-trace", documentId],
    queryFn: () => provenanceApi.getProcessingTrace(documentId!),
    enabled: !!documentId,
    staleTime: 5 * 60_000,
  });
}

export function useCheckProvenance(checkResultId: string | null) {
  return useQuery({
    queryKey: ["check-provenance", checkResultId],
    queryFn: () => provenanceApi.getCheckProvenance(checkResultId!),
    enabled: !!checkResultId,
    staleTime: 5 * 60_000,
  });
}




// =============================================================
// src/types/classificationInvestigation.ts
// Типы для explainability / investigation API классификации.
// =============================================================

import type { DocumentCompositionMeta } from "./documents";

export interface ClassificationInvestigationSummary {
  total_documents: number;
  classified_count: number;
  manual_review_count: number;
  unknown_count: number;
  l4_count: number;
  contradiction_count: number;
}

export interface ClassificationCandidateResponse {
  doctype: string;
  confidence: number;
  level: string;
  method: string | null;
  evidence: string | null;
  language: string | null;
  jurisdiction: string | null;
  extra: Record<string, unknown> | null;
}

export interface ClassificationLevelResultResponse {
  level: string;
  type: string | null;
  confidence: number | null;
  method: string | null;
  evidence: string | null;
  extra: Record<string, unknown> | null;
}

export interface ClassificationVotingResponse {
  strategy: string | null;
  reason: string | null;
  type: string | null;
  confidence: number | null;
  margin: number | null;
  ranking: Array<Record<string, unknown>>;
  override: Record<string, unknown> | null;
}

export interface ClassificationSegmentSummaryResponse {
  segment_count: number | null;
  primary_segment_id: string | null;
  primary_segment_label: string | null;
  has_segment_classification: boolean | null;
}

export interface ClassificationInvestigationRow {
  document_id: string;
  filename: string;
  folder_path: string | null;
  status: string;

  doc_type: string | null;
  classification_level: string | null;
  classification_confidence: number | null;
  applicable_triggers: string[];
  classification_requires_review: boolean;

  decided_by: string | null;
  confidence_zone: string | null;
  contradiction_detected: boolean;
  l4_triggered: boolean;

  composition: DocumentCompositionMeta | null;
  segment_summary: ClassificationSegmentSummaryResponse | null;

  updated_at: string;
}

export interface ClassificationInvestigationListResponse {
  summary: ClassificationInvestigationSummary;
  items: ClassificationInvestigationRow[];

  total: number;
  page: number;
  per_page: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface ClassificationInvestigationDetailResponse {
  document_id: string;
  filename: string;
  folder_path: string | null;
  status: string;

  doc_type: string | null;
  classification_level: string | null;
  classification_confidence: number | null;
  applicable_triggers: string[];
  classification_requires_review: boolean;

  language: string | null;
  jurisdiction_guess: string | null;

  decided_by: string | null;
  confidence_zone: string | null;
  contradiction_detected: boolean;
  l4_triggered: boolean;

  levels_tried: string[];
  candidates: ClassificationCandidateResponse[];
  level_results: ClassificationLevelResultResponse[];
  voting: ClassificationVotingResponse | null;
  decision_summary: Record<string, unknown>;

  composition: DocumentCompositionMeta | null;
  segment_summary: ClassificationSegmentSummaryResponse | null;

  raw_result: Record<string, unknown>;
  raw_details: Record<string, unknown>;
}


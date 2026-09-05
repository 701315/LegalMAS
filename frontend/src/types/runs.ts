// =============================================================
// src/types/runs.ts
// Run, analysis run statuses, and SSE progress types.
// =============================================================

import type { ClassificationStats } from "./documents";

/**
 * Statuses synchronized with backend Run.status:
 * - pending  — Run created, but pipeline has not been started yet;
 * - running  — orchestrator scheduled tasks, analysis is in progress;
 * - completed — all documents completed checks successfully;
 * - completed_with_errors — analysis finished, but some documents are FAILED/QUARANTINE;
 * - failed   — critical Run error (configuration/infrastructure);
 * - cancelled — reserved for Run cancellation scenarios from the UI.
 */
export type RunStatus =
  | "pending"
  | "running"
  | "completed"
  | "completed_with_errors"
  | "failed"
  | "cancelled";

export type RunProfile = "core" | "full" | "max";

export type RunChecksMode =
  | "global_only"
  | "doc_type_only"
  | "global_and_doc_type";

/**
 * Input payload to start a new analysis run.
 *
 * Playbook and model_config are fetched from the deal settings (Deal.playbook_version_id),
 * so they do not need to be passed in the request body.
 */
export interface RunCreateInput {
  /** Run profile: core / full / max */
  profile?: RunProfile;

  /** Checks scope: global_only / doc_type_only / global_and_doc_type */
  checks_mode?: RunChecksMode;

  /** If true, HybridClassifier will rerun for all documents */
  force_reclassify?: boolean;
}

/**
 * Analysis run information.
 *
 * Used for:
 *  - status badges in the Overview tab;
 *  - checks progress bar;
 *  - last Run summary inside the deal card;
 *  - DD Grid (filtering by checks scope and strategy).
 */
export interface Run {
  id: string;
  deal_id: string;
  status: RunStatus;

  /** Run profile: core / full / max */
  profile: RunProfile;

  /**
   * Checks scope for the Run:
   *  - "global_only"
   *  - "doc_type_only"
   *  - "global_and_doc_type"
   */
  checks_mode: RunChecksMode;

  /**
   * Pipeline rerun strategy:
   *  - REUSE_STRUCTURE — reuse pre-computed document structure tree;
   *  - FULL_RERUN      — recalculate everything from scratch;
   */
  pipeline_strategy: string;

  /** Total number of checks to run across documents */
  total_checks: number;

  /** Completed checks count */
  completed_checks: number;

  /** Whether the run has FAILED/QUARANTINE documents */
  has_errors?: boolean;

  /** Number of documents in FAILED status */
  failed_docs_count?: number;

  /** Number of documents in QUARANTINE status */
  quarantine_docs_count?: number;

  /** Run started/completed timestamps (ISO8601 strings) */
  started_at?: string;
  completed_at?: string;

  /**
   * Run-level error details (not document-specific).
   * Schema aligned with backend Run.error_details.
   */
  error_details?: Record<string, unknown>;

  /** Optional classification stats — returned if include_classification_stats=true */
  classification_stats?: ClassificationStats;
}

/** Progress event received via SSE during analysis */
export interface ProgressEvent {
  run_id: string;
  status: RunStatus;

  /** Current active contract fields */
  completed_checks?: number;
  total_checks?: number;

  /** Backwards compatibility with older payloads */
  completed?: number;
  total?: number;

  current_document?: string;
  error?: string;
}

// =============================================================
// Pipeline progress types
// Used for detailed rendering of pipeline stages
// inside the project overview tab.
// =============================================================

/**
 * Status of a single product-level pipeline step.
 * pending               — not started yet
 * running               — currently running
 * completed             — completed successfully
 * completed_with_errors — completed but some documents have errors
 * failed                — completed with a terminal failure
 */
export type PipelineStepStatus =
  | "pending"
  | "running"
  | "completed"
  | "completed_with_errors"
  | "failed";

/**
 * Status of a technical substep inside a pipeline step.
 * planned   — planned, not started yet
 * running   — currently running
 * completed — completed successfully
 * failed    — failed with an error
 * cancelled — cancelled
 */
export type PipelineSubstepStatus =
  | "planned"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

/**
 * Type of live progress inside a long-running step.
 * legal_units — enrichment of semantic blocks
 * segments    — segment classification
 * checks      — DD checks execution
 * documents   — general document progress
 */
export type PipelineSubProgressKind =
  | "legal_units"
  | "segments"
  | "checks"
  | "documents";

/**
 * Live progress state inside a pipeline step (from progress_details in DB).
 */
export interface PipelineSubProgress {
  kind: PipelineSubProgressKind;
  current: number;
  total: number;
  total_units_in_document?: number;
  current_document_id?: string;
  current_document_name?: string;
  current_segment_id?: string;
  current_segment_title?: string;
  current_unit_label?: string;
  updated_at?: string;
}

/**
 * A single technical substep inside a product-level step.
 * Example: workers.extract_document inside "Document Preprocessing".
 */
export interface PipelineSubstep {
  code: string;
  title: string;
  status: PipelineSubstepStatus;
  started_at?: string;
  finished_at?: string;
  duration_seconds?: number;
  error_message?: string;
}

/**
 * A single product-level pipeline step visible to the user.
 * Example: "Document Preprocessing", "Semantic Enrichment".
 */
export interface PipelineStep {
  code: string;
  title: string;
  status: PipelineStepStatus;
  documents_total: number;
  documents_completed: number;
  documents_running: number;
  documents_failed: number;
  started_at?: string;
  finished_at?: string;
  duration_seconds?: number;
  message?: string;
  error_message?: string;
  substeps: PipelineSubstep[];
  sub_progress?: PipelineSubProgress | null;
}

/**
 * Detailed user-facing pipeline progress for a run.
 * Returned by GET /api/v1/runs/{run_id}/progress.
 *
 * Shows full document pipeline progression:
 * preparation → structure → classification → enrichment → checks → finalization.
 */
export interface RunPipelineProgress {
  run_id: string;
  deal_id: string;
  run_status: RunStatus;
  started_at?: string;
  completed_at?: string;
  elapsed_seconds?: number;
  last_activity_at?: string;
  is_stale: boolean;
  stale_threshold_minutes: number;
  documents_total: number;
  documents_failed: number;
  documents_quarantine: number;
  current_step_code?: string;
  current_step_title?: string;
  active_step_codes: string[];
  steps: PipelineStep[];
}



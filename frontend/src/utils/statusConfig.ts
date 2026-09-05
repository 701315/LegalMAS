// =============================================================
// src/utils/statusConfig.ts
// Unified configuration for displaying document and run statuses in UI.
//
// Module purpose:
// - Single source of truth for all labels, colors, and human-readable stage names;
// - Ensures all components (tables, cards, tooltips) use consistent
//   labels and colors instead of inventing their own.
//
// Colors are semantic — map to your design system tokens (primary/success/warning/error).
// =============================================================

import type {
  DocumentStatus,
  RunStatus,
  ProcessingErrorDetails,
} from "../types";

// Color as simple string — later mapped to design class/token.
export type StatusColor = "default" | "info" | "success" | "warning" | "error";

export interface DocumentStatusConfig {
  label: string; // Backward compatibility fallback (English canonical)
  labelKey: string;
  color: StatusColor;
  tooltip?: string; // Backward compatibility fallback
  tooltipKey?: string;
  description?: string; // Backward compatibility fallback
  descriptionKey?: string;
}

export interface RunStatusConfig {
  label: string; // Backward compatibility fallback (English canonical)
  labelKey: string;
  color: StatusColor;
}

/** Mapping of document status to label, i18n key, and color. */
export const DOCUMENT_STATUS_CONFIG: Record<DocumentStatus, DocumentStatusConfig> = {
  pending: {
    label: "Pending",
    labelKey: "pipeline:documentStatuses.pending",
    color: "default",
  },
  extracting: {
    label: "Extracting text",
    labelKey: "pipeline:documentStatuses.extracting",
    color: "info",
  },
  extracted: {
    label: "Text extracted",
    labelKey: "pipeline:documentStatuses.extracted",
    color: "info",
  },
  sanitized: {
    label: "PII redacted",
    labelKey: "pipeline:documentStatuses.sanitized",
    color: "info",
  },
  structured: {
    label: "Structure built",
    labelKey: "pipeline:documentStatuses.structured",
    color: "info",
  },
  classified: {
    label: "Classified",
    labelKey: "pipeline:documentStatuses.classified",
    color: "info",
  },
  analyzing: {
    label: "Running checks",
    labelKey: "pipeline:documentStatuses.analyzing",
    color: "info",
  },
  completed: {
    label: "Checks complete",
    labelKey: "pipeline:documentStatuses.completed",
    color: "success",
  },
  quarantine: {
    label: "Quarantine (review needed)",
    labelKey: "pipeline:documentStatuses.quarantine",
    color: "warning",
  },
  failed: {
    label: "Processing error",
    labelKey: "pipeline:documentStatuses.failed",
    color: "error",
  },
  duplicate: {
    label: "Duplicate",
    labelKey: "pipeline:documentStatuses.duplicate",
    color: "default",
  },
  language_selection_required: {
    label: "Language selection required",
    labelKey: "pipeline:documentStatuses.language_selection_required.label",
    color: "warning",
    tooltip:
      "Document upload is complete. Further processing for multilingual documents is paused until the primary analysis language is selected. Russian is selected by default.",
    tooltipKey: "pipeline:documentStatuses.language_selection_required.tooltip",
    description:
      "Document upload is complete. For documents with multiple detected languages, further processing — monolingual conversion to the selected primary language, as well as extraction, sanitization, structure building, chunking, and classification — will not continue until the primary analysis language is chosen. Russian is set by default.",
    descriptionKey: "pipeline:documentStatuses.language_selection_required.description",
  },
};

/** Mapping of Run status to label, i18n key, and color. */
export const RUN_STATUS_CONFIG: Record<RunStatus, RunStatusConfig> = {
  pending: {
    label: "Pending",
    labelKey: "pipeline:runStatuses.pending",
    color: "default",
  },
  running: {
    label: "Running",
    labelKey: "pipeline:runStatuses.running",
    color: "info",
  },
  completed: {
    label: "Completed",
    labelKey: "pipeline:runStatuses.completed",
    color: "success",
  },
  completed_with_errors: {
    label: "Completed with errors",
    labelKey: "pipeline:runStatuses.completed_with_errors",
    color: "warning",
  },
  failed: {
    label: "Failed",
    labelKey: "pipeline:runStatuses.failed",
    color: "error",
  },
  cancelled: {
    label: "Cancelled",
    labelKey: "pipeline:runStatuses.cancelled",
    color: "default",
  },
};

/** Human-readable pipeline stage labels from processing_error_details.stage (English canonical). */
const STAGE_LABELS: Record<string, string> = {
  import: "File import",
  extract: "Text extraction",
  pii: "PII redaction",
  structure: "Structure building",
  classify: "Classification",
  checks: "Playbook checks",
  export: "Report generation",
};

/**
 * Returns human-readable error stage label from processing_error_details.
 *
 * If stage is unknown or missing — returns generic text.
 * Supports i18next TFunction if provided.
 */
export function getErrorStageLabel(
  details?: ProcessingErrorDetails | null,
  tFn?: (key: string, options?: Record<string, unknown>) => string,
): string {
  if (!details || !details.stage) {
    return tFn ? tFn("pipeline:stages.unknown") : "Unknown stage";
  }
  if (tFn) {
    const key = `pipeline:stages.${details.stage}`;
    const localized = tFn(key, { defaultValue: "" });
    if (localized) return localized;
  }
  return STAGE_LABELS[details.stage] ?? details.stage;
}



// =============================================================
// src/pages/tabs/dd-grid-v1/ddGridV1.drawer.ts
// Pure helpers для DD Grid V1 drawer.
//
// i18n: канонический English fallback + динамический tFn.
// =============================================================

import type {
  DDGridV1DetectionLevel,
  DDGridV1DrawerContentDTO,
  DDGridV1DrawerFieldDTO,
  DDGridV1DrawerQcStatus,
} from "../../../types/dealReview";

import {
  classifyDDGridV1LocationAvailability,
  formatDDGridV1CellText,
  getDDGridV1CellTone,
  type DDGridV1CellTone,
} from "./ddGridV1.formatters";

import type { DDGridV1LocationAvailability } from "./ddGridV1.types";

type TFunction = (key: string, options?: Record<string, unknown>) => string;

// -------------------------------------------------------------
// i18n: Backend EN canonical → i18n key mapping
// -------------------------------------------------------------

/**
 * Maps EN canonical reason strings from _PLAN_STATUS_TO_REASON
 * to i18n keys in ddGrid.planStatusReasons.
 */
const PLAN_REASON_I18N: Record<string, string> = {
  "Check is planned and awaiting execution.": "planStatusReasons.planned",
  "Check is currently executing.": "planStatusReasons.started",
  "Error occurred during check execution.": "planStatusReasons.failed",
  "Check execution timed out.": "planStatusReasons.timeout",
  "Check was cancelled.": "planStatusReasons.cancelled",
  "Check skipped (result accounted for in another plan).": "planStatusReasons.skipped",
  "Result is expected.": "planStatusReasons.succeeded",
  "Unknown check status.": "planStatusReasons.unknown",
};

/**
 * Localizes a drawer reason string if it matches a known EN canonical token.
 * Real document data (Russian text from metadata) passes through unchanged.
 */
export function localizeDrawerReason(
  reason: string | null,
  tFn?: TFunction,
): string | null {
  if (!reason || !tFn) return reason;
  const key = PLAN_REASON_I18N[reason];
  return key ? tFn(key) : reason;
}

// -------------------------------------------------------------
// Reason precedence
// -------------------------------------------------------------

export type DDGridV1PresentationTone =
  | "success"
  | "warning"
  | "error"
  | "muted";

export interface DDGridV1PresentationInfo {
  labelKey: string;
  tone: DDGridV1PresentationTone;
  interpolation?: Record<string, string>;
}

/**
 * Builds drawer-only presentation provenance UI.
 *
 * This function never decides which result text to render. Backend
 * read-side selection already validates locale, content version,
 * source hash, and lifecycle status before returning drawer content.
 */
export function resolveDDGridV1PresentationInfo(
  drawer: DDGridV1DrawerContentDTO | null,
): DDGridV1PresentationInfo | null {
  if (!drawer || !drawer.presentation_status) {
    return null;
  }

  const locale = (drawer.output_locale || drawer.presentation_locale)?.trim();

  if (drawer.presentation_is_fallback === false) {
    return {
      labelKey: "drawer.presentation.localized",
      tone: "success",
      interpolation: locale ? { locale } : undefined,
    };
  }

  switch (drawer.presentation_status.trim().toLowerCase()) {
    case "pending":
    case "processing":
      return {
        labelKey: "drawer.presentation.fallbackProcessing",
        tone: "warning",
      };
    case "failed":
      return {
        labelKey: "drawer.presentation.fallbackFailed",
        tone: "error",
      };
    case "stale":
      return {
        labelKey: "drawer.presentation.fallbackStale",
        tone: "warning",
      };
    case "missing":
      return {
        labelKey: "drawer.presentation.fallbackMissing",
        tone: "muted",
      };
    default:
      return {
        labelKey: "drawer.presentation.fallbackCanonical",
        tone: "muted",
      };
  }
}

export type DDGridV1ReasonSource =
  | "reason"
  | "review_message"
  | "display_text"
  | "none";

export interface DDGridV1ResolvedReason {
  text: string | null;
  source: DDGridV1ReasonSource;
}

function firstNonEmpty(...values: Array<string | null | undefined>): string | null {
  for (const v of values) {
    if (typeof v === "string" && v.trim().length > 0) {
      return v;
    }
  }
  return null;
}

export function resolveDDGridV1DrawerReason(
  drawer: DDGridV1DrawerContentDTO | null,
  tFn?: TFunction,
): DDGridV1ResolvedReason {
  if (!drawer) return { text: null, source: "none" };

  const reason = firstNonEmpty(drawer.reason);
  if (reason) return { text: localizeDrawerReason(reason, tFn), source: "reason" };

  const reviewMessage = firstNonEmpty(drawer.review_message);
  if (reviewMessage) return { text: reviewMessage, source: "review_message" };

  const displayText = firstNonEmpty(drawer.display_text);
  if (displayText) return { text: displayText, source: "display_text" };

  return { text: null, source: "none" };
}

// -------------------------------------------------------------
// Field view model
// -------------------------------------------------------------

export interface DDGridV1DrawerFieldView {
  key: string;
  label: string;
  fieldName: string;
  columnId: string;
  cellState: DDGridV1DrawerFieldDTO["cell_state"];
  tone: DDGridV1CellTone;
  displayText: string;
  locationAvailability: DDGridV1LocationAvailability;
  raw: DDGridV1DrawerFieldDTO;
}

export function buildDDGridV1DrawerFieldViews(
  drawer: DDGridV1DrawerContentDTO | null,
  tFn?: TFunction,
): DDGridV1DrawerFieldView[] {
  if (!drawer) return [];

  return (drawer.fields ?? []).map((field, index) => {
    const availability = classifyDDGridV1LocationAvailability({
      location_source: field.location_source,
      anchor_method: field.anchor_method ?? null,
    });

    const syntheticColumn = {
      column_id: field.column_id,
      check_id: drawer.check_id,
      label: field.label,
      format: "text" as const,
      fallback_display: "—",
      display_order: 0,
      enum_labels: {},
      unit: null,
    };

    const displayText = formatDDGridV1CellText(
      field.cell_state,
      field.cell_state === "defined"
        ? {
            cell_state: field.cell_state,
            display_value: field.display_value,
            raw_value: field.raw_value,
            location_source: field.location_source,
            location_clause_ref: field.location_clause_ref,
            location_clause_uid: field.location_clause_uid,
            location_page: field.location_page,
            location_confidence: field.location_confidence,
            // ── B5: anchor metadata ──────────────────────────────────────
            anchor_method: field.anchor_method,
            anchor_confidence: field.anchor_confidence,
            anchor_stale: field.anchor_stale,
            layout_element_ids: field.layout_element_ids,
            // ── Risk-aware DD Grid (COC pilot) ──────────────────────────
            cell_risk_level: field.cell_risk_level,
            top_risk_field: field.top_risk_field,
            top_risk_value: field.top_risk_value,
            top_risk_display: field.top_risk_display,
          }
        : null,
      syntheticColumn,
      tFn, // 🌟 Пробрасываем tFn в форматтер
    );

    return {
      key: `${field.column_id}#${index}`,
      label: field.label,
      fieldName: field.field_name,
      columnId: field.column_id,
      cellState: field.cell_state,
      tone: getDDGridV1CellTone(field.cell_state),
      displayText,
      locationAvailability: availability,
      raw: field,
    };
  });
}

// -------------------------------------------------------------
// Evidence
// -------------------------------------------------------------

export function normalizeDDGridV1EvidenceItems(
  drawer: DDGridV1DrawerContentDTO | null,
): string[] {
  if (!drawer) return [];
  const items = drawer.evidence_items ?? [];
  const out: string[] = [];
  for (const item of items) {
    if (typeof item === "string" && item.trim().length > 0) {
      out.push(item.trim());
    }
  }
  return out;
}

// -------------------------------------------------------------
// Detection level
// -------------------------------------------------------------

export interface DDGridV1DetectionLevelInfo {
  level: DDGridV1DetectionLevel | null;
  badge: string | null;
  label: string;
}

const DETECTION_LEVEL_FALLBACKS: Record<DDGridV1DetectionLevel, string> = {
  L1: "Pattern",
  L2: "LLM",
  L3: "RAG + LLM",
  L4: "Manual review",
};

export function resolveDDGridV1DetectionLevel(
  drawer: DDGridV1DrawerContentDTO | null,
  tFn?: TFunction,
): DDGridV1DetectionLevelInfo {
  const level = drawer?.detection_level ?? null;
  if (!level) {
    return {
      level: null,
      badge: null,
      label: tFn ? tFn("detectionLevels.undefined") : "Not determined",
    };
  }
  return {
    level,
    badge: level,
    label: tFn
      ? tFn(`detectionLevels.${level}`)
      : (DETECTION_LEVEL_FALLBACKS[level] ?? level),
  };
}

// -------------------------------------------------------------
// Confidence
// -------------------------------------------------------------

export type DDGridV1ConfidenceTier = "high" | "medium" | "low";

export interface DDGridV1ConfidenceInfo {
  value: number | null;
  tier: DDGridV1ConfidenceTier | null;
  formatted: string | null;
}

export function resolveDDGridV1Confidence(
  drawer: DDGridV1DrawerContentDTO | null,
): DDGridV1ConfidenceInfo {
  const value = drawer?.confidence ?? null;
  if (value === null || typeof value !== "number") {
    return { value: null, tier: null, formatted: null };
  }

  const tier: DDGridV1ConfidenceTier =
    value >= 0.8 ? "high" : value >= 0.6 ? "medium" : "low";

  return {
    value,
    tier,
    formatted: value.toFixed(2),
  };
}

// -------------------------------------------------------------
// Quality flags
// -------------------------------------------------------------

const QUALITY_FLAG_FALLBACKS: Record<string, string> = {
  structure_degraded: "Structure degraded",
  llm_fallback_used: "Fallback model",
  retry_used: "Retry attempt",
  partial_result: "Partial result",
  confidence_below_threshold: "Low confidence",
  missing_provenance: "No provenance",
};

export interface DDGridV1QualityFlagItem {
  key: string;
  label: string;
}

export function resolveDDGridV1QualityFlags(
  drawer: DDGridV1DrawerContentDTO | null,
  tFn?: TFunction,
): DDGridV1QualityFlagItem[] {
  const flags = drawer?.quality_flags;
  if (!flags || typeof flags !== "object") return [];

  return Object.keys(flags).map((key) => ({
    key,
    label: tFn
      ? tFn(`qualityFlags.${key}`)
      : (QUALITY_FLAG_FALLBACKS[key] ?? key.replace(/_/g, " ")),
  }));
}

// -------------------------------------------------------------
// QC Audit Trail
// -------------------------------------------------------------

export interface DDGridV1QcAuditInfo {
  status: DDGridV1DrawerQcStatus | null;
  editableStatus: DDGridV1DrawerQcStatus;
  by: string | null;
  at: string | null;
  atFormatted: string | null;
  comment: string | null;
  hasBeenActioned: boolean;
}

function formatISODate(iso: string | null, locale: string): string | null {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleString(locale, {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function resolveDDGridV1QcAuditInfo(
  drawer: DDGridV1DrawerContentDTO | null,
  locale?: string,
): DDGridV1QcAuditInfo {
  const status = drawer?.qc_status ?? null;
  const editableStatus: DDGridV1DrawerQcStatus = status ?? "pending";

  return {
    status,
    editableStatus,
    by: drawer?.qc_by ?? null,
    at: drawer?.qc_at ?? null,
    atFormatted: formatISODate(drawer?.qc_at ?? null, locale ?? "en-US"),
    comment: drawer?.qc_comment ?? null,
    hasBeenActioned: !!status && status !== "pending",
  };
}

// -------------------------------------------------------------
// Observability
// -------------------------------------------------------------

export interface DDGridV1ObservabilityInfo {
  agentName: string | null;
  modelVersion: string | null;
  executionTimeMs: number | null;
  executionTimeFormatted: string | null;
  retryAttempts: number | null;
  inputTokens: number | null;
  outputTokens: number | null;
  hasAnyData: boolean;
}

function formatMs(ms: number | null): string | null {
  if (ms === null || ms === undefined) return null;
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

export function resolveDDGridV1Observability(
  drawer: DDGridV1DrawerContentDTO | null,
): DDGridV1ObservabilityInfo {
  const agentName = drawer?.agent_name ?? null;
  const modelVersion = drawer?.model_version ?? null;
  const executionTimeMs = drawer?.execution_time_ms ?? null;
  const retryAttempts = drawer?.retry_attempts ?? null;
  const inputTokens = drawer?.input_tokens ?? null;
  const outputTokens = drawer?.output_tokens ?? null;

  const hasAnyData =
    !!agentName ||
    !!modelVersion ||
    executionTimeMs !== null ||
    retryAttempts !== null ||
    inputTokens !== null ||
    outputTokens !== null;

  return {
    agentName,
    modelVersion,
    executionTimeMs,
    executionTimeFormatted: formatMs(executionTimeMs),
    retryAttempts,
    inputTokens,
    outputTokens,
    hasAnyData,
  };
}



// =============================================================
// src/pages/tabs/documents/utils.ts
// =============================================================

import type { DocumentListItem } from "../../../types";
import {
  DOCUMENT_STATUS_CONFIG,
  getErrorStageLabel,
} from "../../../utils/statusConfig";
import { getCompositionCellValue } from "../../../utils/compositionHelpers";

type TranslateFn = (key: string, options?: Record<string, unknown>) => string;

export function formatRiskLevel(
  risk: string | null | undefined,
  tFn?: TranslateFn,
): string {
  if (!risk) return "";
  const key = `documentsTab.utils.risk.${risk}`;
  if (tFn) {
    const translated = tFn(key, { defaultValue: risk });
    return typeof translated === "string" ? translated : risk;
  }
  // Canonical English defaults (source copy)
  switch (risk) {
    case "low":
      return "Low";
    case "medium":
      return "Medium";
    case "high":
      return "High";
    case "critical":
      return "Critical";
    default:
      return risk;
  }
}

export function formatDateTime(
  value: string | undefined | null,
  locale?: string,
): string {
  if (!value) return "";
  try {
    return new Date(value).toLocaleString(locale ?? undefined);
  } catch {
    return value;
  }
}

export function hasProcessingError(doc: DocumentListItem): boolean {
  if (doc.status === "failed" || doc.status === "quarantine") return true;
  const details = doc.processing_error_details;
  if (!details) return false;
  return Boolean(details.message || details.type);
}

/**
 * Document count noun for UI subtitles.
 * Prefer i18next pluralization via tFn; English defaults when tFn omitted.
 */
export function getDocumentsCountLabel(
  count: number,
  tFn?: TranslateFn,
): string {
  if (tFn) {
    return String(
      tFn("documentsTab.utils.documentsCount", {
        count,
        defaultValue: count === 1 ? "document" : "documents",
      }),
    );
  }
  return count === 1 ? "document" : "documents";
}

export function resolveDocumentCellValue(
  colId: string,
  colField: string,
  doc: DocumentListItem,
  options?: { tFn?: TranslateFn; locale?: string },
): unknown {
  const tFn = options?.tFn;
  const locale = options?.locale;

  if (
    colId === "composition_type" ||
    colId === "segment_count" ||
    colId === "primary_segment_label" ||
    colId === "is_composite_file"
  ) {
    return getCompositionCellValue(colId as any, doc);
  }

  switch (colField) {
    case "applicable_triggers_count":
      return doc.applicable_triggers?.length ?? 0;

    case "status": {
      const baseLabel =
        doc.status && DOCUMENT_STATUS_CONFIG[doc.status]
          ? DOCUMENT_STATUS_CONFIG[doc.status].label
          : doc.status || "";

      return hasProcessingError(doc) ? `${baseLabel} ⚠` : baseLabel;
    }

    case "risk_level":
      return formatRiskLevel(doc.risk_level, tFn);

    case "created_at":
      return formatDateTime(doc.created_at, locale);

    case "updated_at":
      return formatDateTime(doc.updated_at, locale);

    default: {
      type DocumentKey = keyof DocumentListItem;
      return doc[colField as DocumentKey];
    }
  }
}

export function resolveDocumentCellTitle(
  colField: string,
  value: unknown,
  doc: DocumentListItem,
  options?: { tFn?: TranslateFn },
): string | undefined {
  const tFn = options?.tFn;
  const unknownStage = tFn
    ? String(
        tFn("documentsTab.utils.unknownStage", {
          defaultValue: "Unknown stage",
        }),
      )
    : "Unknown stage";

  if (colField === "status" && hasProcessingError(doc)) {
    const details = doc.processing_error_details;
    const stageLabel = getErrorStageLabel(details);
    const message = details?.message;

    // Compare against both EN canonical and legacy RU hardcoded stage label
    const isUnknown =
      !stageLabel ||
      stageLabel === unknownStage ||
      stageLabel === "Неизвестная стадия" ||
      stageLabel === "Unknown stage";

    if (message && !isUnknown) {
      return `${stageLabel}: ${message}`;
    }

    if (message) return message;

    if (typeof value === "string") return value;

    return undefined;
  }

  if (colField === "status" && doc.status) {
    return (
      DOCUMENT_STATUS_CONFIG[doc.status]?.tooltip ??
      (typeof value === "string" ? value : undefined)
    );
  }

  if (typeof value === "string") return value;

  return undefined;
}



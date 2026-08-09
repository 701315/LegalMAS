// =============================================================
// src/pages/tabs/documents/utils.ts
// =============================================================

import type { DocumentListItem } from "../../../types";
import {
  DOCUMENT_STATUS_CONFIG,
  getErrorStageLabel,
} from "../../../utils/statusConfig";
import { getCompositionCellValue } from "../../../utils/compositionHelpers";

export function formatRiskLevel(risk: string | null | undefined): string {
  if (!risk) return "";
  switch (risk) {
    case "low":
      return "Низкий";
    case "medium":
      return "Средний";
    case "high":
      return "Высокий";
    case "critical":
      return "Критический";
    default:
      return risk;
  }
}

export function formatDateTime(value: string | undefined | null): string {
  if (!value) return "";
  try {
    return new Date(value).toLocaleString();
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

export function getDocumentsCountLabel(count: number): string {
  const mod10 = count % 10;
  const mod100 = count % 100;

  if (mod10 === 1 && mod100 !== 11) return "документ";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20))
    return "документа";

  return "документов";
}

export function resolveDocumentCellValue(
  colId: string,
  colField: string,
  doc: DocumentListItem,
): unknown {
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

      return hasProcessingError(doc)
        ? `${baseLabel} ⚠`
        : baseLabel;
    }

    case "risk_level":
      return formatRiskLevel(doc.risk_level);

    case "created_at":
      return formatDateTime(doc.created_at);

    case "updated_at":
      return formatDateTime(doc.updated_at);

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
): string | undefined {
  if (colField === "status" && hasProcessingError(doc)) {
    const details = doc.processing_error_details;
    const stageLabel = getErrorStageLabel(details);
    const message = details?.message;

    if (message && stageLabel !== "Неизвестная стадия") {
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



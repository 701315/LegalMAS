// =============================================================
// src/pages/tabs/grid/gridTab.utils.ts
// Вспомогательные утилиты для вкладки Grid.
//
// i18n: канонический English fallback + динамический tFn.
// =============================================================

import type { DDMatrixResponseDTO } from "../../../types/dealReview";
import type { NormalizedOrigin } from "./gridTab.types";

export function normalizeOrigin(
  rawOrigin: string | null | undefined,
  originType?: "global" | "doctype" | "custom",
): NormalizedOrigin {
  if (originType === "global") return "global";
  if (originType === "doctype") return "doctype";

  if (!rawOrigin) {
    return "other";
  }

  const raw = rawOrigin.toString();
  const upper = raw.toUpperCase();

  if (
    upper === "GLOBAL_PLAYBOOK" ||
    raw === "global_playbook" ||
    raw === "project_playbook"
  ) {
    return "global";
  }

  if (upper === "DOCUMENT_TYPE") {
    return "doctype";
  }

  return "other";
}

export function getReviewSummary(matrix: DDMatrixResponseDTO | undefined) {
  if (!matrix) {
    return {
      documentCount: 0,
      checkCount: 0,
      criticalCount: 0,
      highCount: 0,
      mediumCount: 0,
      unclearCount: 0,
      passCount: 0,
    };
  }

  return {
    documentCount: matrix.total_documents ?? matrix.documents.length,
    checkCount: matrix.total_checks ?? matrix.checks.length,
    criticalCount: matrix.severity_counts?.critical ?? 0,
    highCount: matrix.severity_counts?.high ?? 0,
    mediumCount: matrix.severity_counts?.medium ?? 0,
    unclearCount: matrix.severity_counts?.unclear ?? 0,
    passCount: matrix.severity_counts?.pass ?? 0,
  };
}

export function humanChecksMode(
  mode?: string | null,
  tFn?: (key: string) => string,
): string | null {
  if (!mode) return null;

  if (tFn) {
    if (mode === "global_and_doc_type") return tFn("checksMode.global_and_doc_type");
    if (mode === "global_only") return tFn("checksMode.global_only");
    if (mode === "doc_type_only") return tFn("checksMode.doc_type_only");
  } else {
    // Canonical English default fallback
    if (mode === "global_and_doc_type") return "Playbook + document types";
    if (mode === "global_only") return "Playbook only";
    if (mode === "doc_type_only") return "Document types only";
  }

  return mode;
}

export function toExportChecksMode(
  mode?: string | null,
): "global_only" | "doc_type_only" | "global_and_doc_type" | undefined {
  if (
    mode === "global_only" ||
    mode === "doc_type_only" ||
    mode === "global_and_doc_type"
  ) {
    return mode;
  }

  return undefined;
}



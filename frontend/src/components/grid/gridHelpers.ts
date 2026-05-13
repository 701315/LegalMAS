// =============================================================
// src/components/grid/gridHelpers.ts
// Pure helpers for tooltips, labels and selection
// =============================================================

import type { SelectionChangedEvent } from "ag-grid-community";

import type { CheckResult } from "../../types";
import type { MatrixRow } from "./gridTypes";

function getLegacyPageInfo(result: CheckResult): {
  page: number | null;
  clauseUid: string | null;
} {
  const rawPage =
    (result as CheckResult & {
      page?: number | string | null;
      page_num?: number | string | null;
      source_page?: number | string | null;
      metadata?: {
        page?: number | string | null;
        page_num?: number | string | null;
        source_page?: number | string | null;
        clause_uid?: string | null;
        clauseUid?: string | null;
      } | null;
    }).page ??
    (result as CheckResult & { page_num?: number | string | null }).page_num ??
    (result as CheckResult & { source_page?: number | string | null })
      .source_page ??
    (result as CheckResult & {
      metadata?: {
        page?: number | string | null;
        page_num?: number | string | null;
        source_page?: number | string | null;
      } | null;
    }).metadata?.page ??
    (result as CheckResult & {
      metadata?: { page_num?: number | string | null } | null;
    }).metadata?.page_num ??
    (result as CheckResult & {
      metadata?: { source_page?: number | string | null } | null;
    }).metadata?.source_page;

  const rawClauseUid =
    (result as CheckResult & {
      clause_uid?: string | null;
      clauseUid?: string | null;
      metadata?: {
        clause_uid?: string | null;
        clauseUid?: string | null;
      } | null;
    }).clause_uid ??
    (result as CheckResult & { clauseUid?: string | null }).clauseUid ??
    (result as CheckResult & {
      metadata?: {
        clause_uid?: string | null;
        clauseUid?: string | null;
      } | null;
    }).metadata?.clause_uid ??
    (result as CheckResult & {
      metadata?: { clauseUid?: string | null } | null;
    }).metadata?.clauseUid ??
    null;

  const parsedPage =
    rawPage == null || rawPage === ""
      ? null
      : Number.isFinite(Number(rawPage))
        ? Number(rawPage)
        : null;

  return {
    page: parsedPage,
    clauseUid: rawClauseUid ? String(rawClauseUid) : null,
  };
}

export function getMatrixResultLabel(result: CheckResult): string {
  if (result.result === "fail") {
    return result.severity
      ? `Идентифицирован (${result.severity})`
      : "Идентифицирован";
  }

  if (result.result === "unclear") {
    return "Требует внимания юриста";
  }

  return "Не найден";
}

export function getSelectedDocumentIds(
  event: SelectionChangedEvent<MatrixRow>,
): string[] {
  return event.api
    .getSelectedNodes()
    .map((node) => node.data?.documentId)
    .filter((value): value is string => Boolean(value));
}

export function getSelectedResultIds(
  event: SelectionChangedEvent<CheckResult>,
): string[] {
  return event.api
    .getSelectedNodes()
    .map((node) => node.data?.id)
    .filter((value): value is string => Boolean(value));
}

export function buildMatrixCellTooltip(result: CheckResult): string {
  const pageInfo = getLegacyPageInfo(result);
  const parts: string[] = [];

  if (result.value_text) {
    parts.push(result.value_text);
  }

  if (pageInfo.page != null || pageInfo.clauseUid) {
    parts.push(
      [
        pageInfo.page != null ? `стр. ${pageInfo.page}` : null,
        pageInfo.clauseUid || null,
      ]
        .filter(Boolean)
        .join(" · "),
    );
  }

  return parts.filter(Boolean).join("\n");
}

export function buildSeverityTooltip(result: CheckResult): string {
  const parts: string[] = [];

  if (result.severity) {
    parts.push(`Severity: ${result.severity}`);
  }
  if (result.result) {
    parts.push(`Result: ${result.result}`);
  }
  if (result.confidence != null) {
    parts.push(`Confidence: ${Math.round(result.confidence * 100)}%`);
  }

  return parts.filter(Boolean).join(" · ");
}



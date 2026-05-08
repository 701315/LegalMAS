// =============================================================
// src/components/grid/gridHelpers.ts
// Pure helpers for tooltips, labels and selection
// =============================================================

import type { SelectionChangedEvent } from "ag-grid-community";

import type { CheckResult } from "../../types";
import type { MatrixRow } from "./gridTypes";
import { getLegacyPageInfo } from "./gridLegacyHelpers";

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




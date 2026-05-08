// =============================================================
// src/pages/tabs/grid/gridTab.filters.ts
// Pure helpers для legacy-фильтрации и scope-выборок DD Grid.
// =============================================================

import type { CheckResult } from "../../../types";
import type { QuickFilter } from "../../../components/grid/GridFilters";
import type { GridScope } from "./gridTab.types";
import { normalizeOrigin } from "./gridTab.utils";

export function filterLegacyResults(params: {
  results: CheckResult[];
  searchText: string;
  quickFilter: QuickFilter;
}): CheckResult[] {
  const { results, searchText, quickFilter } = params;

  let filtered = results;

  if (searchText.trim()) {
    const lower = searchText.toLowerCase();

    filtered = filtered.filter(
      (r) =>
        r.document_name?.toLowerCase().includes(lower) ||
        r.check_name.toLowerCase().includes(lower),
    );
  }

  switch (quickFilter) {
    case "critical":
      filtered = filtered.filter((r) => r.severity === "critical");
      break;
    case "high":
      filtered = filtered.filter((r) => r.severity === "high");
      break;
    case "unclear":
      filtered = filtered.filter((r) => r.result === "unclear");
      break;
    case "no_qc":
      filtered = filtered.filter((r) => r.qc_status === "pending");
      break;
    case "important":
      filtered = filtered.filter(
        (r) =>
          (r.severity === "critical" || r.severity === "high") &&
          r.qc_status === "pending",
      );
      break;
    case "conditional":
      filtered = filtered.filter(
        (r) => r.conditional_check_triggered === true,
      );
      break;
    case "low_confidence":
      filtered = filtered.filter((r) => {
        const value = r.doc_classification_confidence;
        return value != null && value < 0.6;
      });
      break;
    case "all":
    default:
      break;
  }

  return filtered;
}

export function getGlobalResults(results: CheckResult[]): CheckResult[] {
  return results.filter(
    (r) => normalizeOrigin(r.origin, r.origin_type) === "global",
  );
}

export function getDoctypeResults(results: CheckResult[]): CheckResult[] {
  return results.filter(
    (r) => normalizeOrigin(r.origin, r.origin_type) === "doctype",
  );
}

export function getScopeDoctypes(results: CheckResult[]): string[] {
  return Array.from(
    new Set(
      results
        .map((r) => r.doc_type)
        .filter((value): value is string => Boolean(value)),
    ),
  ).sort();
}

export function getScopeResults(params: {
  gridScope: GridScope;
  filteredResults: CheckResult[];
  globalResults: CheckResult[];
  doctypeResults: CheckResult[];
  selectedScopeDocTypes: string[];
}): CheckResult[] {
  const {
    gridScope,
    filteredResults,
    globalResults,
    doctypeResults,
    selectedScopeDocTypes,
  } = params;

  let base: CheckResult[];

  switch (gridScope) {
    case "global":
      base = globalResults;
      break;
    case "doctype":
      base = doctypeResults;
      break;
    case "all":
    default:
      base = filteredResults;
      break;
  }

  if (gridScope === "doctype" && selectedScopeDocTypes.length > 0) {
    base = base.filter(
      (r) => Boolean(r.doc_type) && selectedScopeDocTypes.includes(r.doc_type!),
    );
  }

  return base;
}

export function getSelectedResults(
  results: CheckResult[],
  selectedIds: string[],
): CheckResult[] {
  return results.filter((r) => selectedIds.includes(r.id));
}



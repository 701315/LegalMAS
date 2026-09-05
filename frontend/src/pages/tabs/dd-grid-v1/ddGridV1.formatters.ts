// =============================================================
// src/pages/tabs/dd-grid-v1/ddGridV1.formatters.ts
// Pure formatters for DD Grid V1.
//
// Rules:
// - no hardcoded enum values ("yes", "present", "unclear");
// - formatters only build display strings based on contract
//   (format + cell_state + display_value / raw_value / enum_labels);
// - pure functions: same input → same output, no side-effects.
//
// i18n: Canonical English fallback + dynamic tFn.
// =============================================================

import type {
  DDGridV1CellState,
  DDGridV1CellValueDTO,
  DDGridV1ColumnDTO,
  DDGridV1LocationConfidence,
} from "../../../types/dealReview";

import type { DDGridV1LocationAvailability } from "./ddGridV1.types";

// -------------------------------------------------------------
// Helpers
// -------------------------------------------------------------

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

/**
 * Returns fallback_display of column or a dash.
 * Never throws.
 */
function safeFallback(column: DDGridV1ColumnDTO): string {
  return isNonEmptyString(column.fallback_display)
    ? column.fallback_display
    : "—";
}

/**
 * Appends unit to text with a space if unit is defined and non-empty.
 */
function appendUnit(value: string, unit: string | null): string {
  if (!isNonEmptyString(unit)) return value;
  return `${value} ${unit}`;
}

// -------------------------------------------------------------
// Cell text formatting
// -------------------------------------------------------------

/**
 * Returns prepared string for cell rendering.
 *
 * Never throws; returns safe fallback on unknown inputs.
 * Universal across 5 cell_states × 4 formats.
 */
export function formatDDGridV1CellText(
  cellState: DDGridV1CellState,
  cell: DDGridV1CellValueDTO | null,
  column: DDGridV1ColumnDTO,
  t?: (key: string) => string,
): string {
  if (cellState === "error") {
    return t ? t("drawer.cellStateLabels.error") : "⚠ Error";
  }
  if (cellState === "not_executed" || cellState === "not_defined") {
    if (cell && isNonEmptyString(cell.display_value)) {
      return cell.display_value;
    }
    return safeFallback(column);
  }

  // cellState === "defined"
  if (!cell) {
    return safeFallback(column);
  }

  switch (column.format) {
    case "text": {
      const base = isNonEmptyString(cell.display_value)
        ? cell.display_value
        : isNonEmptyString(cell.raw_value)
          ? cell.raw_value
          : safeFallback(column);
      return appendUnit(base, column.unit);
    }

    case "enum": {
      const raw = cell.raw_value;
      if (isNonEmptyString(raw) && column.enum_labels[raw]) {
        return column.enum_labels[raw];
      }
      if (isNonEmptyString(cell.display_value)) {
        return cell.display_value;
      }
      return safeFallback(column);
    }

    case "yes_no": {
      if (isNonEmptyString(cell.display_value)) {
        return cell.display_value;
      }
      const raw = cell.raw_value;
      if (isNonEmptyString(raw) && column.enum_labels[raw]) {
        return column.enum_labels[raw];
      }
      return safeFallback(column);
    }

    case "presence_only": {
      if (isNonEmptyString(cell.display_value)) {
        return cell.display_value;
      }
      const raw = cell.raw_value;
      if (isNonEmptyString(raw) && column.enum_labels[raw]) {
        return column.enum_labels[raw];
      }
      return safeFallback(column);
    }

    default: {
      return isNonEmptyString(cell.display_value)
        ? cell.display_value
        : safeFallback(column);
    }
  }
}

// -------------------------------------------------------------
// Location classification
// -------------------------------------------------------------

/**
 * Classifies location availability strictly by contract.
 */
export function classifyDDGridV1LocationAvailability(input: {
  has_location_fallback: boolean;
  location_clause_ref: string | null;
  location_page: number | null;
  location_confidence?: DDGridV1LocationConfidence;
}): DDGridV1LocationAvailability {
  const hasPointer =
    isNonEmptyString(input.location_clause_ref) ||
    typeof input.location_page === "number";

  if (!input.has_location_fallback && hasPointer) {
    return "exact";
  }
  if (input.has_location_fallback && hasPointer) {
    return "approximate";
  }
  return "unavailable";
}

// -------------------------------------------------------------
// Visual tone tokens
// -------------------------------------------------------------

export type DDGridV1CellTone =
  | "defined"
  | "muted"
  | "error";

export function getDDGridV1CellTone(state: DDGridV1CellState): DDGridV1CellTone {
  switch (state) {
    case "defined":
      return "defined";
    case "not_defined":
    case "not_executed":
      return "muted";
    case "error":
      return "error";
    default:
      return "muted";
  }
}



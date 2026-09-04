// =============================================================
// src/pages/tabs/dd-grid-v1/ddGridV1.formatters.ts
// Pure formatters для DD Grid V1.
//
// Правила:
// - никаких хардкодов конкретных enum values ("yes", "present", "unclear");
// - форматтер ничего не решает про семантику — только собирает display string
//   по контракту (format + cell_state + display_value / raw_value / enum_labels);
// - функции чистые: одинаковый input → одинаковый output, без побочных эффектов.
//
// i18n: канонический English fallback + динамический tFn.
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
 * Возвращает fallback_display колонки, либо тире.
 * Никогда не бросает.
 */
function safeFallback(column: DDGridV1ColumnDTO): string {
  return isNonEmptyString(column.fallback_display)
    ? column.fallback_display
    : "—";
}

/**
 * Прикладывает unit к тексту через пробел, если unit задан и не пустой.
 * Не форматирует "внутри" значения — просто concat.
 */
function appendUnit(value: string, unit: string | null): string {
  if (!isNonEmptyString(unit)) return value;
  return `${value} ${unit}`;
}

// -------------------------------------------------------------
// Cell text formatting
// -------------------------------------------------------------

/**
 * Возвращает готовую строку для рендера ячейки.
 *
 * Никогда не бросает; при любом непонятном входе возвращает
 * безопасный fallback (`fallback_display` колонки или "—").
 *
 * Универсально по 5 cell_state × 4 format.
 */
export function formatDDGridV1CellText(
  cellState: DDGridV1CellState,
  cell: DDGridV1CellValueDTO | null,
  column: DDGridV1ColumnDTO,
  t?: (key: string) => string,
): string {
  // Нестандартные состояния — не читаем raw/display, возвращаем fallback.
  if (cellState === "error") {
    return t ? t("drawer.cellStateLabels.error") : "⚠ Error";
  }
  if (cellState === "not_executed" || cellState === "not_defined") {
    // По контракту оба этих состояния используют fallback_display.
    // Если у ячейки уже есть display_value — используем его, иначе fallback.
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
 * Классифицирует доступность location строго по контракту.
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



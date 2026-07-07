// =============================================================
// src/pages/tabs/dd-grid-v1/ddGridV1.cellSummary.ts
// Строитель компактной сводки ячейки check-а для DD Grid V1 матрицы.
//
// Правила:
// - никаких хардкодов конкретных check_id / column_id / doc_type;
// - для каждого runtime column строим одну строку "Label: value";
// - value идёт через formatDDGridV1CellText — единственный источник
//   правды по форматированию (text / enum / yes_no / presence_only);
// - если для (document, column) ячейки нет и колонка привязана к
//   конкретному type_code, а doc_type документа не совпадает —
//   отображаем "н/о" (not_applicable) без хардкода конкретного типа;
// - если ячейки нет и колонка применима — отображаем fallback_display
//   колонки (not_executed).
// =============================================================

import { formatDDGridV1CellText } from "./ddGridV1.formatters";
import type { DDGridV1CellState } from "../../../types/dealReview";
import type {
  DDGridV1CheckNode,
  DDGridV1DerivedModel,
} from "./ddGridV1.types";

/**
 * View-модель одной пары "Label: value" для отображения в ячейке check-а.
 */
export interface DDGridV1CheckCellSummaryEntry {
  /** Стабильный ключ для React (учитывает индекс, т.к. column_id может дублироваться). */
  key: string;
  label: string;
  displayText: string;
  cellState: DDGridV1CellState;
}

/**
 * Полная сводка одного check-а для одного документа.
 */
export interface DDGridV1CheckCellSummary {
  checkId: string;
  checkName: string;
  entries: DDGridV1CheckCellSummaryEntry[];
  /**
   * true, если ВСЕ runtime columns этого check-а для документа
   * оказались not_applicable (например, check из doc_type ветки
   * для документа другого типа). Используется для визуального
   * приглушения ячейки.
   */
  allNotApplicable: boolean;
}

/**
 * Универсальный строитель сводки check-а для конкретного документа.
 *
 * Принимает CheckNode из V1 иерархии, поэтому позиция check-а в дереве
 * (global vs doc_type) не имеет значения — используется его локальный
 * список columns + applicableDocTypeCodes каждой колонки.
 */
export function buildDDGridV1CheckCellSummary(
  model: DDGridV1DerivedModel,
  documentId: string,
  docType: string,
  check: DDGridV1CheckNode,
): DDGridV1CheckCellSummary {
  const perDocCells = model.cellValues[documentId] ?? {};

  let notApplicableCount = 0;

  const entries: DDGridV1CheckCellSummaryEntry[] = check.columns.map(
    (runtimeCol, indexInCheck) => {
      const rawCell = perDocCells[runtimeCol.column.column_id] ?? null;

      let effectiveState: DDGridV1CellState;
      if (rawCell) {
        effectiveState = rawCell.cell_state;
      } else if (
        runtimeCol.applicableDocTypeCodes.length > 0 &&
        !runtimeCol.applicableDocTypeCodes.includes(docType)
      ) {
        effectiveState = "not_applicable";
      } else {
        effectiveState = "not_executed";
      }

      if (effectiveState === "not_applicable") {
        notApplicableCount += 1;
      }

      const displayText = formatDDGridV1CellText(
        effectiveState,
        rawCell,
        runtimeCol.column,
      );

      return {
        key: `${runtimeCol.column.column_id}#${indexInCheck}`,
        label: runtimeCol.column.label,
        displayText,
        cellState: effectiveState,
      };
    },
  );

  return {
    checkId: check.checkId,
    checkName: check.checkName,
    entries,
    allNotApplicable:
      entries.length > 0 && notApplicableCount === entries.length,
  };
}



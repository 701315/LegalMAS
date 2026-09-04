// =============================================================
// src/pages/tabs/dd-grid-v1/ddGridV1.cellSummary.ts
// Строитель компактной сводки ячейки check-а для DD Grid V1 матрицы.
//
// i18n: проброс tFn в форматтер.
// =============================================================

import { formatDDGridV1CellText } from "./ddGridV1.formatters";
import type { DDGridV1CellState, DDGridV1CellValueDTO } from "../../../types/dealReview";
import type {
  DDGridV1CheckNode,
  DDGridV1DerivedModel,
} from "./ddGridV1.types";

type TFunction = (key: string, options?: Record<string, unknown>) => string;

export interface DDGridV1CheckCellSummaryEntry {
  key: string;
  label: string;
  displayText: string;
  cellState: DDGridV1CellState;
}

export interface DDGridV1CheckCellSummary {
  checkId: string;
  checkName: string;
  entries: DDGridV1CheckCellSummaryEntry[];
  allNotApplicable: boolean;
}

export function buildDDGridV1CheckCellSummary(
  model: DDGridV1DerivedModel,
  documentId: string,
  _docType: string,
  check: DDGridV1CheckNode,
  tFn?: TFunction, // 🌟 Добавили опциональный транслятор
): DDGridV1CheckCellSummary {
  const perDocCells = model.cellValues[documentId] ?? {};
  const segmentId = "_default";
  const perSegmentCells = perDocCells[segmentId] ?? {};

  const entries: DDGridV1CheckCellSummaryEntry[] = check.columns.map(
    (runtimeCol, indexInCheck) => {
      const rawCell: DDGridV1CellValueDTO | null =
        perSegmentCells[runtimeCol.column.column_id] ?? null;

      let effectiveState: DDGridV1CellState;
      if (rawCell) {
        effectiveState = rawCell.cell_state;
      } else {
        effectiveState = "not_executed";
      }

      const displayText = formatDDGridV1CellText(
        effectiveState,
        rawCell,
        runtimeCol.column,
        tFn, // 🌟 Пробрасываем tFn
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
    allNotApplicable: false,
  };
}



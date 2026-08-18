// =============================================================
// src/pages/tabs/dd-grid-v1/ddGridV1.cellSummary.ts
// Строитель компактной сводки ячейки check-а для DD Grid V1 матрицы.
//
// Правила:
// - никаких хардкодов конкретных check_id / column_id / doc_type;
// - для каждого runtime column строим одну строку "Label: value";
// - value идёт через formatDDGridV1CellText — единственный источник
//   правды по форматированию (text / enum / yes_no / presence_only);
// - если для (document, column) ячейки нет — отображаем fallback_display
//   колонки (not_executed).
// - not_applicable удалён из типа DDGridV1CellState.
// =============================================================

import { formatDDGridV1CellText } from "./ddGridV1.formatters";
import type { DDGridV1CellState, DDGridV1CellValueDTO } from "../../../types/dealReview";
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
   * Примечание: allNotApplicable всегда false, т.к. not_applicable
   * удалён из типа DDGridV1CellState. Применимость check гарантируется
   * планировщиком на бэкенде.
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
  _docType: string, // eslint-disable-line @typescript-eslint/no-unused-vars
  check: DDGridV1CheckNode,
): DDGridV1CheckCellSummary {
  // 3-уровневый lookup: doc_id → segment_id → column_id
  // segment_id = "_default" для single-segment документов
  const perDocCells = model.cellValues[documentId] ?? {};
  const segmentId = "_default";
  const perSegmentCells = perDocCells[segmentId] ?? {};

  const entries: DDGridV1CheckCellSummaryEntry[] = check.columns.map(
    (runtimeCol, indexInCheck) => {
      // rawCell — это DDGridV1CellValueDTO | null (не Record!)
      const rawCell: DDGridV1CellValueDTO | null = perSegmentCells[runtimeCol.column.column_id] ?? null;

      let effectiveState: DDGridV1CellState;
      if (rawCell) {
        effectiveState = rawCell.cell_state;
      } else {
        // Применимость check гарантируется планировщиком на бэкенде.
        // Для docType-scoped колонок которые не применимы — not_executed.
        effectiveState = "not_executed";
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
    allNotApplicable: false,
  };
}



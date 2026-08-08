// =============================================================
// src/pages/tabs/dd-grid-v1/DDGridV1ExportButtons.tsx
// V1-native export buttons.
//
// В matrix mode кнопки PDF/Word триггерят callback onRequestMatrixLayout,
// чтобы parent (ExportPanel) показал inline layout picker.
// В list mode PDF/Word работают напрямую без picker.
// Excel всегда работает напрямую.
// =============================================================

import React from "react";
import Button from "../../../components/ui/Button";
import { INLINE_PANEL_ACTIVE_CLASS } from "../grid/gridTab.constants";

import type { DDGridV1DerivedModel } from "./ddGridV1.types";
import {
  buildDDGridV1ListExportTable,
  buildDDGridV1MatrixExportTable,
} from "./ddGridV1.exportBuilder";
import {
  exportListToExcel,
  exportListToPdf,
  exportListToWord,
  exportMatrixToExcel,
} from "./ddGridV1.exportRunners";

// -------------------------------------------------------------
// Props
// -------------------------------------------------------------

export type DDGridV1ExportMode = "list" | "matrix";

export interface DDGridV1ExportButtonsProps {
  model: DDGridV1DerivedModel;
  mode: DDGridV1ExportMode;
  visibleCheckIds?: readonly string[];
  includePassResults?: boolean;
  visibleExtraColumnIds?: readonly string[];
  dealName?: string;
  runId?: string;

  /**
   * Вызывается в matrix mode при клике на PDF или Word.
   * Parent должен показать inline layout picker.
   */
  onRequestMatrixLayout?: (format: "pdf" | "docx") => void;

  /**
   * Формат, для которого сейчас открыт layout picker в parent.
   * Используется для подсветки активной кнопки (PDF / Word).
   */
  activeLayoutPickerFormat?: "pdf" | "docx" | null;
}

// -------------------------------------------------------------
// Main component
// -------------------------------------------------------------

export const DDGridV1ExportButtons: React.FC<DDGridV1ExportButtonsProps> = ({
  model,
  mode,
  visibleCheckIds,
  includePassResults,
  visibleExtraColumnIds,
  dealName,
  runId,
  onRequestMatrixLayout,
  activeLayoutPickerFormat,
}) => {
  const listTable = React.useMemo(() => {
    if (mode !== "list") return null;
    return buildDDGridV1ListExportTable({
      model,
      visibleCheckIds,
      includePassResults,
      visibleExtraColumnIds,
    });
  }, [mode, model, visibleCheckIds, includePassResults, visibleExtraColumnIds]);

  const matrixTable = React.useMemo(() => {
    if (mode !== "matrix") return null;
    return buildDDGridV1MatrixExportTable({ model, visibleCheckIds });
  }, [mode, model, visibleCheckIds]);

  const rowCount = listTable?.rowCount ?? matrixTable?.rowCount ?? 0;
  const columnCount =
    listTable?.headers.length ?? matrixTable?.leafHeaders.length ?? 0;
  const isEmpty = rowCount === 0;
  const opts = { dealName, runId };

  const handleExcel = () => {
    if (isEmpty) return;
    if (mode === "matrix" && matrixTable) {
      void exportMatrixToExcel(matrixTable, opts);
    } else if (listTable) {
      void exportListToExcel(listTable.headers, listTable.rows, opts);
    }
  };

  const handlePdf = () => {
    if (isEmpty) return;
    if (mode === "matrix" && matrixTable) {
      onRequestMatrixLayout?.("pdf");
    } else if (listTable) {
      void exportListToPdf(listTable.headers, listTable.rows, opts);
    }
  };

  const handleWord = () => {
    if (isEmpty) return;
    if (mode === "matrix" && matrixTable) {
      onRequestMatrixLayout?.("docx");
    } else if (listTable) {
      void exportListToWord(listTable.headers, listTable.rows, opts);
    }
  };

  const disabledTitle = "Нет данных для экспорта";

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        type="button"
        size="sm"
        variant="secondary"
        onClick={handleExcel}
        disabled={isEmpty}
        title={
          isEmpty
            ? disabledTitle
            : `Экспорт ${rowCount} строк в Excel (${columnCount} колонок)`
        }
      >
        Excel
      </Button>

      <Button
        type="button"
        size="sm"
        variant={activeLayoutPickerFormat === "pdf" ? "outline" : "secondary"}
        onClick={handlePdf}
        disabled={isEmpty}
        title={
          isEmpty
            ? disabledTitle
            : `Экспорт ${rowCount} строк в PDF (${columnCount} колонок)`
        }
        aria-expanded={activeLayoutPickerFormat === "pdf"}
        className={
          activeLayoutPickerFormat === "pdf" ? INLINE_PANEL_ACTIVE_CLASS : ""
        }
      >
        PDF
      </Button>

      <Button
        type="button"
        size="sm"
        variant={activeLayoutPickerFormat === "docx" ? "outline" : "secondary"}
        onClick={handleWord}
        disabled={isEmpty}
        title={
          isEmpty
            ? disabledTitle
            : `Экспорт ${rowCount} строк в Word (${columnCount} колонок)`
        }
        aria-expanded={activeLayoutPickerFormat === "docx"}
        className={
          activeLayoutPickerFormat === "docx" ? INLINE_PANEL_ACTIVE_CLASS : ""
        }
      >
        Word
      </Button>
    </div>
  );
};

export default DDGridV1ExportButtons;



// =============================================================
// src/pages/tabs/grid/ReviewExportButtons.tsx
// Review-native export buttons для ReviewFinding[].
// Без зависимости от legacy CheckResult / exportResults utils.
// =============================================================

import React from "react";

import type { ReviewFinding } from "./reviewGrid.types";
import { buildReviewExportRows } from "./reviewGrid.export";
import {
  exportReviewRowsToExcel,
  exportReviewRowsToPdf,
  exportReviewRowsToWord,
} from "./reviewGrid.exportUtils";

import Button from "../../../components/ui/Button";

interface ReviewExportButtonsProps {
  findings: ReviewFinding[];
  dealName?: string;
  runId?: string;
}

/**
 * Review-native export buttons.
 *
 * Для непрофессионального программиста:
 * Этот компонент экспортирует все findings, которые ему передали.
 * Обычно это уже отфильтрованный набор после поиска и review filters.
 *
 * ВАЖНО:
 * - экспортируются все переданные findings;
 * - selected-only export пока не поддерживается,
 *   потому что selection в DDMatrixGrid сейчас row-level;
 * - используется review-specific export pipeline,
 *   а не legacy exportResults utils.
 */
export const ReviewExportButtons: React.FC<ReviewExportButtonsProps> = ({
  findings,
  dealName,
  runId,
}) => {
  const isEmpty = findings.length === 0;

  const runExport = async (
    exporter: (rows: ReturnType<typeof buildReviewExportRows>, meta: {
      dealName?: string;
      runId?: string;
    }) => void | Promise<void>,
  ) => {
    if (isEmpty) return;

    const rows = buildReviewExportRows(findings);
    await exporter(rows, { dealName, runId });
  };

  const handleExportExcel = () => {
    void runExport(exportReviewRowsToExcel);
  };

  const handleExportPdf = () => {
    void runExport(exportReviewRowsToPdf);
  };

  const handleExportWord = () => {
    void runExport(exportReviewRowsToWord);
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        type="button"
        size="sm"
        variant="secondary"
        onClick={handleExportExcel}
        disabled={isEmpty}
        title={
          isEmpty
            ? "Нет данных для экспорта"
            : `Экспорт ${findings.length} findings в Excel`
        }
      >
        Excel
      </Button>

      <Button
        type="button"
        size="sm"
        variant="secondary"
        onClick={handleExportPdf}
        disabled={isEmpty}
        title={
          isEmpty
            ? "Нет данных для экспорта"
            : `Экспорт ${findings.length} findings в PDF`
        }
      >
        PDF
      </Button>

      <Button
        type="button"
        size="sm"
        variant="secondary"
        onClick={handleExportWord}
        disabled={isEmpty}
        title={
          isEmpty
            ? "Нет данных для экспорта"
            : `Экспорт ${findings.length} findings в Word`
        }
      >
        Word
      </Button>
    </div>
  );
};

export default ReviewExportButtons;





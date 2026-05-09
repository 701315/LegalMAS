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
 * ВАЖНО:
 * - экспортируют все переданные findings (filtered set);
 * - НЕ поддерживают selected-only export пока, потому что
 *   DDMatrixGrid selection сейчас row-level (documentId), а не finding-level;
 * - используют review export pipeline, а не legacy exportResults utils.
 */
export const ReviewExportButtons: React.FC<ReviewExportButtonsProps> = ({
  findings,
  dealName,
  runId,
}) => {
  const isEmpty = findings.length === 0;

  const handleExportExcel = () => {
    if (isEmpty) return;

    const rows = buildReviewExportRows(findings);
    exportReviewRowsToExcel(rows, { dealName, runId });
  };

  const handleExportPdf = () => {
    if (isEmpty) return;

    const rows = buildReviewExportRows(findings);
    exportReviewRowsToPdf(rows, { dealName, runId });
  };

  const handleExportWord = async () => {
    if (isEmpty) return;

    const rows = buildReviewExportRows(findings);
    await exportReviewRowsToWord(rows, { dealName, runId });
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



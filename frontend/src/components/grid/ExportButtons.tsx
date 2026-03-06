// =============================================================
// src/components/grid/ExportButtons.tsx
// Кнопки экспорта для DD Grid.
// - Если есть выбранные строки -> экспортируем их.
// - Если нет выбранных -> экспортируем все результаты.
// =============================================================

import React from "react";
import type { CheckResult } from "../../types";
import {
  exportResultsToExcel,
  exportResultsToPdf,
  exportResultsToWord,
} from "../../utils/exportResults";

interface ExportButtonsProps {
  allResults: CheckResult[];
  selectedResults: CheckResult[];
  dealName?: string;
  runId?: string;
}

export const ExportButtons: React.FC<ExportButtonsProps> = ({
  allResults,
  selectedResults,
  dealName,
  runId,
}) => {
  const hasSelection = selectedResults.length > 0;
  const baseResults = hasSelection ? selectedResults : allResults;

  const handleExcel = () => {
    if (!baseResults.length) return;
    exportResultsToExcel(baseResults, { dealName, runId });
  };

  const handlePdf = () => {
    if (!baseResults.length) return;
    exportResultsToPdf(baseResults, { dealName, runId });
  };

  const handleWord = async () => {
    if (!baseResults.length) return;
    await exportResultsToWord(baseResults, { dealName, runId });
  };

  const labelSuffix = hasSelection
    ? `(${selectedResults.length} selected)`
    : "(all)";

  return (
    <div className="flex flex-wrap items-center gap-2 mb-2">
      <span className="text-xs text-gray-600">
        Export {labelSuffix}
      </span>
      <button
        type="button"
        onClick={handleExcel}
        className="px-2 py-1 text-xs border rounded hover:bg-gray-100"
      >
        Excel
      </button>
      <button
        type="button"
        onClick={handlePdf}
        className="px-2 py-1 text-xs border rounded hover:bg-gray-100"
      >
        PDF
      </button>
      <button
        type="button"
        onClick={handleWord}
        className="px-2 py-1 text-xs border rounded hover:bg-gray-100"
      >
        Word
      </button>
    </div>
  );
};

export default ExportButtons;

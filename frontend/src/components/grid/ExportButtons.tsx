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
import Button from "../ui/Button";

interface ExportButtonsProps {
  allResults: CheckResult[];
  selectedResults: CheckResult[];
  dealName?: string;
  runId?: string;

  /**
   * Дополнительный контекст запуска анализа для экспорта:
   * - режим проверок (global_only / doc_type_only / global_and_doc_type)
   * - стратегия пайплайна (REUSE_STRUCTURE / FULL_RERUN / ...)
   *
   * Эти поля не обязательны: если их нет, экспорт просто не будет
   * добавлять эту информацию в имя файла/шапку.
   */
  runChecksMode?:
    | "global_only"
    | "doc_type_only"
    | "global_and_doc_type";
  runPipelineStrategy?: string;
}

export const ExportButtons: React.FC<ExportButtonsProps> = ({
  allResults,
  selectedResults,
  dealName,
  runId,
  runChecksMode,
  runPipelineStrategy,
}) => {
  const hasSelection = selectedResults.length > 0;
  const baseResults = hasSelection ? selectedResults : allResults;
  const isDisabled = baseResults.length === 0;

  const commonMeta = {
    dealName,
    runId,
    runChecksMode,
    runPipelineStrategy,
  };

  const handleExcel = () => {
    if (!baseResults.length) return;
    exportResultsToExcel(baseResults, commonMeta);
  };

  const handlePdf = () => {
    if (!baseResults.length) return;
    exportResultsToPdf(baseResults, commonMeta);
  };

  const handleWord = async () => {
    if (!baseResults.length) return;
    await exportResultsToWord(baseResults, commonMeta);
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        type="button"
        size="sm"
        variant="secondary"
        onClick={handleExcel}
        disabled={isDisabled}
        title={isDisabled ? "Нет данных для экспорта" : "Экспорт в Excel"}
      >
        Excel
      </Button>

      <Button
        type="button"
        size="sm"
        variant="secondary"
        onClick={handlePdf}
        disabled={isDisabled}
        title={isDisabled ? "Нет данных для экспорта" : "Экспорт в PDF"}
      >
        PDF
      </Button>

      <Button
        type="button"
        size="sm"
        variant="secondary"
        onClick={handleWord}
        disabled={isDisabled}
        title={isDisabled ? "Нет данных для экспорта" : "Экспорт в Word"}
      >
        Word
      </Button>
    </div>
  );
};

export default ExportButtons;




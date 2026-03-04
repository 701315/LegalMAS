// =============================================================
// src/pages/tabs/GridTab.tsx
// Вкладка "DD Grid": поиск + фильтры + Magic Zoom + bulk QC.
// =============================================================

import React from "react";
import { useAllResults } from "../../api/results";
import {
  useConfirmResults,
  useRejectResults,
  useOverrideResults,
} from "../../api/qc";
import type {
  CheckResult,
  QCStatus,
  SeverityLevel,
  CheckResultValue,
} from "../../types";
import DDGrid from "../../components/grid/DDGrid";
import GridFilters, {
  type QuickFilter,
} from "../../components/grid/GridFilters";
import MagicZoom from "../../components/evidence/MagicZoom";
import EvidencePanel from "../../components/evidence/EvidencePanel";
import BulkQCBar from "../../components/qc/BulkQCBar";
import QualityFlagsLegend from "../../components/qc/QualityFlagsLegend";

interface GridTabProps {
  dealId: string;
  runId: string | null;
}

/**
 * Вкладка DD Grid:
 * - загружает все результаты для выбранного run;
 * - даёт поиск и несколько быстрых фильтров;
 * - показывает DDGrid + Magic Zoom + EvidencePanel;
 * - поддерживает массовый QC через BulkQCBar.
 */
const GridTab: React.FC<GridTabProps> = ({ dealId, runId }) => {
  const [searchText, setSearchText] = React.useState("");
  const [quickFilter, setQuickFilter] = React.useState<QuickFilter>("all");
  const [zoomResult, setZoomResult] = React.useState<CheckResult | null>(null);
  const [panelResult, setPanelResult] = React.useState<CheckResult | null>(null);
  const [selectedIds, setSelectedIds] = React.useState<string[]>([]);
  const [selectedDocType, setSelectedDocType] = React.useState<string | null>(
    null,
  );

  const {
    data: allResults = [],
    isLoading,
    error,
  } = useAllResults(runId);

  const confirmMutation = useConfirmResults();
  const rejectMutation = useRejectResults();
  const overrideMutation = useOverrideResults();

  const availableDocTypes = React.useMemo(
    () =>
      Array.from(
        new Set(
          allResults
            .map((r) => r.doc_type)
            .filter((v): v is string => !!v),
        ),
      ).sort(),
    [allResults],
  );

  const filteredResults = React.useMemo(() => {
    let results: CheckResult[] = allResults;

    if (searchText.trim()) {
      const lower = searchText.toLowerCase();
      results = results.filter(
        (r) =>
          r.document_name?.toLowerCase().includes(lower) ||
          r.check_name.toLowerCase().includes(lower),
      );
    }

    if (selectedDocType) {
      results = results.filter((r) => r.doc_type === selectedDocType);
    }

    switch (quickFilter) {
      case "critical":
        results = results.filter((r) => r.severity === "critical");
        break;
      case "high":
        results = results.filter((r) => r.severity === "high");
        break;
      case "unclear":
        results = results.filter((r) => r.result === "unclear");
        break;
      case "no_qc":
        results = results.filter((r) => r.qc_status === "pending");
        break;
      case "important":
        results = results.filter(
          (r) =>
            (r.severity === "critical" || r.severity === "high") &&
            r.qc_status === "pending",
        );
        break;
      case "conditional":
        results = results.filter(
          (r) => r.conditional_check_triggered === true,
        );
        break;
      case "low_confidence":
        results = results.filter((r) => {
          const v = (r as any).classification_confidence as
            | number
            | null
            | undefined;
          return v != null && v < 0.6;
        });
        break;
      case "all":
      default:
        break;
    }

    return results;
  }, [allResults, searchText, quickFilter, selectedDocType]);

  const importantCount = React.useMemo(
    () =>
      allResults.filter(
        (r) =>
          (r.severity === "critical" || r.severity === "high") &&
          r.qc_status === "pending",
      ).length,
    [allResults],
  );

  const unclearCount = React.useMemo(
    () => allResults.filter((r) => r.result === "unclear").length,
    [allResults],
  );

  const handleEyeClick = (result: CheckResult) => {
    setZoomResult(result);
  };

  const handleCloseZoom = () => {
    setZoomResult(null);
  };

  const handleOpenFull = (result: CheckResult) => {
    setPanelResult(result);
  };

  const handleClosePanel = () => {
    setPanelResult(null);
  };

  const handleZoomQcChange = (
    result: CheckResult,
    newStatus: Exclude<QCStatus, "pending">,
  ) => {
    // TODO: позже вызывать QC API и обновлять useAllResults
    console.log("QC change from MagicZoom", result.id, newStatus);
  };

  const handleSelectionChange = (ids: string[]) => {
    setSelectedIds(ids);
  };

  const handleBulkConfirm = (comment: string) => {
    if (!selectedIds.length) return;
    confirmMutation.mutate({ ids: selectedIds, comment });
  };

  const handleBulkReject = (comment: string) => {
    if (!selectedIds.length) return;
    rejectMutation.mutate({ ids: selectedIds, comment });
  };

  const handleBulkOverride = ({
    newSeverity,
    newResult,
    comment,
  }: {
    newSeverity: SeverityLevel;
    newResult?: CheckResultValue;
    comment: string;
  }) => {
    if (!selectedIds.length) return;
    overrideMutation.mutate({
      ids: selectedIds,
      newSeverity,
      comment,
      newResult,
    });
  };

  const handlePanelQcChange = (
    result: CheckResult,
    newStatus: Exclude<QCStatus, "pending">,
  ) => {
    // TODO: позже вызывать QC API и обновлять useAllResults
    console.log("QC change from EvidencePanel", result.id, newStatus);
  };

  if (!runId) {
    return (
      <div className="text-sm text-gray-500 py-4">
        Нет выбранного запуска анализа. Сначала запустите анализ на вкладке
        «Обзор».
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="text-sm text-gray-500 py-4">Загружаем результаты…</div>
    );
  }

  if (error) {
    return (
      <div className="text-sm text-red-600 py-4">
        Не удалось загрузить результаты проверки.
      </div>
    );
  }

  return (
    <div className="space-y-3 pb-10">
      <div className="text-[11px] text-gray-400">Сделка: {dealId}</div>

      <GridFilters
        searchText={searchText}
        onSearchChange={setSearchText}
        activeFilter={quickFilter}
        onFilterChange={setQuickFilter}
        totalCount={allResults.length}
        filteredCount={filteredResults.length}
        availableDocTypes={availableDocTypes}
        selectedDocType={selectedDocType}
        onDocTypeChange={setSelectedDocType}
      />

      <div className="text-[11px] text-gray-400">
        Важных без QC: {importantCount} · Неясных: {unclearCount}
      </div>

      <QualityFlagsLegend />

      <DDGrid
        results={filteredResults}
        onEyeClick={handleEyeClick}
        onSelectionChange={handleSelectionChange}
      />

      {zoomResult && (
        <MagicZoom
          result={zoomResult}
          onClose={handleCloseZoom}
          onQcChange={handleZoomQcChange}
          onOpenFull={handleOpenFull}
        />
      )}

      {panelResult && (
        <EvidencePanel
          result={panelResult}
          onClose={handleClosePanel}
          onQcChange={handlePanelQcChange}
        />
      )}

      {selectedIds.length > 0 && (
        <BulkQCBar
          selectedCount={selectedIds.length}
          onConfirm={handleBulkConfirm}
          onReject={handleBulkReject}
          onOverride={handleBulkOverride}
        />
      )}
    </div>
  );
};

export default GridTab;

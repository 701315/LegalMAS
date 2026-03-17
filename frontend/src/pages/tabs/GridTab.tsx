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
import ExportButtons from "../../components/grid/ExportButtons";
import { useDealPermissions } from "../../hooks/usePermissions";

interface GridTabProps {
  dealId: string;
  runId: string | null;
}

type GridScope = "all" | "global" | "doctype";

/**
 * Вкладка DD Grid:
 * - загружает все результаты для выбранного run;
 * - даёт поиск и несколько быстрых фильтров;
 * - показывает DDGrid + Magic Zoom + EvidencePanel;
 * - поддерживает массовый QC через BulkQCBar;
 * - позволяет экспортировать результаты (все или выбранные).
 */
const GridTab: React.FC<GridTabProps> = ({ dealId, runId }) => {
  const [searchText, setSearchText] = React.useState("");
  const [quickFilter, setQuickFilter] = React.useState<QuickFilter>("all");
  const [zoomResult, setZoomResult] = React.useState<CheckResult | null>(null);
  const [panelResult, setPanelResult] = React.useState<CheckResult | null>(
    null,
  );
  const [selectedIds, setSelectedIds] = React.useState<string[]>([]);
  const [selectedDocType, setSelectedDocType] = React.useState<string | null>(
    null,
  );
  const [gridScope, setGridScope] = React.useState<GridScope>("all");
  const [selectedScopeDocTypes, setSelectedScopeDocTypes] = React.useState<
    string[]
  >([]);

  const { canReclassifyDocuments } = useDealPermissions(dealId);
  const canDoQc = canReclassifyDocuments;

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

  const globalResults = React.useMemo(
    () => filteredResults.filter((r) => r.origin === "global_playbook"),
    [filteredResults],
  );

  const doctypeResults = React.useMemo(
    () =>
      filteredResults.filter(
        (r) => !r.origin || r.origin !== "global_playbook",
      ),
    [filteredResults],
  );

  const scopeDoctypes = React.useMemo(
    () =>
      Array.from(
        new Set(
          doctypeResults
            .map((r) => r.doc_type)
            .filter((v): v is string => !!v),
        ),
      ).sort(),
    [doctypeResults],
  );

  const scopeResults = React.useMemo(() => {
    let base: CheckResult[];

    switch (gridScope) {
      case "global":
        base = globalResults;
        break;
      case "doctype":
        base = doctypeResults;
        break;
      case "all":
      default:
        base = filteredResults;
        break;
    }

    if (gridScope === "doctype" && selectedScopeDocTypes.length > 0) {
      base = base.filter(
        (r) => r.doc_type && selectedScopeDocTypes.includes(r.doc_type),
      );
    }

    return base;
  }, [
    gridScope,
    filteredResults,
    globalResults,
    doctypeResults,
    selectedScopeDocTypes,
  ]);

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

  const selectedResults = React.useMemo(
    () => scopeResults.filter((r) => selectedIds.includes(r.id)),
    [scopeResults, selectedIds],
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
    if (!canDoQc) return;
    // TODO: позже вызывать QC API и обновлять useAllResults
    console.log("QC change from MagicZoom", result.id, newStatus);
  };

  const handleSelectionChange = (ids: string[]) => {
    if (!canDoQc) {
      setSelectedIds([]);
      return;
    }
    setSelectedIds(ids);
  };

  const handleBulkConfirm = (comment: string) => {
    if (!canDoQc) return;
    if (!selectedIds.length) return;
    confirmMutation.mutate({ ids: selectedIds, comment });
  };

  const handleBulkReject = (comment: string) => {
    if (!canDoQc) return;
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
    if (!canDoQc) return;
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
    if (!canDoQc) return;
    // TODO: позже вызывать QC API и обновлять useAllResults
    console.log("QC change from EvidencePanel", result.id, newStatus);
  };

  const toggleScopeDocType = (docType: string) => {
    setSelectedScopeDocTypes((prev) =>
      prev.includes(docType)
        ? prev.filter((d) => d !== docType)
        : [...prev, docType],
    );
  };

  const resetScopeDocTypes = () => {
    setSelectedScopeDocTypes([]);
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
      <div className="text-sm text-gray-500 py-4">
        Загружаем результаты…
      </div>
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

      <div className="flex items-center justify-between text-[11px] text-gray-400">
        <div>
          Важных без QC: {importantCount} · Неясных: {unclearCount}
        </div>
        <div className="flex items-center gap-2">
          <span>Показывать проверки:</span>
          <button
            type="button"
            className={
              "px-2 py-1 rounded border text-[11px] " +
              (gridScope === "all"
                ? "bg-blue-50 border-blue-400 text-blue-700"
                : "bg-white border-gray-300 text-gray-600")
            }
            onClick={() => setGridScope("all")}
          >
            Все
          </button>
          <button
            type="button"
            className={
              "px-2 py-1 rounded border text-[11px] " +
              (gridScope === "global"
                ? "bg-blue-50 border-blue-400 text-blue-700"
                : "bg-white border-gray-300 text-gray-600")
            }
            onClick={() => setGridScope("global")}
          >
            Глобальный плейбук
          </button>
          <button
            type="button"
            className={
              "px-2 py-1 rounded border text-[11px] " +
              (gridScope === "doctype"
                ? "bg-blue-50 border-blue-400 text-blue-700"
                : "bg-white border-gray-300 text-gray-600")
            }
            onClick={() => setGridScope("doctype")}
          >
            По типу документа
          </button>
        </div>
      </div>

      {gridScope === "doctype" && scopeDoctypes.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-gray-600">
          <span>Типы документов (для этого вида проверок):</span>
          <button
            type="button"
            className="px-2 py-0.5 rounded border border-gray-300 bg-white"
            onClick={resetScopeDocTypes}
          >
            Все
          </button>
          {scopeDoctypes.map((dt) => {
            const checked = selectedScopeDocTypes.includes(dt);
            return (
              <label
                key={dt}
                className={
                  "inline-flex items-center gap-1 px-2 py-0.5 rounded border text-[11px] cursor-pointer " +
                  (checked
                    ? "bg-blue-50 border-blue-400 text-blue-700"
                    : "bg-white border-gray-300 text-gray-700")
                }
              >
                <input
                  type="checkbox"
                  className="h-3 w-3"
                  checked={checked}
                  onChange={() => toggleScopeDocType(dt)}
                />
                <span>{dt}</span>
              </label>
            );
          })}
        </div>
      )}

      <QualityFlagsLegend />

      <ExportButtons
        allResults={scopeResults}
        selectedResults={selectedResults}
        dealName={dealId}
        runId={runId ?? undefined}
      />

      <DDGrid
        results={scopeResults}
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

      {canDoQc && selectedIds.length > 0 && (
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

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
  OpenViewerAtFn,
  OpenViewerAtPayload,
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
import { useRun } from "../../api/runs";
import DocumentViewerModal from "../../components/viewer/DocumentViewerModal";

interface GridTabProps {
  dealId: string;
  runId: string | null;
}

type GridScope = "all" | "global" | "doctype";
type GridMode = "matrix" | "list";

// Нормализованный тип источника проверки.
type NormalizedOrigin = "global" | "doctype" | "other";

// Функция нормализации значений origin/origin_type из бэкенда
// в стабильный enum NormalizedOrigin.
function normalizeOrigin(
  rawOrigin: string | null | undefined,
  originType?: "global" | "doctype" | "custom",
): NormalizedOrigin {
  if (originType === "global") return "global";
  if (originType === "doctype") return "doctype";

  if (!rawOrigin) {
    return "other";
  }

  const raw = rawOrigin.toString();
  const upper = raw.toUpperCase();

  if (
    upper === "GLOBAL_PLAYBOOK" ||
    raw === "global_playbook" ||
    raw === "project_playbook"
  ) {
    return "global";
  }

  if (upper === "DOCUMENT_TYPE") {
    return "doctype";
  }

  return "other";
}

type ViewerState = {
  location: OpenViewerAtPayload;
  pdfUrl: string;
} | null;

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

  // Флаг "только со структурированными данными"
  const [hasStructuredDataOnly, setHasStructuredDataOnly] =
    React.useState(false);

  const [gridScope, setGridScope] = React.useState<GridScope>("all");
  const [selectedScopeDocTypes, setSelectedScopeDocTypes] = React.useState<
    string[]
  >([]);
  const [gridMode, setGridMode] = React.useState<GridMode>("matrix");

  // Стейт цели для viewer'a + реальный PDF URL
  const [viewerState, setViewerState] = React.useState<ViewerState>(null);
  const [isViewerLoading, setIsViewerLoading] = React.useState(false);
  const [viewerError, setViewerError] = React.useState<string | null>(null);

  const { canReclassifyDocuments } = useDealPermissions(dealId);
  const canDoQc = canReclassifyDocuments;

  const {
    data: allResults = [],
    isLoading,
    error,
  } = useAllResults(runId);

  // Загружаем информацию о Run, чтобы знать checks_mode / pipeline_strategy
  const {
    data: run,
    isLoading: isRunLoading,
    error: runError,
  } = useRun(runId, false);

  // Инициализация gridScope на основе checks_mode Run
  React.useEffect(() => {
    if (!run) return;
    const mode = run.checks_mode;
    if (mode === "global_only") {
      setGridScope("global");
    } else if (mode === "doc_type_only") {
      setGridScope("doctype");
    } else {
      setGridScope("all");
    }
  }, [run]);

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

    // Новый фильтр: только те результаты, у которых есть structured_data
    if (hasStructuredDataOnly) {
      results = results.filter((r) => r.structured_data != null);
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
          const v = r.doc_classification_confidence;
          return v != null && v < 0.6;
        });
        break;
      case "all":
      default:
        break;
    }

    console.log(
      "DEBUG origins in filteredResults",
      Array.from(
        new Set(results.map((r) => String(r.origin ?? "(null)"))),
      ),
    );

    return results;
  }, [
    allResults,
    searchText,
    quickFilter,
    selectedDocType,
    hasStructuredDataOnly,
  ]);

  const globalResults = React.useMemo(
    () =>
      filteredResults.filter(
        (r) => normalizeOrigin(r.origin, r.origin_type) === "global",
      ),
    [filteredResults],
  );

  console.log(
    "DEBUG globalResults origins",
    Array.from(
      new Set(globalResults.map((r) => String(r.origin ?? "(null)"))),
    ),
    "len=",
    globalResults.length,
  );

  const doctypeResults = React.useMemo(
    () =>
      filteredResults.filter(
        (r) => normalizeOrigin(r.origin, r.origin_type) === "doctype",
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

  const uniqueDocCount = React.useMemo(
    () => new Set(scopeResults.map((r) => r.document_id)).size,
    [scopeResults],
  );

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

  // Коллбэк открытия viewer'a в нужном месте документа:
  // 1) тянем /api/v1/documents/{doc_id}/pdf-url
  // 2) кладём реальный pdfUrl + location в стейт
  const openViewerAt: OpenViewerAtFn = async (loc) => {
    try {
      setViewerError(null);
      setIsViewerLoading(true);
      
      const resp = await fetch(
        `/api/v1/documents/${loc.documentId}/converted-pdf-url`,
        { credentials: "include" },
      );
      if (!resp.ok) {
        console.error("Failed to fetch pdf-url", resp.status);
        setViewerError("Не удалось получить ссылку на PDF документа");
        setIsViewerLoading(false);
        return;
      }
      const pdfUrl = await resp.text();

      console.log("PDF URL from backend:", pdfUrl);

      if (!pdfUrl) {
        setViewerError("Сервер не вернул ссылку на PDF");
        setIsViewerLoading(false);
        return;
      }
      setViewerState({ location: loc, pdfUrl });
    } catch (e) {
      console.error("Error fetching converted-pdf-url", e);
      setViewerError("Ошибка при запросе PDF документа");
    } finally {
      setIsViewerLoading(false);
    }
  };

  if (!runId) {
    return (
      <div className="text-sm text-gray-500 py-4">
        Нет выбранного запуска анализа. Сначала запустите анализ на вкладке
        «Обзор».
      </div>
    );
  }

  if (isRunLoading) {
    return (
      <div className="text-sm text-gray-500 py-4">
        Загружаем информацию о запуске анализа…
      </div>
    );
  }

  if (runError) {
    return (
      <div className="text-sm text-red-600 py-4">
        Не удалось загрузить информацию о запуске анализа.
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

      {/* Краткий контекст последнего Run для грида */}
      {run && (
        <div className="text-[11px] text-gray-500">
          Анализ: run {run.id} · статус: {run.status}
          {run.checks_mode && (
            <>
              {" · "}режим проверок{" "}
              <span className="font-medium text-gray-700">
                {run.checks_mode === "global_and_doc_type"
                  ? "Плейбук + типы документов"
                  : run.checks_mode === "global_only"
                  ? "Только плейбук"
                  : "Только типы документов"}
              </span>
            </>
          )}
          {run.pipeline_strategy && (
            <>
              {" · "}стратегия пайплайна{" "}
              <span className="font-medium text-gray-700">
                {run.pipeline_strategy}
              </span>
            </>
          )}
        </div>
      )}

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
        hasStructuredDataOnly={hasStructuredDataOnly}
        onHasStructuredDataChange={setHasStructuredDataOnly}
      />

      <div className="flex items-center justify-between text-[11px] text-gray-400">
        <div>
          Важных без QC: {importantCount} · Неясных: {unclearCount}
          {" · "}
          Проверок: {scopeResults.length} по {uniqueDocCount} документам
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

      <div className="flex items-center justify-end text-[11px] text-gray-400 gap-2">
        <span>Режим:</span>
        <button
          type="button"
          className={
            "px-2 py-1 rounded border text-[11px] " +
            (gridMode === "matrix"
              ? "bg-blue-50 border-blue-400 text-blue-700"
              : "bg-white border-gray-300 text-gray-600")
          }
          onClick={() => setGridMode("matrix")}
        >
          Матрица
        </button>
        <button
          type="button"
          className={
            "px-2 py-1 rounded border text-[11px] " +
            (gridMode === "list"
              ? "bg-blue-50 border-blue-400 text-blue-700"
              : "bg-white border-gray-300 text-gray-600")
          }
          onClick={() => setGridMode("list")}
        >
          Список
        </button>
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
        runChecksMode={run?.checks_mode}
        runPipelineStrategy={run?.pipeline_strategy}
      />

      <DDGrid
        results={scopeResults}
        onEyeClick={handleEyeClick}
        onSelectionChange={handleSelectionChange}
        mode={gridMode}
        onOpenAtLocation={openViewerAt}
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
          onOpenAtLocation={openViewerAt}
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

      <DocumentViewerModal
        open={!!viewerState}
        onClose={() => setViewerState(null)}
        fileUrl={viewerState?.pdfUrl ?? null}
        location={viewerState?.location ?? null}
        title={viewerError ?? (isViewerLoading ? "Загрузка PDF…" : null)}
      />
    </div>
  );
};

export default GridTab;
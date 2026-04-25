// =============================================================
// src/pages/tabs/GridTab.tsx
// Вкладка "DD Grid":
// - legacy режим: поиск + фильтры + Magic Zoom + bulk QC поверх CheckResult[]
// - review режим: backend dd-matrix DTO поверх run-scoped review API
// =============================================================

import React from "react";
import { useAllResults } from "../../api/results";
import {
  useConfirmResults,
  useRejectResults,
  useOverrideResults,
} from "../../api/qc";
import { useDealReviewDdMatrix } from "../../api/dealReview";
import type {
  CheckResult,
  QCStatus,
  SeverityLevel,
  CheckResultValue,
  OpenViewerAtFn,
  OpenViewerAtPayload,
} from "../../types";
import DDGrid from "../../components/grid/DDGrid";
import DDMatrixGrid from "../../components/grid/DDMatrixGrid";
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
import DocumentViewerModal, {
  type LayoutElement,
  type SizedChunkMeta,
} from "../../components/viewer/DocumentViewerModal";
import type { DDMatrixResponseDTO } from "../../types/dealReview";

interface GridTabProps {
  dealId: string;
  runId: string | null;
}

type GridScope = "all" | "global" | "doctype";
type GridMode = "matrix" | "list";
type GridDataSource = "legacy" | "review";

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

// Состояние viewer'а: куда прыгать, какой PDF открывать,
// и дополнительные данные для overlay (layout + чанки).
type ViewerState = {
  location: OpenViewerAtPayload;
  pdfUrl: string;
  layoutElements?: LayoutElement[];
  sizedChunks?: SizedChunkMeta[];
} | null;

function getReviewSummary(matrix: DDMatrixResponseDTO | undefined) {
  if (!matrix) {
    return {
      documentCount: 0,
      checkCount: 0,
      criticalCount: 0,
      highCount: 0,
      mediumCount: 0,
      unclearCount: 0,
      passCount: 0,
    };
  }

  return {
    documentCount: matrix.total_documents ?? matrix.documents.length,
    checkCount: matrix.total_checks ?? matrix.checks.length,
    criticalCount: matrix.severity_counts?.critical ?? 0,
    highCount: matrix.severity_counts?.high ?? 0,
    mediumCount: matrix.severity_counts?.medium ?? 0,
    unclearCount: matrix.severity_counts?.unclear ?? 0,
    passCount: matrix.severity_counts?.pass ?? 0,
  };
}

const GridTab: React.FC<GridTabProps> = ({ dealId, runId }) => {
  const [dataSource, setDataSource] =
    React.useState<GridDataSource>("legacy");

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

  // Стейт цели для viewer'a + реальный PDF URL + данные для overlay
  const [viewerState, setViewerState] = React.useState<ViewerState>(null);
  const [isViewerLoading, setIsViewerLoading] = React.useState(false);
  const [viewerError, setViewerError] = React.useState<string | null>(null);

  const { canReclassifyDocuments } = useDealPermissions(dealId);
  const canDoQc = canReclassifyDocuments;

  // Legacy источник
  const {
    data: allResults = [],
    isLoading: isLegacyLoading,
    error: legacyError,
  } = useAllResults(runId);

  // Новый review matrix источник
  const {
    data: ddMatrix,
    isLoading: isReviewLoading,
    error: reviewError,
  } = useDealReviewDdMatrix(dealId, runId);

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

  React.useEffect(() => {
    if (dataSource === "review" && gridMode !== "matrix") {
      setGridMode("matrix");
    }
  }, [dataSource, gridMode]);

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

    // Фильтр: только те результаты, у которых есть structured_data
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
        (r) => !!r.doc_type && selectedScopeDocTypes.includes(r.doc_type),
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

  const reviewSummary = React.useMemo(
    () => getReviewSummary(ddMatrix),
    [ddMatrix],
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
  // 1) тянем /api/v1/documents/{doc_id}/converted-pdf-url
  // 2) параллельно тянем layout + sized-chunks для overlay
  // 3) кладём всё в стейт viewerState
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

      if (!pdfUrl) {
        setViewerError("Сервер не вернул ссылку на PDF");
        setIsViewerLoading(false);
        return;
      }

      const [layoutResp, chunksResp] = await Promise.all([
        fetch(
          `/api/v1/documents/${loc.documentId}/layout-for-viewer`,
          { credentials: "include" },
        ),
        fetch(
          `/api/v1/documents/${loc.documentId}/sized-chunks`,
          { credentials: "include" },
        ),
      ]);

      let layoutElements: LayoutElement[] | undefined;
      let sizedChunks: SizedChunkMeta[] | undefined;

      if (layoutResp.ok) {
        const layoutJson = await layoutResp.json();
        layoutElements = (layoutJson.elements ?? []).map((el: any) => ({
          elementId: el.element_id,
          page: el.page,
          bbox: el.bbox,
        }));
      }

      if (chunksResp.ok) {
        const chunksJson = await chunksResp.json();

        const rawChunks = Array.isArray(chunksJson?.chunks)
          ? chunksJson.chunks
          : [];

        sizedChunks = rawChunks.map((ch: any) => ({
          id: String(ch.id),
          elementIds: Array.isArray(ch.element_ids)
            ? ch.element_ids.map(String)
            : [],
          clauseUids: Array.isArray(ch.clause_uids)
            ? ch.clause_uids.map(String)
            : [],
        }));
      }

      setViewerState({
        location: loc,
        pdfUrl,
        layoutElements,
        sizedChunks,
      });
    } catch (e) {
      console.error("Error fetching viewer data", e);
      setViewerError("Ошибка при запросе данных для просмотра документа");
    } finally {
      setIsViewerLoading(false);
    }
  };

  if (!runId) {
    return (
      <div className="py-4 text-sm text-gray-500">
        Нет выбранного запуска анализа. Сначала запустите анализ на вкладке
        «Обзор».
      </div>
    );
  }

  if (isRunLoading) {
    return (
      <div className="py-4 text-sm text-gray-500">
        Загружаем информацию о запуске анализа…
      </div>
    );
  }

  if (runError) {
    return (
      <div className="py-4 text-sm text-red-600">
        Не удалось загрузить информацию о запуске анализа.
      </div>
    );
  }

  const isGridLoading =
    dataSource === "review" ? isReviewLoading : isLegacyLoading;
  const gridError = dataSource === "review" ? reviewError : legacyError;

  if (isGridLoading) {
    return (
      <div className="py-4 text-sm text-gray-500">
        {dataSource === "review"
          ? "Загружаем review-матрицу…"
          : "Загружаем результаты…"}
      </div>
    );
  }

  if (gridError) {
    return (
      <div className="py-4 text-sm text-red-600">
        {dataSource === "review"
          ? "Не удалось загрузить review-матрицу."
          : "Не удалось загрузить результаты проверки."}
      </div>
    );
  }

  return (
    <div className="space-y-3 pb-10">
      <div className="text-[11px] text-gray-400">Сделка: {dealId}</div>

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

      <div className="flex items-center justify-between gap-4 text-[11px] text-gray-400">
        <div className="flex items-center gap-2">
          <span>Источник:</span>
          <button
            type="button"
            className={
              "rounded border px-2 py-1 text-[11px] " +
              (dataSource === "review"
                ? "bg-blue-50 border-blue-400 text-blue-700"
                : "bg-white border-gray-300 text-gray-600")
            }
            onClick={() => setDataSource("review")}
          >
            Review matrix
          </button>
          <button
            type="button"
            className={
              "rounded border px-2 py-1 text-[11px] " +
              (dataSource === "legacy"
                ? "bg-blue-50 border-blue-400 text-blue-700"
                : "bg-white border-gray-300 text-gray-600")
            }
            onClick={() => setDataSource("legacy")}
          >
            Legacy results
          </button>
        </div>

        <div className="flex items-center gap-2">
          <span>Режим:</span>
          <button
            type="button"
            className={
              "rounded border px-2 py-1 text-[11px] " +
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
              "rounded border px-2 py-1 text-[11px] " +
              (gridMode === "list"
                ? "bg-blue-50 border-blue-400 text-blue-700"
                : "bg-white border-gray-300 text-gray-600")
            }
            onClick={() => setGridMode("list")}
            disabled={dataSource === "review"}
            title={
              dataSource === "review"
                ? "В review-режиме пока доступна только матрица"
                : undefined
            }
          >
            Список
          </button>
        </div>
      </div>

      {dataSource === "legacy" && (
        <>
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
                  "rounded border px-2 py-1 text-[11px] " +
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
                  "rounded border px-2 py-1 text-[11px] " +
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
                  "rounded border px-2 py-1 text-[11px] " +
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
                className="rounded border border-gray-300 bg-white px-2 py-0.5"
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
                      "inline-flex cursor-pointer items-center gap-1 rounded border px-2 py-0.5 text-[11px] " +
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
        </>
      )}

      {dataSource === "review" && (
        <>
          <div className="flex items-center justify-between text-[11px] text-gray-400">
            <div>
              Документов: {reviewSummary.documentCount}
              {" · "}
              Проверок: {reviewSummary.checkCount}
              {" · "}
              Critical: {reviewSummary.criticalCount}
              {" · "}
              High: {reviewSummary.highCount}
              {" · "}
              Medium: {reviewSummary.mediumCount}
              {" · "}
              Unclear: {reviewSummary.unclearCount}
            </div>
            <div>
              Quarantine: {ddMatrix?.quarantine_count ?? 0}
              {" · "}
              Degraded: {ddMatrix?.degraded_count ?? 0}
              {" · "}
              Evidence validity:{" "}
              {ddMatrix?.evidence_validity_rate != null
                ? `${Math.round(ddMatrix.evidence_validity_rate * 100)}%`
                : "—"}
            </div>
          </div>

          <div className="rounded border border-blue-100 bg-blue-50 px-3 py-2 text-[11px] text-blue-800">
            Review mode рендерит матрицу поверх run-scoped backend DTO.
            Legacy-фильтры, bulk QC, Magic Zoom и export пока остаются только
            в legacy-режиме, чтобы не маппить новую модель обратно в
            CheckResult[].
          </div>

          <DDMatrixGrid
            data={ddMatrix ?? null}
            onOpenAtLocation={openViewerAt}
            onOpenDocument={({ documentId, documentName }) => {
              console.log("Open review document", { documentId, documentName });
            }}
            onSelectionChange={() => {
              // Review bulk actions будут добавлены отдельным инкрементом.
            }}
          />
        </>
      )}

      {dataSource === "legacy" && zoomResult && (
        <MagicZoom
          result={zoomResult}
          onClose={handleCloseZoom}
          onQcChange={handleZoomQcChange}
          onOpenFull={handleOpenFull}
        />
      )}

      {dataSource === "legacy" && panelResult && (
        <EvidencePanel
          result={panelResult}
          onClose={handleClosePanel}
          onQcChange={handlePanelQcChange}
          onOpenAtLocation={openViewerAt}
        />
      )}

      {dataSource === "legacy" && canDoQc && selectedIds.length > 0 && (
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
        layoutElements={viewerState?.layoutElements}
        sizedChunks={viewerState?.sizedChunks}
      />
    </div>
  );
};

export default GridTab;



// =============================================================
// src/pages/tabs/grid/GridTabPage.tsx
// Вкладка "DD Grid":
// - legacy режим: поиск + фильтры + Magic Zoom + bulk QC поверх CheckResult[]
// - review режим: backend dd-matrix DTO поверх run-scoped review API
//   + unified DDMatrixCellDetails для evidence (без MagicZoom/EvidencePanel)
// Приведено к общему дизайну workspace LegalMAS.
// =============================================================

import React from "react";

import { useAllResults } from "../../../api/results";
import {
  useConfirmResults,
  useRejectResults,
  useOverrideResults,
} from "../../../api/qc";
import { useDealReviewDdMatrix } from "../../../api/dealReview";
import { useRun } from "../../../api/runs";
import { useDocuments } from "../../../api/documents";
import ReviewGridFilters from "../../../components/grid/ReviewGridFilters";
import type {
  CheckResult,
  QCStatus,
  SeverityLevel,
  CheckResultValue,
  OpenViewerAtFn,
  DocumentCompositionMeta,
} from "../../../types";

import DDGrid from "../../../components/grid/DDGrid";
import DDMatrixGrid from "../../../components/grid/DDMatrixGrid";
import GridFilters, {
  type QuickFilter,
} from "../../../components/grid/GridFilters";
import MagicZoom from "../../../components/evidence/MagicZoom";
import EvidencePanel from "../../../components/evidence/EvidencePanel";
import BulkQCBar from "../../../components/qc/BulkQCBar";
import Button from "../../../components/ui/Button";
import PageSection from "../../../components/ui/PageSection";
import DocumentViewerModal, {
  type LayoutElement,
  type SizedChunkMeta,
} from "../../../components/viewer/DocumentViewerModal";

import { useDealPermissions } from "../../../hooks/usePermissions";
import {
  filterReviewFindings,
  filterReviewRows,
} from "./reviewGrid.filters";
import { INLINE_PANEL_ACTIVE_CLASS } from "./gridTab.constants";
import {
  ExportStatCard,
  ScopeInlinePanel,
  SectionCard,
  StatCard,
} from "./gridTab.sections";
import type {
  GridDataSource,
  GridMode,
  GridScope,
  GridTabProps,
  ViewerState,
} from "./gridTab.types";
import { humanChecksMode } from "./gridTab.utils";
import {
  filterLegacyResults,
  getDoctypeResults,
  getGlobalResults,
  getScopeDoctypes,
  getScopeResults,
  getSelectedResults,
} from "./gridTab.filters";
import {
  DEFAULT_REVIEW_FILTER_STATE,
  type ReviewFilterState,
  type ReviewSelectionItem,
} from "./reviewGrid.types";
import { selectReviewGridData } from "./reviewGrid.selectors";
import ReviewExportButtons from "./ReviewExportButtons";
import { getReviewQcDisabledNote } from "./reviewGrid.qc";

const GridTabPage: React.FC<GridTabProps> = ({ dealId, runId }) => {
  const [dataSource, setDataSource] =
    React.useState<GridDataSource>("legacy");

  const [searchText, setSearchText] = React.useState("");
  const [quickFilter, setQuickFilter] = React.useState<QuickFilter>("all");
  const [zoomResult, setZoomResult] = React.useState<CheckResult | null>(null);
  const [panelResult, setPanelResult] = React.useState<CheckResult | null>(
    null,
  );
  const [selectedIds, setSelectedIds] = React.useState<string[]>([]);
  const [legacyMultiDocOnly] = React.useState(false);

  const [reviewFilterState, setReviewFilterState] =
    React.useState<ReviewFilterState>(DEFAULT_REVIEW_FILTER_STATE);

  const [reviewSelection, setReviewSelection] = React.useState<
    ReviewSelectionItem[]
  >([]);
  const [isReviewFiltersPanelOpen, setIsReviewFiltersPanelOpen] =
    React.useState(false);

  const [gridScope, setGridScope] = React.useState<GridScope>("all");
  const [selectedScopeDocTypes, setSelectedScopeDocTypes] = React.useState<
    string[]
  >([]);
  const [gridMode, setGridMode] = React.useState<GridMode>("matrix");
  const [isScopePanelOpen, setIsScopePanelOpen] = React.useState(false);
  const [isFiltersPanelOpen, setIsFiltersPanelOpen] = React.useState(false);

  const [viewerState, setViewerState] = React.useState<ViewerState>(null);
  const [isViewerLoading, setIsViewerLoading] = React.useState(false);
  const [viewerError, setViewerError] = React.useState<string | null>(null);

  const { canReclassifyDocuments } = useDealPermissions(dealId);
  const canDoQc = canReclassifyDocuments;

  const { data: documentsPage } = useDocuments(dealId);

  const compositionByDocId = React.useMemo(() => {
    const items = documentsPage?.items ?? [];
    return new Map<string, DocumentCompositionMeta>(
      items
        .filter((d): d is typeof d & { composition: DocumentCompositionMeta } =>
          d.composition != null,
        )
        .map((d) => [d.id, d.composition]),
    );
  }, [documentsPage]);

  const {
    data: allResults = [],
    isLoading: isLegacyLoading,
    error: legacyError,
  } = useAllResults(runId);

  const {
    data: ddMatrix,
    isLoading: isReviewLoading,
    error: reviewError,
  } = useDealReviewDdMatrix(dealId, runId);

  const {
    data: run,
    isLoading: isRunLoading,
    error: runError,
  } = useRun(runId, false);

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

  const filteredResults = React.useMemo(
    () =>
      filterLegacyResults({
        results: allResults,
        searchText,
        quickFilter,
      }),
    [allResults, searchText, quickFilter],
  );

  const globalResults = React.useMemo(
    () => getGlobalResults(filteredResults),
    [filteredResults],
  );

  const doctypeResults = React.useMemo(
    () => getDoctypeResults(filteredResults),
    [filteredResults],
  );

  const scopeDoctypes = React.useMemo(
    () => getScopeDoctypes(doctypeResults),
    [doctypeResults],
  );

  const scopeResults = React.useMemo(
    () =>
      getScopeResults({
        gridScope,
        filteredResults,
        globalResults,
        doctypeResults,
        selectedScopeDocTypes,
      }),
    [
      gridScope,
      filteredResults,
      globalResults,
      doctypeResults,
      selectedScopeDocTypes,
    ],
  );

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
    () => getSelectedResults(scopeResults, selectedIds),
    [scopeResults, selectedIds],
  );

  const reviewDerived = React.useMemo(
    () => selectReviewGridData(ddMatrix ?? null),
    [ddMatrix],
  );

  const filteredReviewFindings = React.useMemo(
    () =>
      filterReviewFindings(
        reviewDerived.findings,
        reviewDerived.rows,
        reviewFilterState,
      ),
    [reviewDerived.findings, reviewDerived.rows, reviewFilterState],
  );

  const filteredReviewRows = React.useMemo(
    () => filterReviewRows(reviewDerived.rows, filteredReviewFindings),
    [reviewDerived.rows, filteredReviewFindings],
  );

  const reviewSummary = React.useMemo(
    () => reviewDerived.stats,
    [reviewDerived.stats],
  );

  const reviewQcDisabledNote = React.useMemo(
    () => getReviewQcDisabledNote(reviewSelection),
    [reviewSelection],
  );

  const checksModeLabel = humanChecksMode(run?.checks_mode);

  const scopeButtonLabel =
    gridScope === "all"
      ? "Область: все"
      : gridScope === "global"
        ? "Область: глобальный плейбук"
        : selectedScopeDocTypes.length > 0
          ? `Типы документов: ${selectedScopeDocTypes.length}`
          : "Область: по типу документа";

  const filtersButtonLabel =
    quickFilter === "all" && !searchText.trim()
      ? "Фильтры"
      : "Фильтры применены";

  const reviewFiltersButtonLabel =
    reviewFilterState.quickFilter === "all" &&
    !reviewFilterState.searchText.trim() &&
    !reviewFilterState.selectedDocTypes.length &&
    !reviewFilterState.selectedOrigins.length &&
    !reviewFilterState.multiDocumentOnly &&
    !reviewFilterState.criticalOnly
      ? "Фильтры"
      : "Фильтры применены";

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
    if (!canDoQc || !selectedIds.length) return;
    confirmMutation.mutate({ ids: selectedIds, comment });
  };

  const handleBulkReject = (comment: string) => {
    if (!canDoQc || !selectedIds.length) return;
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
    if (!canDoQc || !selectedIds.length) return;

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

  const handleResetReviewFilters = () => {
    setReviewFilterState(DEFAULT_REVIEW_FILTER_STATE);
  };

  const handleReviewSelectionChange = (rowIds: string[]) => {
    const items: ReviewSelectionItem[] = rowIds.map((rowId) => ({
      rowId,
    }));
    setReviewSelection(items);
  };

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
        fetch(`/api/v1/documents/${loc.documentId}/layout-for-viewer`, {
          credentials: "include",
        }),
        fetch(`/api/v1/documents/${loc.documentId}/sized-chunks`, {
          credentials: "include",
        }),
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
    } catch (error) {
      console.error("Error fetching viewer data", error);
      setViewerError("Ошибка при запросе данных для просмотра документа");
    } finally {
      setIsViewerLoading(false);
    }
  };

  if (!runId) {
    return (
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
        <div className="px-6 py-10">
          <div className="flex min-h-[280px] flex-col items-center justify-center text-center">
            <h2 className="text-base font-semibold text-[var(--text-primary)]">
              DD Grid станет доступен после запуска анализа
            </h2>
            <p className="mt-2 max-w-md text-sm text-[var(--text-muted)]">
              Нет выбранного запуска анализа. Сначала запустите анализ на вкладке
              «Обзор».
            </p>
          </div>
        </div>
      </section>
    );
  }

  if (isRunLoading) {
    return (
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
        <div className="px-6 py-10">
          <div className="text-sm text-[var(--text-muted)]">
            Загружаем информацию о запуске анализа…
          </div>
        </div>
      </section>
    );
  }

  if (runError) {
    return (
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
        <div className="px-6 py-10">
          <div className="rounded-xl border border-[var(--color-error)]/20 bg-[var(--color-error)]/10 px-4 py-3 text-sm text-[var(--color-error)]">
            Не удалось загрузить информацию о запуске анализа.
          </div>
        </div>
      </section>
    );
  }

  const isGridLoading =
    dataSource === "review" ? isReviewLoading : isLegacyLoading;
  const gridError = dataSource === "review" ? reviewError : legacyError;

  if (isGridLoading) {
    return (
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
        <div className="px-6 py-10">
          <div className="text-sm text-[var(--text-muted)]">
            {dataSource === "review"
              ? "Загружаем review-матрицу…"
              : "Загружаем результаты…"}
          </div>
        </div>
      </section>
    );
  }

  if (gridError) {
    return (
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
        <div className="px-6 py-10">
          <div className="rounded-xl border border-[var(--color-error)]/20 bg-[var(--color-error)]/10 px-4 py-3 text-sm text-[var(--color-error)]">
            {dataSource === "review"
              ? "Не удалось загрузить review-матрицу."
              : "Не удалось загрузить результаты проверки."}
          </div>
        </div>
      </section>
    );
  }

  return (
    <div className="flex min-h-full flex-col gap-6">
      <PageSection
        title="DD Grid"
        subtitle="Матрица проверок и доказательств с переключением между legacy-результатами и review matrix."
        rightSlot={
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              size="sm"
              variant={dataSource === "review" ? "primary" : "secondary"}
              onClick={() => setDataSource("review")}
            >
              Review matrix
            </Button>

            <Button
              type="button"
              size="sm"
              variant={dataSource === "legacy" ? "primary" : "secondary"}
              onClick={() => setDataSource("legacy")}
            >
              Legacy results
            </Button>
          </div>
        }
      >
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
          <StatCard
            label="Документы"
            value={
              dataSource === "review"
                ? reviewSummary.documentsCount
                : uniqueDocCount
            }
          />

          <StatCard
            label="Проверки"
            value={
              dataSource === "review"
                ? reviewSummary.checksCount
                : scopeResults.length
            }
            tone="accent"
          />

          <StatCard
            label="Critical / High"
            value={
              dataSource === "review"
                ? `${reviewSummary.criticalCount} / ${reviewSummary.highCount}`
                : `${allResults.filter((r) => r.severity === "critical").length} / ${
                    allResults.filter((r) => r.severity === "high").length
                  }`
            }
            tone="critical"
          />

          <StatCard
            label={dataSource === "review" ? "Unclear" : "Без QC / Unclear"}
            value={
              dataSource === "review"
                ? `${reviewSummary.unclearCount}`
                : `${importantCount} / ${unclearCount}`
            }
          />

          <StatCard label="Режим проверок" value={checksModeLabel ?? "—"} />

          {dataSource === "legacy" ? (
            <ExportStatCard
              allResults={scopeResults}
              selectedResults={selectedResults}
              dealId={dealId}
              runId={runId ?? undefined}
              runChecksMode={run?.checks_mode}
              runPipelineStrategy={run?.pipeline_strategy}
            />
          ) : (
            <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-4 shadow-sm">
              <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                Экспорт review findings
              </div>
              <div className="mt-3">
                <ReviewExportButtons
                  findings={filteredReviewFindings}
                  dealName={dealId}
                  runId={runId ?? undefined}
                />
              </div>
            </div>
          )}

        </div>
      </PageSection>

      {dataSource === "legacy" && (
        <SectionCard
          title="Результаты DD Grid"
          description="Сетка результатов проверки с доступом к Magic Zoom, Evidence Panel и массовым QC-действиям."
          actions={
            <div className="flex flex-wrap items-center gap-3">
              <Button
                type="button"
                size="sm"
                variant={isScopePanelOpen ? "outline" : "secondary"}
                onClick={() => setIsScopePanelOpen((prev) => !prev)}
                aria-expanded={isScopePanelOpen}
                aria-controls="dd-grid-scope-panel"
                className={isScopePanelOpen ? INLINE_PANEL_ACTIVE_CLASS : ""}
              >
                {scopeButtonLabel}
              </Button>

              <Button
                type="button"
                size="sm"
                variant={isFiltersPanelOpen ? "outline" : "secondary"}
                onClick={() => setIsFiltersPanelOpen((prev) => !prev)}
                aria-expanded={isFiltersPanelOpen}
                aria-controls="dd-grid-filters-panel"
                className={isFiltersPanelOpen ? INLINE_PANEL_ACTIVE_CLASS : ""}
              >
                {filtersButtonLabel}
              </Button>

              <div
                className="inline-flex items-center rounded-xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] p-1"
                role="tablist"
                aria-label="Режим отображения DD Grid"
              >
                <button
                  type="button"
                  role="tab"
                  aria-selected={gridMode === "matrix"}
                  onClick={() => setGridMode("matrix")}
                  className={
                    gridMode === "matrix"
                      ? "rounded-lg bg-[var(--bg-card)] px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] shadow-sm"
                      : "rounded-lg px-3 py-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                  }
                >
                  Матрица
                </button>

                <button
                  type="button"
                  role="tab"
                  aria-selected={gridMode === "list"}
                  onClick={() => setGridMode("list")}
                  className={
                    gridMode === "list"
                      ? "rounded-lg bg-[var(--bg-card)] px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] shadow-sm"
                      : "rounded-lg px-3 py-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                  }
                >
                  Список
                </button>
              </div>
            </div>
          }
        >
          <div className="flex flex-col gap-4">
            {isScopePanelOpen && (
              <div id="dd-grid-scope-panel">
                <ScopeInlinePanel
                  gridScope={gridScope}
                  setGridScope={setGridScope}
                  scopeDoctypes={scopeDoctypes}
                  selectedScopeDocTypes={selectedScopeDocTypes}
                  toggleScopeDocType={toggleScopeDocType}
                  resetScopeDocTypes={resetScopeDocTypes}
                  onClose={() => setIsScopePanelOpen(false)}
                />
              </div>
            )}

            {isFiltersPanelOpen && (
              <div
                id="dd-grid-filters-panel"
                className="rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated-soft)]"
              >
                <div className="border-b border-[var(--border-subtle)] px-4 py-3">
                  <p className="text-sm font-semibold text-[var(--text-primary)]">
                    Фильтры результатов
                  </p>
                  <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
                    Поиск и быстрые фильтры для legacy-результатов DD Grid
                  </p>
                </div>

                <div className="px-4 py-4">
                  <GridFilters
                    searchText={searchText}
                    onSearchChange={setSearchText}
                    activeFilter={quickFilter}
                    onFilterChange={setQuickFilter}
                  />
                </div>

                <div className="flex items-center justify-end gap-2 border-t border-[var(--border-subtle)] px-4 py-3">
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    onClick={() => setIsFiltersPanelOpen(false)}
                  >
                    Закрыть
                  </Button>
                </div>
              </div>
            )}

            <div className="min-h-[480px]">
              <DDGrid
                results={scopeResults}
                compositionByDocId={compositionByDocId}
                onlyMultiDocument={legacyMultiDocOnly}
                onEyeClick={handleEyeClick}
                onSelectionChange={handleSelectionChange}
                mode={gridMode}
                onOpenAtLocation={openViewerAt}
              />
            </div>
          </div>
        </SectionCard>
      )}

      {dataSource === "review" && (
        <>
          <SectionCard
            title="Review matrix controls"
            description="Фильтрация, экспорт и review-context для run-scoped матрицы документов и проверок."
            actions={
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant={isReviewFiltersPanelOpen ? "outline" : "secondary"}
                  onClick={() => setIsReviewFiltersPanelOpen((prev) => !prev)}
                  className={
                    isReviewFiltersPanelOpen ? INLINE_PANEL_ACTIVE_CLASS : ""
                  }
                >
                  {reviewFiltersButtonLabel}
                </Button>
              </div>
            }
          >
            <div className="flex flex-col gap-4">
              {isReviewFiltersPanelOpen && (
                <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated-soft)]">
                  <div className="border-b border-[var(--border-subtle)] px-4 py-3">
                    <p className="text-sm font-semibold text-[var(--text-primary)]">
                      Фильтры review matrix
                    </p>
                    <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
                      Поиск, quick filters и ограничения по типу документа / origin.
                    </p>
                  </div>

                  <div className="px-4 py-4">
                    <ReviewGridFilters
                      filterState={reviewFilterState}
                      onFilterStateChange={setReviewFilterState}
                      availableDocTypes={reviewDerived.availableDocTypes}
                      availableOrigins={reviewDerived.availableOrigins}
                    />
                  </div>

                  <div className="flex items-center justify-end gap-2 border-t border-[var(--border-subtle)] px-4 py-3">
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      onClick={handleResetReviewFilters}
                    >
                      Сбросить
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      onClick={() => setIsReviewFiltersPanelOpen(false)}
                    >
                      Закрыть
                    </Button>
                  </div>
                </div>
              )}
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                <StatCard label="Документов" value={reviewSummary.documentsCount} />
                <StatCard
                  label="Проверок"
                  value={reviewSummary.checksCount}
                  tone="accent"
                />
                <StatCard
                  label="Findings"
                  value={reviewSummary.findingsCount}
                />
                <StatCard
                  label="Critical"
                  value={reviewSummary.criticalCount}
                  tone="critical"
                />
                <StatCard label="Unclear" value={reviewSummary.unclearCount} />
              </div>

              <div className="rounded-xl border border-[var(--accent-primary)]/10 bg-[var(--accent-muted)] px-4 py-3 text-sm leading-6 text-[var(--text-secondary)]">
                Review mode теперь использует unified DDMatrixCellDetails для
                evidence и document context. Legacy MagicZoom / EvidencePanel
                отключены в review mode — весь evidence flow идёт через detail drawer.
              </div>

              <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3 text-sm text-[var(--text-secondary)]">
                {reviewQcDisabledNote}
              </div>
            </div>
          </SectionCard>

          <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
            <div className="px-6 pt-5">
              <h2 className="text-base font-semibold text-[var(--text-primary)]">
                Review DD Matrix
              </h2>
              <p className="mt-1 text-sm text-[var(--text-muted)]">
                Run-scoped матрица документов и проверок для review-режима.
              </p>
              <div className="mt-4 border-t border-[var(--border-subtle)]" />
            </div>

            <div className="px-6 py-5">
              <DDMatrixGrid
                runId={runId}
                rows={filteredReviewRows}
                columns={reviewDerived.columns}
                onOpenAtLocation={openViewerAt}
                onOpenDocument={({ documentId, documentName }) => {
                  console.log("Open review document", {
                    documentId,
                    documentName,
                  });
                }}
                onSelectionChange={handleReviewSelectionChange}
              />
            </div>
          </section>
        </>
      )}

      {dataSource === "legacy" && zoomResult && (
        <MagicZoom
          result={zoomResult}
          onClose={handleCloseZoom}
          onQcChange={handleZoomQcChange}
          onOpenFull={handleOpenFull}
          onOpenAtLocation={openViewerAt}
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
        open={Boolean(viewerState)}
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

export default GridTabPage;





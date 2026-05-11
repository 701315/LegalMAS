// =============================================================
// src/pages/tabs/grid/GridTabPage.tsx
// Review-only DD Grid workspace:
// - run-scoped review matrix API via useDealReviewDdMatrix
// - DDMatrixGrid for 2D matrix view
// - DDReviewListGrid for flat findings list view
// - unified DocumentViewerModal for evidence navigation
// - review filters, export, selection state
// - bulk QC actions for selected review findings
// =============================================================

import React from "react";
import { ChevronRight, Download, SlidersHorizontal } from "lucide-react";

import { useDealReviewDdMatrix } from "../../../api/dealReview";
import { useRun } from "../../../api/runs";
import ReviewGridFilters from "../../../components/grid/ReviewGridFilters";
import DDMatrixGrid from "../../../components/grid/DDMatrixGrid";
import DDReviewListGrid from "../../../components/grid/DDReviewListGrid";
import Button from "../../../components/ui/Button";
import PageSection from "../../../components/ui/PageSection";
import DocumentViewerModal, {
  type LayoutElement,
  type SizedChunkMeta,
} from "../../../components/viewer/DocumentViewerModal";

import type { OpenViewerAtFn } from "../../../types";

import { filterReviewFindings, filterReviewRows } from "./reviewGrid.filters";
import { INLINE_PANEL_ACTIVE_CLASS } from "./gridTab.constants";
import { StatCard } from "./gridTab.sections";
import type { GridMode, GridTabProps, ViewerState } from "./gridTab.types";
import { humanChecksMode } from "./gridTab.utils";
import {
  DEFAULT_REVIEW_FILTER_STATE,
  type ReviewFilterState,
  type ReviewSelectionItem,
} from "./reviewGrid.types";
import { selectReviewGridData } from "./reviewGrid.selectors";
import ReviewExportButtons from "./ReviewExportButtons";
import ReviewQcBulkActions from "./ReviewQcBulkActions";
import {
  getReviewQcCapability,
  getReviewQcDisabledNote,
  getSelectedReviewFindings,
} from "./reviewGrid.qc";

type LayoutElementApi = {
  element_id: string;
  page: number;
  bbox: [number, number, number, number];
};

type StatusStateCardProps = {
  title: string;
  description?: string;
  tone?: "default" | "error";
};

type ModeToggleProps = {
  value: GridMode;
  onChange: (mode: GridMode) => void;
};

type FiltersPanelProps = {
  open: boolean;
  gridMode: GridMode;
  filterState: ReviewFilterState;
  availableDocTypes: string[];
  availableOrigins: string[];
  onFilterStateChange: React.Dispatch<React.SetStateAction<ReviewFilterState>>;
  onReset: () => void;
  onClose: () => void;
};

type ExportPanelProps = {
  open: boolean;
  findings: ReturnType<typeof selectReviewGridData>["findings"];
  dealName: string;
  runId?: string;
};

type FetchTextOptions = {
  url: string;
  errorMessage: string;
  init?: RequestInit;
};

type FetchJsonOptions = {
  url: string;
  init?: RequestInit;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isBboxTuple(
  value: unknown,
): value is [number, number, number, number] {
  return (
    Array.isArray(value) &&
    value.length === 4 &&
    value.every((item) => typeof item === "number")
  );
}

function isLayoutElementApi(value: unknown): value is LayoutElementApi {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.element_id === "string" &&
    typeof value.page === "number" &&
    isBboxTuple(value.bbox)
  );
}

function parseLayoutElements(payload: unknown): LayoutElement[] | undefined {
  if (!isRecord(payload) || !Array.isArray(payload.elements)) {
    return undefined;
  }

  return payload.elements
    .filter(isLayoutElementApi)
    .map((element) => ({
      elementId: element.element_id,
      page: element.page,
      bbox: element.bbox,
    }));
}

function parseSizedChunks(payload: unknown): SizedChunkMeta[] | undefined {
  if (!isRecord(payload) || !Array.isArray(payload.chunks)) {
    return undefined;
  }

  return payload.chunks
    .filter(isRecord)
    .map((chunk) => ({
      id: String(chunk.id ?? ""),
      elementIds: Array.isArray(chunk.element_ids)
        ? chunk.element_ids.map(String)
        : [],
      clauseUids: Array.isArray(chunk.clause_uids)
        ? chunk.clause_uids.map(String)
        : [],
    }))
    .filter((chunk) => chunk.id.length > 0);
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }

  try {
    return JSON.stringify(error);
  } catch {
    return String(error);
  }
}

async function fetchTextOrThrow({
  url,
  errorMessage,
  init,
}: FetchTextOptions): Promise<string> {
  const response = await fetch(url, init);

  if (!response.ok) {
    throw new Error(errorMessage);
  }

  const text = await response.text();
  if (!text) {
    throw new Error(errorMessage);
  }

  return text;
}

async function fetchJsonIfOk({
  url,
  init,
}: FetchJsonOptions): Promise<unknown | undefined> {
  const response = await fetch(url, init);

  if (!response.ok) {
    return undefined;
  }

  return response.json();
}

const StatusStateCard: React.FC<StatusStateCardProps> = ({
  title,
  description,
  tone = "default",
}) => {
  const contentClassName =
    tone === "error"
      ? "rounded-xl border border-[var(--color-error)]/20 bg-[var(--color-error)]/10 px-4 py-3 text-sm text-[var(--color-error)]"
      : "text-sm text-[var(--text-muted)]";

  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
      <div className="px-6 py-10">
        <div
          className={
            tone === "error"
              ? contentClassName
              : "flex min-h-[280px] flex-col items-center justify-center text-center"
          }
        >
          <div className={contentClassName}>
            <div
              className={
                tone === "error"
                  ? undefined
                  : "text-base font-semibold text-[var(--text-primary)]"
              }
            >
              {title}
            </div>
            {description ? (
              <p
                className={
                  tone === "error"
                    ? "mt-0"
                    : "mt-2 max-w-md text-sm text-[var(--text-muted)]"
                }
              >
                {description}
              </p>
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
};

const ModeToggle: React.FC<ModeToggleProps> = ({ value, onChange }) => {
  const getTabClassName = (mode: GridMode) =>
    value === mode
      ? "rounded-lg bg-[var(--bg-card)] px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] shadow-sm"
      : "rounded-lg px-3 py-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)]";

  return (
    <div
      className="inline-flex items-center rounded-xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] p-1"
      role="tablist"
      aria-label="Review view mode"
    >
      <button
        type="button"
        role="tab"
        aria-selected={value === "matrix"}
        onClick={() => onChange("matrix")}
        className={getTabClassName("matrix")}
      >
        Матрица
      </button>

      <button
        type="button"
        role="tab"
        aria-selected={value === "list"}
        onClick={() => onChange("list")}
        className={getTabClassName("list")}
      >
        Список
      </button>
    </div>
  );
};

const FiltersPanel: React.FC<FiltersPanelProps> = ({
  open,
  gridMode,
  filterState,
  availableDocTypes,
  availableOrigins,
  onFilterStateChange,
  onReset,
  onClose,
}) => {
  if (!open) {
    return null;
  }

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated-soft)]">
      <div className="border-b border-[var(--border-subtle)] px-4 py-3">
        <p className="text-sm font-semibold text-[var(--text-primary)]">
          Фильтры review {gridMode === "list" ? "list" : "matrix"}
        </p>
        <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
          Поиск, quick filters и ограничения по типу документа / origin.
        </p>
      </div>

      <div className="px-4 py-4">
        <ReviewGridFilters
          filterState={filterState}
          onFilterStateChange={onFilterStateChange}
          availableDocTypes={availableDocTypes}
          availableOrigins={availableOrigins}
        />
      </div>

      <div className="flex items-center justify-end gap-2 border-t border-[var(--border-subtle)] px-4 py-3">
        <Button type="button" size="sm" variant="secondary" onClick={onReset}>
          Сбросить
        </Button>
        <Button type="button" size="sm" variant="secondary" onClick={onClose}>
          Закрыть
        </Button>
      </div>
    </div>
  );
};

// Inline-выезжающая панель экспорта.
// Семантически — disclosure region, не overlay: не использует position/z-index.
const ExportPanel: React.FC<ExportPanelProps> = ({
  open,
  findings,
  dealName,
  runId,
}) => {
  return (
    <div
      id="dd-grid-export-panel"
      aria-hidden={!open}
      className={`grid overflow-hidden transition-[grid-template-rows,opacity,margin] duration-300 ease-out ${
        open
          ? "mt-3 grid-rows-[1fr] opacity-100"
          : "mt-0 grid-rows-[0fr] opacity-0"
      }`}
    >
      <div className="min-h-0">
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-4 py-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                Экспорт findings
              </p>
              <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
                Файл будет сформирован по текущему набору отфильтрованных
                findings.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <ReviewExportButtons
                findings={findings}
                dealName={dealName}
                runId={runId}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

const GridTabPage: React.FC<GridTabProps> = ({ dealId, runId }) => {
  const [reviewFilterState, setReviewFilterState] =
    React.useState<ReviewFilterState>(DEFAULT_REVIEW_FILTER_STATE);
  const [reviewSelection, setReviewSelection] = React.useState<
    ReviewSelectionItem[]
  >([]);
  const [isReviewFiltersPanelOpen, setIsReviewFiltersPanelOpen] =
    React.useState(false);
  const [isExportPanelOpen, setIsExportPanelOpen] = React.useState(false);
  const [gridMode, setGridMode] = React.useState<GridMode>("matrix");
  const [viewerState, setViewerState] = React.useState<ViewerState>(null);
  const [isViewerLoading, setIsViewerLoading] = React.useState(false);
  const [viewerError, setViewerError] = React.useState<string | null>(null);

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

  const selectedReviewFindings = React.useMemo(
    () =>
      getSelectedReviewFindings(reviewDerived.findings, reviewSelection),
    [reviewDerived.findings, reviewSelection],
  );

  const reviewQcCapability = React.useMemo(
    () =>
      getReviewQcCapability(reviewSelection, selectedReviewFindings, runId),
    [reviewSelection, selectedReviewFindings, runId],
  );

  const reviewQcDisabledNote = React.useMemo(
    () => getReviewQcDisabledNote(reviewQcCapability),
    [reviewQcCapability],
  );

  const checksModeLabel = humanChecksMode(run?.checks_mode);

  const reviewFiltersButtonLabel =
    reviewFilterState.quickFilter === "all" &&
    !reviewFilterState.searchText.trim() &&
    !reviewFilterState.selectedDocTypes.length &&
    !reviewFilterState.selectedOrigins.length &&
    !reviewFilterState.multiDocumentOnly &&
    !reviewFilterState.criticalOnly
      ? "Фильтры"
      : "Фильтры применены";

  const handleResetReviewFilters = React.useCallback(() => {
    setReviewFilterState(DEFAULT_REVIEW_FILTER_STATE);
  }, []);

  const handleReviewSelectionChange = React.useCallback((rowIds: string[]) => {
    setReviewSelection(rowIds.map((rowId) => ({ rowId })));
  }, []);

  const handleCloseViewer = React.useCallback(() => {
    setViewerState(null);
  }, []);

  const handleToggleFilters = React.useCallback(() => {
    setIsReviewFiltersPanelOpen((prev) => !prev);
  }, []);

  const handleCloseFilters = React.useCallback(() => {
    setIsReviewFiltersPanelOpen(false);
  }, []);

  const handleToggleExportPanel = React.useCallback(() => {
    setIsExportPanelOpen((prev) => !prev);
  }, []);

  const openViewerAt: OpenViewerAtFn = React.useCallback(async (loc) => {
    try {
      setViewerError(null);
      setIsViewerLoading(true);

      const requestInit: RequestInit = { credentials: "include" };

      const pdfUrl = await fetchTextOrThrow({
        url: `/api/v1/documents/${loc.documentId}/converted-pdf-url`,
        errorMessage: "Не удалось получить ссылку на PDF документа",
        init: requestInit,
      });

      const [layoutJson, chunksJson] = await Promise.all([
        fetchJsonIfOk({
          url: `/api/v1/documents/${loc.documentId}/layout-for-viewer`,
          init: requestInit,
        }),
        fetchJsonIfOk({
          url: `/api/v1/documents/${loc.documentId}/sized-chunks`,
          init: requestInit,
        }),
      ]);

      setViewerState({
        location: loc,
        pdfUrl,
        layoutElements: parseLayoutElements(layoutJson),
        sizedChunks: parseSizedChunks(chunksJson),
      });
    } catch (error: unknown) {
      setViewerError(
        `Ошибка при запросе данных для просмотра документа: ${getErrorMessage(error)}`,
      );
    } finally {
      setIsViewerLoading(false);
    }
  }, []);

  if (!runId) {
    return (
      <StatusStateCard
        title="DD Grid станет доступен после запуска анализа"
        description="Нет выбранного запуска анализа. Сначала запустите анализ на вкладке «Обзор»."
      />
    );
  }

  if (isRunLoading) {
    return <StatusStateCard title="Загружаем информацию о запуске анализа…" />;
  }

  if (runError) {
    return (
      <StatusStateCard
        title="Не удалось загрузить информацию о запуске анализа."
        tone="error"
      />
    );
  }

  if (isReviewLoading) {
    return <StatusStateCard title="Загружаем матрицу документов…" />;
  }

  if (reviewError) {
    return (
      <StatusStateCard
        title="Не удалось загрузить матрицу документов."
        tone="error"
      />
    );
  }

  const matrixSectionTitle =
    gridMode === "matrix" ? "Review DD Matrix" : "Review findings list";

  const matrixSectionSubtitle =
    gridMode === "matrix"
      ? "Run-scoped матрица документов и проверок."
      : "Плоский список findings из review matrix с фильтрацией и экспортом.";

  return (
    <div className="flex min-h-full flex-col gap-6">
      <PageSection
        title="DD Grid"
        subtitle="Матрица документов и проверок с фильтрацией, экспортом и навигацией по evidence."
      >
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
          <StatCard label="Документы" value={reviewSummary.documentsCount} />
          <StatCard
            label="Проверки"
            value={reviewSummary.checksCount}
            tone="accent"
          />
          <StatCard label="Findings" value={reviewSummary.findingsCount} />
          <StatCard
            label="Critical / High"
            value={`${reviewSummary.criticalCount} / ${reviewSummary.highCount}`}
            tone="critical"
          />
          <StatCard label="Unclear" value={reviewSummary.unclearCount} />
          <StatCard label="Режим проверок" value={checksModeLabel ?? "—"} />
        </div>
      </PageSection>

      <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3 px-6 pt-5">
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-[var(--text-primary)]">
              {matrixSectionTitle}
            </h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              {matrixSectionSubtitle}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              size="sm"
              variant={isReviewFiltersPanelOpen ? "outline" : "secondary"}
              onClick={handleToggleFilters}
              leftIcon={<SlidersHorizontal className="h-4 w-4" />}
              aria-expanded={isReviewFiltersPanelOpen}
              aria-controls="dd-grid-filters-panel"
              className={
                isReviewFiltersPanelOpen ? INLINE_PANEL_ACTIVE_CLASS : ""
              }
            >
              {reviewFiltersButtonLabel}
            </Button>

            <Button
              type="button"
              size="sm"
              variant={isExportPanelOpen ? "outline" : "secondary"}
              onClick={handleToggleExportPanel}
              aria-expanded={isExportPanelOpen}
              aria-controls="dd-grid-export-panel"
              leftIcon={<Download className="h-4 w-4" />}
              rightIcon={
                <ChevronRight
                  className={`h-4 w-4 transition-transform duration-200 ${
                    isExportPanelOpen ? "rotate-90" : "rotate-0"
                  }`}
                />
              }
              className={isExportPanelOpen ? INLINE_PANEL_ACTIVE_CLASS : ""}
            >
              Экспорт данных
            </Button>

            <ModeToggle value={gridMode} onChange={setGridMode} />
          </div>
        </div>

        <div className="px-6 pt-3">
          <div id="dd-grid-filters-panel">
            <FiltersPanel
              open={isReviewFiltersPanelOpen}
              gridMode={gridMode}
              filterState={reviewFilterState}
              availableDocTypes={reviewDerived.availableDocTypes}
              availableOrigins={reviewDerived.availableOrigins}
              onFilterStateChange={setReviewFilterState}
              onReset={handleResetReviewFilters}
              onClose={handleCloseFilters}
            />
          </div>

          <ExportPanel
            open={isExportPanelOpen}
            findings={filteredReviewFindings}
            dealName={dealId}
            runId={runId ?? undefined}
          />

          {reviewQcCapability.supported && runId ? (
            <div className="mt-4">
              <ReviewQcBulkActions
                selectedRowsCount={reviewQcCapability.selectedRowsCount}
                selectedFindings={selectedReviewFindings}
                runId={runId}
              />
            </div>
          ) : reviewQcDisabledNote ? (
            <div className="mt-4 rounded-xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] px-4 py-3 text-sm text-[var(--text-secondary)]">
              {reviewQcDisabledNote}
            </div>
          ) : null}

          <div className="mt-4 border-t border-[var(--border-subtle)]" />
        </div>

        <div className="px-6 py-5">
          {gridMode === "matrix" ? (
            <DDMatrixGrid
              runId={runId}
              rows={filteredReviewRows}
              columns={reviewDerived.columns}
              onOpenAtLocation={openViewerAt}
              onSelectionChange={handleReviewSelectionChange}
            />
          ) : (
            <DDReviewListGrid
              runId={runId}
              rows={filteredReviewRows}
              columns={reviewDerived.columns}
              onOpenAtLocation={openViewerAt}
              onSelectionChange={handleReviewSelectionChange}
            />
          )}
        </div>
      </section>

      <DocumentViewerModal
        open={Boolean(viewerState)}
        onClose={handleCloseViewer}
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




// =============================================================
// src/pages/tabs/GridTab.tsx
// Вкладка "DD Grid":
// - legacy режим: поиск + фильтры + Magic Zoom + bulk QC поверх CheckResult[]
// - review режим: backend dd-matrix DTO поверх run-scoped review API
// Приведено к общему дизайну workspace LegalMAS.
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
  DocumentCompositionMeta,
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
import Button from "../../components/ui/Button";
import { useDealPermissions } from "../../hooks/usePermissions";
import { useRun } from "../../api/runs";
import DocumentViewerModal, {
  type LayoutElement,
  type SizedChunkMeta,
} from "../../components/viewer/DocumentViewerModal";
import type { DDMatrixResponseDTO } from "../../types/dealReview";
import { useDocuments } from "../../api/documents";

interface GridTabProps {
  dealId: string;
  runId: string | null;
}

type GridScope = "all" | "global" | "doctype";
type GridMode = "matrix" | "list";
type GridDataSource = "legacy" | "review";
type NormalizedOrigin = "global" | "doctype" | "other";

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

function SectionCard({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-[24px] border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
      <div className="flex flex-col gap-3 border-b border-[var(--border)] px-5 py-4 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">
            {title}
          </h2>
          {description ? (
            <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
              {description}
            </p>
          ) : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}

function StatCard({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: React.ReactNode;
  tone?: "default" | "critical" | "accent";
}) {
  const valueClass =
    tone === "critical"
      ? "text-[color:rgb(120,35,46)]"
      : tone === "accent"
        ? "text-[var(--accent-primary)]"
        : "text-[var(--text-primary)]";

  return (
    <div className="rounded-[20px] border border-[var(--border-soft)] bg-[var(--bg-base)] px-4 py-3">
      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
        {label}
      </div>
      <div className={`mt-2 text-lg font-semibold tracking-tight ${valueClass}`}>
        {value}
      </div>
    </div>
  );
}

const GridTab: React.FC<GridTabProps> = ({ dealId, runId }) => {
  const [dataSource, setDataSource] =
    React.useState<GridDataSource>("legacy");

  const [searchText, setSearchText] = React.useState("");
  const [quickFilter, setQuickFilter] = React.useState<QuickFilter>("all");
  const [zoomResult, setZoomResult] = React.useState<CheckResult | null>(null);
  const [panelResult, setPanelResult] = React.useState<CheckResult | null>(null);
  const [selectedIds, setSelectedIds] = React.useState<string[]>([]);
  const [selectedDocType, setSelectedDocType] = React.useState<string | null>(null);

  const [hasStructuredDataOnly, setHasStructuredDataOnly] =
    React.useState(false);
  const [legacyMultiDocOnly, setLegacyMultiDocOnly] = React.useState(false);
  const [legacyCriticalOnly, setLegacyCriticalOnly] = React.useState(false);

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

  const [reviewMultiDocOnly, setReviewMultiDocOnly] = React.useState(false);
  const [reviewCriticalOnly, setReviewCriticalOnly] = React.useState(false);

  const [gridScope, setGridScope] = React.useState<GridScope>("all");
  const [selectedScopeDocTypes, setSelectedScopeDocTypes] = React.useState<
    string[]
  >([]);
  const [gridMode, setGridMode] = React.useState<GridMode>("matrix");

  const [viewerState, setViewerState] = React.useState<ViewerState>(null);
  const [isViewerLoading, setIsViewerLoading] = React.useState(false);
  const [viewerError, setViewerError] = React.useState<string | null>(null);

  const { canReclassifyDocuments } = useDealPermissions(dealId);
  const canDoQc = canReclassifyDocuments;

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

    if (legacyCriticalOnly) {
      results = results.filter((r) => r.severity === "critical");
    }

    return results;
  }, [
    allResults,
    searchText,
    quickFilter,
    selectedDocType,
    hasStructuredDataOnly,
    legacyCriticalOnly,
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
    } catch (e) {
      console.error("Error fetching viewer data", e);
      setViewerError("Ошибка при запросе данных для просмотра документа");
    } finally {
      setIsViewerLoading(false);
    }
  };

  if (!runId) {
    return (
      <div className="rounded-[24px] border border-[var(--border)] bg-[var(--bg-card)] px-5 py-4 text-sm text-[var(--text-secondary)] shadow-sm">
        Нет выбранного запуска анализа. Сначала запустите анализ на вкладке «Обзор».
      </div>
    );
  }

  if (isRunLoading) {
    return (
      <div className="rounded-[24px] border border-[var(--border)] bg-[var(--bg-card)] px-5 py-4 text-sm text-[var(--text-secondary)] shadow-sm">
        Загружаем информацию о запуске анализа…
      </div>
    );
  }

  if (runError) {
    return (
      <div className="rounded-[24px] border border-[color:rgba(161,53,68,0.22)] bg-[color:rgba(161,53,68,0.08)] px-5 py-4 text-sm text-[color:rgb(120,35,46)] shadow-sm">
        Не удалось загрузить информацию о запуске анализа.
      </div>
    );
  }

  const isGridLoading =
    dataSource === "review" ? isReviewLoading : isLegacyLoading;
  const gridError = dataSource === "review" ? reviewError : legacyError;

  if (isGridLoading) {
    return (
      <div className="rounded-[24px] border border-[var(--border)] bg-[var(--bg-card)] px-5 py-4 text-sm text-[var(--text-secondary)] shadow-sm">
        {dataSource === "review"
          ? "Загружаем review-матрицу…"
          : "Загружаем результаты…"}
      </div>
    );
  }

  if (gridError) {
    return (
      <div className="rounded-[24px] border border-[color:rgba(161,53,68,0.22)] bg-[color:rgba(161,53,68,0.08)] px-5 py-4 text-sm text-[color:rgb(120,35,46)] shadow-sm">
        {dataSource === "review"
          ? "Не удалось загрузить review-матрицу."
          : "Не удалось загрузить результаты проверки."}
      </div>
    );
  }

  return (
    <div className="space-y-4 pb-10">
      <section className="rounded-[28px] border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
        <div className="border-b border-[var(--border)] px-5 py-4">
          <div className="inline-flex items-center rounded-full border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">
            DD Grid
          </div>

          <div className="mt-4 flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
            <div className="min-w-0">
              <h1 className="text-[22px] font-semibold tracking-tight text-[var(--text-primary)]">
                Матрица проверок и доказательств
              </h1>
              <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                Просматривайте результаты проверок, переключайтесь между legacy и review
                представлением и открывайте связанные документы в viewer.
              </p>

              <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-[var(--text-muted)]">
                <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-base)] px-2.5 py-1">
                  Сделка: {dealId}
                </span>
                {run && (
                  <>
                    <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-base)] px-2.5 py-1">
                      Run: {run.id}
                    </span>
                    <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-base)] px-2.5 py-1">
                      Статус: {run.status}
                    </span>
                    {run.checks_mode && (
                      <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-base)] px-2.5 py-1">
                        Проверки:{" "}
                        {run.checks_mode === "global_and_doc_type"
                          ? "Плейбук + типы документов"
                          : run.checks_mode === "global_only"
                            ? "Только плейбук"
                            : "Только типы документов"}
                      </span>
                    )}
                    {run.pipeline_strategy && (
                      <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-base)] px-2.5 py-1">
                        Пайплайн: {run.pipeline_strategy}
                      </span>
                    )}
                  </>
                )}
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-[20px] border border-[var(--border-soft)] bg-[var(--bg-base)] p-3">
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
                  Источник данных
                </div>
                <div className="flex flex-wrap gap-2">
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
              </div>

              <div className="rounded-[20px] border border-[var(--border-soft)] bg-[var(--bg-base)] p-3">
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
                  Режим отображения
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant={gridMode === "matrix" ? "primary" : "secondary"}
                    onClick={() => setGridMode("matrix")}
                  >
                    Матрица
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant={gridMode === "list" ? "primary" : "secondary"}
                    onClick={() => setGridMode("list")}
                    disabled={dataSource === "review"}
                    title={
                      dataSource === "review"
                        ? "В review-режиме пока доступна только матрица"
                        : undefined
                    }
                  >
                    Список
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="grid gap-3 px-5 py-4 md:grid-cols-2 xl:grid-cols-4">
          <StatCard label="Документы" value={dataSource === "review" ? reviewSummary.documentCount : uniqueDocCount} />
          <StatCard label="Проверки" value={dataSource === "review" ? reviewSummary.checkCount : scopeResults.length} tone="accent" />
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
            label="Без QC / Unclear"
            value={
              dataSource === "review"
                ? `${reviewSummary.unclearCount}`
                : `${importantCount} / ${unclearCount}`
            }
          />
        </div>
      </section>

      {dataSource === "legacy" && (
        <>
          <SectionCard
            title="Фильтры и экспорт"
            description="Уточните выборку, переключите область проверок и выгрузите текущий набор результатов."
          >
            <div className="space-y-4">
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
                onlyMultiDocument={legacyMultiDocOnly}
                onOnlyMultiDocumentChange={setLegacyMultiDocOnly}
                hasCompositionData={compositionByDocId.size > 0}
                criticalOnly={legacyCriticalOnly}
                onCriticalOnlyChange={setLegacyCriticalOnly}
              />

              <div className="flex flex-col gap-3 rounded-[20px] border border-[var(--border-soft)] bg-[var(--bg-base)] px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
                <div className="text-xs leading-5 text-[var(--text-secondary)]">
                  Важных без QC: <span className="font-semibold text-[var(--text-primary)]">{importantCount}</span>
                  {" · "}
                  Неясных: <span className="font-semibold text-[var(--text-primary)]">{unclearCount}</span>
                  {" · "}
                  Проверок: <span className="font-semibold text-[var(--text-primary)]">{scopeResults.length}</span>
                  {" · "}
                  Документов: <span className="font-semibold text-[var(--text-primary)]">{uniqueDocCount}</span>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
                    Область
                  </span>
                  <Button
                    type="button"
                    size="sm"
                    variant={gridScope === "all" ? "primary" : "secondary"}
                    onClick={() => setGridScope("all")}
                  >
                    Все
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant={gridScope === "global" ? "primary" : "secondary"}
                    onClick={() => setGridScope("global")}
                  >
                    Глобальный плейбук
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant={gridScope === "doctype" ? "primary" : "secondary"}
                    onClick={() => setGridScope("doctype")}
                  >
                    По типу документа
                  </Button>
                </div>
              </div>

              {gridScope === "doctype" && scopeDoctypes.length > 0 && (
                <div className="rounded-[20px] border border-[var(--border-soft)] bg-[var(--bg-base)] px-4 py-3">
                  <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
                    Типы документов
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={resetScopeDocTypes}
                    >
                      Все
                    </Button>

                    {scopeDoctypes.map((dt) => {
                      const checked = selectedScopeDocTypes.includes(dt);

                      return (
                        <label
                          key={dt}
                          className={[
                            "inline-flex cursor-pointer items-center gap-2 rounded-xl border px-3 py-1.5 text-xs transition-colors",
                            checked
                              ? "border-[var(--accent-primary)] bg-[var(--accent-muted)] text-[var(--accent-primary)]"
                              : "border-[var(--border)] bg-[var(--bg-card)] text-[var(--text-secondary)]",
                          ].join(" ")}
                        >
                          <input
                            type="checkbox"
                            className="h-3.5 w-3.5"
                            checked={checked}
                            onChange={() => toggleScopeDocType(dt)}
                          />
                          <span>{dt}</span>
                        </label>
                      );
                    })}
                  </div>
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
            </div>
          </SectionCard>

          <SectionCard
            title="Результаты legacy grid"
            description="Сетка результатов проверки с доступом к Magic Zoom, Evidence Panel и массовым QC-действиям."
          >
            <DDGrid
              results={scopeResults}
              compositionByDocId={compositionByDocId}
              onlyMultiDocument={legacyMultiDocOnly}
              onEyeClick={handleEyeClick}
              onSelectionChange={handleSelectionChange}
              mode={gridMode}
              onOpenAtLocation={openViewerAt}
            />
          </SectionCard>
        </>
      )}

      {dataSource === "review" && (
        <>
          <SectionCard
            title="Фильтры review matrix"
            description="Фильтрация backend review DTO без обратного маппинга в legacy CheckResult[]."
          >
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-3 rounded-[20px] border border-[var(--border-soft)] bg-[var(--bg-base)] px-4 py-3">
                <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-[var(--text-secondary)]">
                  <input
                    type="checkbox"
                    className="h-4 w-4"
                    checked={reviewMultiDocOnly}
                    onChange={(e) => setReviewMultiDocOnly(e.target.checked)}
                  />
                  <span>Только multi-document</span>
                </label>

                <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-[var(--text-secondary)]">
                  <input
                    type="checkbox"
                    className="h-4 w-4"
                    checked={reviewCriticalOnly}
                    onChange={(e) => setReviewCriticalOnly(e.target.checked)}
                  />
                  <span className="font-medium text-[color:rgb(120,35,46)]">
                    Только Critical
                  </span>
                </label>
              </div>

              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <StatCard label="Документов" value={reviewSummary.documentCount} />
                <StatCard label="Проверок" value={reviewSummary.checkCount} tone="accent" />
                <StatCard label="Critical" value={reviewSummary.criticalCount} tone="critical" />
                <StatCard label="Unclear" value={reviewSummary.unclearCount} />
              </div>

              <div className="rounded-[20px] border border-[var(--accent-primary)]/12 bg-[var(--accent-muted)] px-4 py-3 text-sm leading-6 text-[var(--text-secondary)]">
                Review mode рендерит матрицу поверх run-scoped backend DTO. Legacy-фильтры,
                bulk QC, Magic Zoom и export пока остаются только в legacy-режиме, чтобы не
                маппить новую модель обратно в `CheckResult[]`.
              </div>

              <div className="flex flex-wrap items-center gap-4 text-sm text-[var(--text-secondary)]">
                <span>
                  Quarantine:{" "}
                  <span className="font-semibold text-[var(--text-primary)]">
                    {ddMatrix?.quarantine_count ?? 0}
                  </span>
                </span>
                <span>
                  Degraded:{" "}
                  <span className="font-semibold text-[var(--text-primary)]">
                    {ddMatrix?.degraded_count ?? 0}
                  </span>
                </span>
                <span>
                  Evidence validity:{" "}
                  <span className="font-semibold text-[var(--text-primary)]">
                    {ddMatrix?.evidence_validity_rate != null
                      ? `${Math.round(ddMatrix.evidence_validity_rate * 100)}%`
                      : "—"}
                  </span>
                </span>
              </div>
            </div>
          </SectionCard>

          <SectionCard
            title="Review DD Matrix"
            description="Run-scoped матрица документов и проверок для review-режима."
          >
            <DDMatrixGrid
              data={ddMatrix ?? null}
              onOpenAtLocation={openViewerAt}
              onOpenDocument={({ documentId, documentName }) => {
                console.log("Open review document", { documentId, documentName });
              }}
              onSelectionChange={() => {
                // Review bulk actions будут добавлены отдельным инкрементом.
              }}
              multiDocumentOnly={reviewMultiDocOnly}
              criticalOnly={reviewCriticalOnly}
            />
          </SectionCard>
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



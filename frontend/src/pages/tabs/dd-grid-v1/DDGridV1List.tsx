// =============================================================
// src/pages/tabs/dd-grid-v1/DDGridV1List.tsx
// V1-native plain list findings из DD Grid V1 модели.
//
// Отличия от legacy DDReviewListGrid:
// - source of truth — DDGridV1DerivedModel (без legacy адаптера);
// - клик по любой ячейке (кроме checkbox) открывает V1 drawer;
// - колонки: Документ / Тип / Проверка / Результат / Статус / Локация;
// - семантическая сортировка по статусу (needs_review первыми);
// - без хардкодов check_id / doc_type / column_id.
//
// Правила collapse-контракта:
// - список плоский, без группировки;
// - учитывает includePassResults toggle из toolbar.
// =============================================================

import React, {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import { AgGridReact } from "ag-grid-react";
import type {
  ColDef,
  GridApi,
  GridReadyEvent,
  ICellRendererParams,
  SelectionChangedEvent,
  SelectionColumnDef,
  ValueFormatterParams,
  ValueGetterParams,
} from "ag-grid-community";
import { CheckCircle2, HelpCircle, MinusCircle, XCircle } from "lucide-react";

import type { OpenViewerAtFn } from "../../../types";
import type {
  DDGridV1DrawerContentDTO,
  ReviewQcStatus,
} from "../../../types/dealReview";

import {
  resolveDDGridV1DetectionLevel,
  resolveDDGridV1Confidence,
  resolveDDGridV1QualityFlags,
  resolveDDGridV1QcAuditInfo,
  resolveDDGridV1Observability,
  type DDGridV1ObservabilityInfo,
  type DDGridV1QualityFlagItem,
} from "./ddGridV1.drawer";

import type {
  DDGridV1CheckNode,
  DDGridV1DerivedModel,
  DDGridV1MatrixRow,
} from "./ddGridV1.types";
import type { ReviewSelectionItem } from "./ddGridV1.types";

import DDGridV1Drawer from "./DDGridV1Drawer";

import "ag-grid-community/styles/ag-grid.css";
import "../../../styles/ag-theme-legalmas.css";
import { useIsMobile } from "../../../hooks/useIsMobile";

// -------------------------------------------------------------
// Constants
// -------------------------------------------------------------

const GRID_MIN_HEIGHT_PX = 240;
const SELECTION_COLUMN_WIDTH_PX = 52;

// -------------------------------------------------------------
// Row model
// -------------------------------------------------------------

/**
 * Одна строка V1 list — плоское представление одной пары
 * (документ, проверка) с готовыми для рендера полями.
 */
interface V1ListRow {
  /** Уникальный rowId для AG Grid: docId::checkId */
  rowId: string;

  /** Оригинальный V1 row из модели. */
  v1Row: DDGridV1MatrixRow;

  /** Оригинальный check node из V1 иерархии. */
  checkNode: DDGridV1CheckNode;

  /** Drawer content для этой пары (или null, если backend не прислал). */
  drawerContent: DDGridV1DrawerContentDTO | null;

  /** Legacy MatrixCellDTO из адаптера — используется как источник qc_status/qc_comment. */
  legacyCellQcStatus: ReviewQcStatus | null;
  legacyCellQcComment: string | null;

  // ── Готовые для рендера производные поля ──────────────────
  documentName: string;
  docType: string;
  checkName: string;
  displayText: string | null;
  reviewStatus: string | null;
  reviewStatusLabel: string;
  reviewStatusTone: ReviewStatusTone;
  locationText: string;

  // B3 pre-resolved для рендера в колонках
  detectionLevelBadge: string | null;
  confidenceFormatted: string | null;
  confidenceTier: "high" | "medium" | "low" | null;
  qualityFlags: DDGridV1QualityFlagItem[];
  qualityFlagsCount: number;
  qcStatusLabel: string | null;
  qcStatusTone: "success" | "error" | "warning" | "neutral" | null;
  observability: DDGridV1ObservabilityInfo;
}

type ReviewStatusTone =
  | "success"
  | "warning"
  | "muted"
  | "unknown";

// -------------------------------------------------------------
// Semantic label + tone для review_status
// -------------------------------------------------------------

function getReviewStatusMeta(
  status: string | null | undefined,
  tFn: (key: string, options?: Record<string, unknown>) => string,
): {
  label: string;
  tone: ReviewStatusTone;
  sortRank: number;
} {
  if (!status || typeof status !== "string" || status.trim().length === 0) {
    return { label: tFn("reviewStatus.empty"), tone: "unknown", sortRank: 4 };
  }

  const normalized = status.trim();

  switch (normalized) {
    case "needs_review":
      return {
        label: tFn("reviewStatus.needs_review"),
        tone: "warning",
        sortRank: 0,
      };
    case "no_issue_detected":
    case "ok":
      return {
        label: tFn("reviewStatus.no_issue_detected"),
        tone: "success",
        sortRank: 2,
      };
    case "not_applicable":
      return {
        label: tFn("reviewStatus.not_applicable"),
        tone: "muted",
        sortRank: 3,
      };
    case "unclear":
      return {
        label: tFn("reviewStatus.unclear"),
        tone: "warning",
        sortRank: 1,
      };
    default:
      return { label: normalized, tone: "unknown", sortRank: 5 };
  }
}

function getReviewStatusIcon(tone: ReviewStatusTone): React.ReactNode {
  const iconClass = "h-3.5 w-3.5";

  switch (tone) {
    case "success":
      return <CheckCircle2 className={`${iconClass} text-[var(--color-success)]`} aria-hidden />;
    case "warning":
      return <XCircle className={`${iconClass} text-[var(--color-warning)]`} aria-hidden />;
    case "muted":
      return <MinusCircle className={`${iconClass} text-[var(--text-muted)]`} aria-hidden />;
    case "unknown":
    default:
      return <HelpCircle className={`${iconClass} text-[var(--text-faint)]`} aria-hidden />;
  }
}

function getReviewStatusTextToneClass(tone: ReviewStatusTone): string {
  switch (tone) {
    case "success":
      return "status-text-success";
    case "warning":
      return "status-text-warning";
    case "muted":
      return "text-[var(--text-muted)]";
    case "unknown":
    default:
      return "text-[var(--text-faint)]";
  }
}

// -------------------------------------------------------------
// Location text builder
// -------------------------------------------------------------

function buildLocationText(
  drawer: DDGridV1DrawerContentDTO | null,
  tFn: (key: string, options?: Record<string, unknown>) => string,
): string {
  if (!drawer) return "";

  for (const field of drawer.fields ?? []) {
    const parts: string[] = [];
    if (typeof field.location_page === "number") {
      parts.push(tFn("location.pageAbbr", { page: field.location_page }));
    }
    if (
      typeof field.location_clause_ref === "string" &&
      field.location_clause_ref.trim().length > 0
    ) {
      parts.push(field.location_clause_ref.trim());
    }
    if (parts.length > 0) {
      return parts.join(" · ");
    }
  }

  return "";
}

function getQcStatusMeta(
  status: string | null | undefined,
  tFn: (key: string, options?: Record<string, unknown>) => string,
): { label: string | null; tone: "success" | "error" | "warning" | "neutral" | null } {
  if (!status || status === "pending") return { label: null, tone: null };
  switch (status) {
    case "approved":
      return { label: tFn("qc.approved"), tone: "success" };
    case "rejected":
      return { label: tFn("qc.rejected"), tone: "error" };
    case "needs_review":
      return { label: tFn("qc.needs_review"), tone: "warning" };
    default:
      return { label: status, tone: "neutral" };
  }
}

// -------------------------------------------------------------
// Row builder
// -------------------------------------------------------------

/**
 * Строит плоский список V1 list rows из V1 модели.
 * Для каждой пары (документ × check) создаёт одну строку.
 */
function buildV1ListRows(
  model: DDGridV1DerivedModel,
  _rows: DDGridV1MatrixRow[],
  _columns: DDGridV1CheckNode[],
  visibleCheckIds: readonly string[] | null,
  includePassResults: boolean,
  tFn: (key: string, options?: Record<string, unknown>) => string,
): V1ListRow[] {
  // Собираем все check nodes из V1 иерархии
  const allChecks: DDGridV1CheckNode[] = [];
  const seenCheckIds = new Set<string>();

  for (const group of model.globalGroups) {
    for (const check of group.checks) {
      if (!seenCheckIds.has(check.checkId)) {
        seenCheckIds.add(check.checkId);
        allChecks.push(check);
      }
    }
  }
  for (const cls of model.docTypeClasses) {
    for (const t of cls.types) {
      for (const check of t.checks) {
        if (!seenCheckIds.has(check.checkId)) {
          seenCheckIds.add(check.checkId);
          allChecks.push(check);
        }
      }
    }
  }

  const visibleCheckSet = visibleCheckIds
    ? new Set(visibleCheckIds)
    : null;

  const result: V1ListRow[] = [];

  for (const v1Row of model.rows) {
    for (const check of allChecks) {
      if (visibleCheckSet && !visibleCheckSet.has(check.checkId)) continue;

      const segmentId = v1Row.segmentId ?? "_default";
      const drawer =
        model.drawerContents[v1Row.documentId]?.[segmentId]?.[check.checkId] ?? null;

      if (!drawer) continue;

      const statusMeta = getReviewStatusMeta(drawer.review_status, tFn);

      if (
        !includePassResults &&
        (drawer.review_status === "no_issue_detected" ||
          drawer.review_status === "ok")
      ) {
        continue;
      }

      const detectionLevelInfo = resolveDDGridV1DetectionLevel(drawer, tFn); // 🌟 Заменили t на tFn
      const confidenceInfo = resolveDDGridV1Confidence(drawer);
      const qualityFlags = resolveDDGridV1QualityFlags(drawer, tFn); // 🌟 Заменили t на tFn
      const qcAuditInfo = resolveDDGridV1QcAuditInfo(drawer);
      const qcStatusMeta = getQcStatusMeta(qcAuditInfo.status, tFn);
      const observability = resolveDDGridV1Observability(drawer);

      const listRow: V1ListRow = {
        rowId: `${v1Row.documentId}::${check.checkId}`,
        v1Row,
        checkNode: check,
        drawerContent: drawer,
        legacyCellQcStatus: drawer.qc_status ?? null,
        legacyCellQcComment: drawer.qc_comment ?? null,
        documentName: v1Row.filename || tFn("unnamedDocument"),
        docType: v1Row.docType || "—",
        checkName: check.checkName || check.checkId,
        displayText: drawer.display_text?.trim() || null,
        reviewStatus: drawer.review_status ?? null,
        reviewStatusLabel: statusMeta.label,
        reviewStatusTone: statusMeta.tone,
        locationText: buildLocationText(drawer, tFn),
        detectionLevelBadge: detectionLevelInfo.badge,
        confidenceFormatted: confidenceInfo.formatted,
        confidenceTier: confidenceInfo.tier,
        qualityFlags,
        qualityFlagsCount: qualityFlags.length,
        qcStatusLabel: qcStatusMeta.label,
        qcStatusTone: qcStatusMeta.tone,
        observability,
      };

      result.push(listRow);
    }
  }

  return result;
}

// -------------------------------------------------------------
// Comparators
// -------------------------------------------------------------

function compareReviewStatus(
  a: string | null,
  b: string | null,
  tFn: (key: string, options?: Record<string, unknown>) => string,
): number {
  const rankA = getReviewStatusMeta(a, tFn).sortRank;
  const rankB = getReviewStatusMeta(b, tFn).sortRank;
  return rankA - rankB;
}

// -------------------------------------------------------------
// Selection helpers
// -------------------------------------------------------------

function buildSelectionItems(
  event: SelectionChangedEvent<V1ListRow>,
): ReviewSelectionItem[] {
  return event.api.getSelectedNodes().flatMap((node) => {
    const data = node.data;
    if (!data) return [];
    return [
      {
        rowId: data.rowId,
        matrixRowId: `docv1:${data.v1Row.documentId}`,
        checkId: data.checkNode.checkId,
      },
    ];
  });
}

// -------------------------------------------------------------
// Selected drawer state
// -------------------------------------------------------------

interface SelectedDrawerState {
  open: boolean;
  row: V1ListRow | null;
}

// -------------------------------------------------------------
// Props
// -------------------------------------------------------------

export interface DDGridV1ListProps {
  runId: string;
  model: DDGridV1DerivedModel;
  rows: DDGridV1MatrixRow[];
  columns: DDGridV1CheckNode[];

  visibleCheckIds?: readonly string[];
  includePassResults?: boolean;
  visibleExtraColumnIds?: readonly string[];

  onOpenAtLocation?: OpenViewerAtFn;
  onSelectionChange?: (selection: ReviewSelectionItem[]) => void;
  clearSelectionToken?: number;
}

// -------------------------------------------------------------
// Extra columns catalog (публичный API для parent toolbar)
// -------------------------------------------------------------

export interface DDGridV1ExtraColumnMeta {
  id: string;
  label: string;
  description: string;
}

/**
 * Полный список доступных extra колонок.
 * Содержит канонические английские наименования/описания,
 * при отрисовке они автоматически мапятся на i18next через extra.[id].label.
 */
export const DD_GRID_V1_EXTRA_COLUMNS: readonly DDGridV1ExtraColumnMeta[] = [
  {
    id: "detectionLevel",
    label: "Analysis method",
    description: "Detection level: L1 (rules), L2 (LLM), L3 (RAG+LLM), L4 (manual)",
  },
  {
    id: "qcStatus",
    label: "QC Status",
    description: "Manual verification status by legal expert",
  },
  {
    id: "confidence",
    label: "Confidence",
    description: "Model confidence in the result (0.0–1.0)",
  },
  {
    id: "qualityFlags",
    label: "Warnings",
    description: "Technical execution quality flags for the check",
  },
  {
    id: "agentName",
    label: "Agent name",
    description: "Name of the detector or agent that ran the check",
  },
  {
    id: "modelVersion",
    label: "Model version",
    description: "LLM model version",
  },
  {
    id: "executionTime",
    label: "Execution time",
    description: "Check execution duration in milliseconds",
  },
  {
    id: "retryAttempts",
    label: "LLM attempts",
    description: "Number of LLM call retry attempts",
  },
  {
    id: "inputTokens",
    label: "Input tokens",
    description: "LLM input token count",
  },
  {
    id: "outputTokens",
    label: "Output tokens",
    description: "LLM output token count",
  },
] as const;

// -------------------------------------------------------------
// Main component
// -------------------------------------------------------------

export const DDGridV1List: React.FC<DDGridV1ListProps> = ({
  runId,
  model,
  rows,
  columns,
  visibleCheckIds,
  includePassResults = true,
  visibleExtraColumnIds,
  onOpenAtLocation,
  onSelectionChange,
  clearSelectionToken,
}) => {
  const { t } = useTranslation("ddGrid");
  const isMobile = useIsMobile();

  const rootRef = useRef<HTMLDivElement | null>(null);
  const [rootWidth, setRootWidth] = useState<number>(0);
  const [gridApi, setGridApi] = useState<GridApi<V1ListRow> | null>(null);

  const [selectedDrawer, setSelectedDrawer] = useState<SelectedDrawerState>({
    open: false,
    row: null,
  });

  const [activeRowId, setActiveRowId] = useState<string | null>(null);
  const activeRowIdRef = useRef<string | null>(null);

  useEffect(() => {
    activeRowIdRef.current = activeRowId;
  }, [activeRowId]);

  const rowData = useMemo(
    () =>
      buildV1ListRows(
        model,
        rows,
        columns,
        visibleCheckIds ?? null,
        includePassResults,
        t,
      ),
    [model, rows, columns, visibleCheckIds, includePassResults, t],
  );

  useEffect(() => {
    const node = rootRef.current;
    if (!node) return;

    const update = () => {
      setRootWidth(Math.round(node.getBoundingClientRect().width));
    };

    update();

    const ro = new ResizeObserver(() => update());
    ro.observe(node);
    const raf = requestAnimationFrame(update);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, []);

  const closeDrawer = useCallback(() => {
    const previousActiveRowId = activeRowIdRef.current;

    setSelectedDrawer({ open: false, row: null });

    if (!gridApi || !previousActiveRowId) return;

    requestAnimationFrame(() => {
      const node = gridApi.getRowNode(previousActiveRowId);
      if (!node) return;

      try {
        gridApi.ensureNodeVisible(node, "middle");
        gridApi.redrawRows({ rowNodes: [node] });
      } catch {
        /* noop */
      }
    });
  }, [gridApi]);

  const openDrawerForRow = useCallback(
    (row: V1ListRow) => {
      if (!row.drawerContent) {
        return;
      }

      const previousActiveRowId = activeRowIdRef.current;

      setSelectedDrawer({ open: true, row });
      setActiveRowId(row.rowId);
      activeRowIdRef.current = row.rowId;

      if (!gridApi) {
        return;
      }

      requestAnimationFrame(() => {
        const rowIdsToRefresh: string[] = [row.rowId];
        if (previousActiveRowId && previousActiveRowId !== row.rowId) {
          rowIdsToRefresh.push(previousActiveRowId);
        }

        const rowNodes = rowIdsToRefresh
          .map((id) => gridApi.getRowNode(id))
          .filter((node): node is NonNullable<typeof node> => node != null);

        if (rowNodes.length > 0) {
          try {
            gridApi.redrawRows({ rowNodes });
          } catch {
            /* noop */
          }
        }
      });
    },
    [gridApi],
  );

  const defaultColDef = useMemo<ColDef<V1ListRow>>(
    () => ({
      sortable: true,
      filter: true,
      resizable: true,
      suppressHeaderMenuButton: false,
    }),
    [],
  );

  const rowSelection = useMemo(
    () => ({
      mode: "multiRow" as const,
      checkboxes: true,
      headerCheckbox: true,
      selectAll: "filtered" as const,
      enableSelectionWithoutKeys: true,
      enableClickSelection: false,
    }),
    [],
  );

  const selectionColumnDef = useMemo<SelectionColumnDef>(
    () => ({
      width: SELECTION_COLUMN_WIDTH_PX,
      minWidth: SELECTION_COLUMN_WIDTH_PX,
      maxWidth: SELECTION_COLUMN_WIDTH_PX,
      resizable: false,
      sortable: false,
      pinned: "left",
      suppressHeaderMenuButton: true,
      suppressMovable: true,
      lockPosition: "left",
    }),
    [],
  );

  // -----------------------------------------------------------
  // Column defs
  // -----------------------------------------------------------

  const columnDefs = useMemo<ColDef<V1ListRow>[]>(() => {
    const baseColumns: ColDef<V1ListRow>[] = [
      {
        headerName: t("columns.document"),
        field: "documentName",
        minWidth: 280,
        pinned: "left",
        tooltipValueGetter: (params) => params.data?.documentName ?? "",
        cellRenderer: (params: ICellRendererParams<V1ListRow>) => {
          const row = params.data;
          if (!row) return null;
          return (
            <span className="text-xs text-[var(--text-primary)]">
              {row.documentName}
            </span>
          );
        },
      },
      {
        headerName: t("columns.docType"),
        field: "docType",
        minWidth: 160,
        maxWidth: 240,
        tooltipValueGetter: (params) => params.data?.docType ?? "",
        cellRenderer: (params: ICellRendererParams<V1ListRow>) => {
          const row = params.data;
          if (!row) return null;
          return (
            <span className="text-xs text-[var(--text-secondary)]">
              {row.docType}
            </span>
          );
        },
      },
      {
        headerName: t("columns.check"),
        field: "checkName",
        minWidth: 240,
        tooltipValueGetter: (params) => params.data?.checkName ?? "",
        cellRenderer: (params: ICellRendererParams<V1ListRow>) => {
          const row = params.data;
          if (!row) return null;
          return (
            <span className="text-xs font-medium text-[var(--text-primary)]">
              {row.checkName}
            </span>
          );
        },
      },
      {
        headerName: t("columns.result"),
        colId: "displayText",
        minWidth: 320,
        flex: 1,
        valueGetter: (params: ValueGetterParams<V1ListRow>) =>
          params.data?.displayText ?? "",
        tooltipValueGetter: (params) => params.data?.displayText ?? "",
        cellRenderer: (params: ICellRendererParams<V1ListRow>) => {
          const row = params.data;
          if (!row) return null;
          return row.displayText ? (
            <span className="whitespace-normal break-words text-xs leading-5 text-[var(--text-primary)]">
              {row.displayText}
            </span>
          ) : (
            <span className="text-[11px] italic text-[var(--text-faint)]">
              {row.reviewStatus === "no_issue_detected" || row.reviewStatus === "ok"
                ? t("location.noViolations")
                : row.reviewStatus === "not_applicable"
                  ? t("location.notApplicable")
                  : row.reviewStatus === "unclear"
                    ? t("location.unclearResult")
                    : t("location.noData")}
            </span>
          );
        },
      },
      {
        headerName: t("columns.status"),
        colId: "reviewStatus",
        minWidth: 220,
        valueGetter: (params: ValueGetterParams<V1ListRow>) =>
          params.data?.reviewStatus ?? null,
        valueFormatter: (params: ValueFormatterParams<V1ListRow>): string => {
          const status = params.value as string | null;
          return getReviewStatusMeta(status, t).label;
        },
        comparator: (a, b) =>
          compareReviewStatus(a as string | null, b as string | null, t),
        tooltipValueGetter: (params) => {
          const row = params.data;
          if (!row) return "";
          return row.reviewStatusLabel;
        },
        cellRenderer: (params: ICellRendererParams<V1ListRow>) => {
          const row = params.data;
          if (!row) return null;
          const tone = row.reviewStatusTone;
          const textToneClass = getReviewStatusTextToneClass(tone);
          return (
            <div className="flex h-full items-center">
              <span
                className={`inline-flex items-center gap-1 text-[11px] font-medium ${textToneClass}`}
              >
                {getReviewStatusIcon(tone)}
                <span>{row.reviewStatusLabel}</span>
              </span>
            </div>
          );
        },
      },
      {
        headerName: t("columns.location"),
        colId: "locationText",
        minWidth: 200,
        maxWidth: 280,
        valueGetter: (params: ValueGetterParams<V1ListRow>) =>
          params.data?.locationText ?? "",
        tooltipValueGetter: (params) => params.data?.locationText ?? "",
        cellRenderer: (params: ICellRendererParams<V1ListRow>) => {
          const row = params.data;
          if (!row) return null;

          const canOpenViewer = Boolean(row.locationText && onOpenAtLocation);

          if (!canOpenViewer) {
            return (
              <span className="text-xs text-[var(--text-muted)]">
                {row.locationText || "—"}
              </span>
            );
          }

          const handleClick = (e: React.MouseEvent) => {
            e.stopPropagation();

            if (row.drawerContent) {
              const firstField = row.drawerContent.fields?.[0];

              if (firstField) {
                onOpenAtLocation?.({
                  documentId: row.v1Row.documentId,
                  page: firstField.location_page ?? undefined,
                  clauseUid: firstField.location_clause_uid ?? undefined,
                  elementId: undefined,
                  segmentId: undefined,
                  chunkId: undefined,
                  chunkIndex: undefined,
                });
              }
            }
          };

          return (
            <button
              type="button"
              data-skip-row-click="true"
              className="text-xs text-[var(--accent-primary)] hover:underline cursor-pointer transition-colors"
              onClick={handleClick}
              title={t("location.openTooltip")}
            >
              {row.locationText}
            </button>
          );
        },
      },
    ];

    const visibleExtras = new Set(visibleExtraColumnIds ?? []);
    if (visibleExtras.size === 0) {
      return baseColumns;
    }

    const extraColumnsMap: Record<string, ColDef<V1ListRow>> = {
      detectionLevel: {
        headerName: t("extra.detectionLevel.label"),
        colId: "detectionLevel",
        minWidth: 120,
        maxWidth: 150,
        valueGetter: (params: ValueGetterParams<V1ListRow>) =>
          params.data?.detectionLevelBadge ?? "",
        tooltipValueGetter: (params) =>
          params.data?.detectionLevelBadge
            ? t("extra.detectionLevel.tooltip", { method: params.data.detectionLevelBadge })
            : t("extra.detectionLevel.unspecified"),
        cellRenderer: (params: ICellRendererParams<V1ListRow>) => {
          const row = params.data;
          if (!row) return null;
          return (
            <span className="text-xs text-[var(--text-secondary)]">
              {row.detectionLevelBadge || "—"}
            </span>
          );
        },
      },
      qcStatus: {
        headerName: t("extra.qcStatus.label"),
        colId: "qcStatus",
        minWidth: 130,
        maxWidth: 200,
        valueGetter: (params: ValueGetterParams<V1ListRow>) =>
          params.data?.qcStatusLabel ?? "",
        tooltipValueGetter: (params) => params.data?.qcStatusLabel ?? "",
        cellRenderer: (params: ICellRendererParams<V1ListRow>) => {
          const row = params.data;
          if (!row || !row.qcStatusLabel || !row.qcStatusTone) {
            return (
              <span className="text-[11px] text-[var(--text-faint)]">—</span>
            );
          }

          const toneClass =
            row.qcStatusTone === "success"
              ? "status-border-success status-bg-success status-text-success"
              : row.qcStatusTone === "error"
                ? "status-border-error status-bg-error status-text-error"
                : row.qcStatusTone === "warning"
                  ? "status-border-warning status-bg-warning status-text-warning"
                  : "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)]";

          return (
            <div className="flex h-full items-center">
              <span
                className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold ${toneClass}`}
              >
                {row.qcStatusLabel}
              </span>
            </div>
          );
        },
      },
      confidence: {
        headerName: t("extra.confidence.label"),
        colId: "confidence",
        minWidth: 110,
        maxWidth: 130,
        valueGetter: (params: ValueGetterParams<V1ListRow>) =>
          params.data?.confidenceFormatted ?? "",
        tooltipValueGetter: (params) =>
          params.data?.confidenceFormatted
            ? t("extra.confidence.tooltip", { confidence: params.data.confidenceFormatted })
            : "",
        cellRenderer: (params: ICellRendererParams<V1ListRow>) => {
          const row = params.data;
          if (!row || !row.confidenceFormatted || !row.confidenceTier) {
            return (
              <span className="text-[11px] text-[var(--text-faint)]">—</span>
            );
          }
          const toneClass =
            row.confidenceTier === "high"
              ? "status-text-success"
              : row.confidenceTier === "medium"
                ? "status-text-warning"
                : "status-text-error";
          return (
            <span className={`text-xs font-medium ${toneClass}`}>
              {row.confidenceFormatted}
            </span>
          );
        },
      },
      qualityFlags: {
        headerName: t("extra.qualityFlags.label"),
        colId: "qualityFlags",
        minWidth: 160,
        maxWidth: 240,
        valueGetter: (params: ValueGetterParams<V1ListRow>) =>
          params.data?.qualityFlagsCount ?? 0,
        tooltipValueGetter: (params) => {
          const flags = params.data?.qualityFlags ?? [];
          if (flags.length === 0) return "";
          return flags.map((f) => f.label).join(", ");
        },
        cellRenderer: (params: ICellRendererParams<V1ListRow>) => {
          const row = params.data;
          if (!row || row.qualityFlags.length === 0) {
            return (
              <span className="text-[11px] text-[var(--text-faint)]">—</span>
            );
          }
          return (
            <div className="flex flex-wrap gap-1 py-0.5">
              {row.qualityFlags.map((flag) => (
                <span
                  key={flag.key}
                  className="status-border-warning status-bg-warning status-text-warning inline-flex items-center rounded border px-1 py-0 text-[10px] font-medium"
                  title={flag.key}
                >
                  {flag.label}
                </span>
              ))}
            </div>
          );
        },
      },
      agentName: {
        headerName: t("extra.agentName.label"),
        colId: "agentName",
        minWidth: 160,
        maxWidth: 220,
        valueGetter: (params: ValueGetterParams<V1ListRow>) =>
          params.data?.observability.agentName ?? "",
        tooltipValueGetter: (params) =>
          params.data?.observability.agentName ?? "",
        cellRenderer: (params: ICellRendererParams<V1ListRow>) => {
          const row = params.data;
          const value = row?.observability.agentName;
          return value ? (
            <span className="font-mono text-[11px] text-[var(--text-secondary)]">
              {value}
            </span>
          ) : (
            <span className="text-[11px] text-[var(--text-faint)]">—</span>
          );
        },
      },
      modelVersion: {
        headerName: t("extra.modelVersion.label"),
        colId: "modelVersion",
        minWidth: 160,
        maxWidth: 220,
        valueGetter: (params: ValueGetterParams<V1ListRow>) =>
          params.data?.observability.modelVersion ?? "",
        tooltipValueGetter: (params) =>
          params.data?.observability.modelVersion ?? "",
        cellRenderer: (params: ICellRendererParams<V1ListRow>) => {
          const row = params.data;
          const value = row?.observability.modelVersion;
          return value ? (
            <span className="font-mono text-[11px] text-[var(--text-secondary)]">
              {value}
            </span>
          ) : (
            <span className="text-[11px] text-[var(--text-faint)]">—</span>
          );
        },
      },
      executionTime: {
        headerName: t("extra.executionTime.label"),
        colId: "executionTime",
        minWidth: 100,
        maxWidth: 130,
        valueGetter: (params: ValueGetterParams<V1ListRow>) =>
          params.data?.observability.executionTimeMs ?? null,
        tooltipValueGetter: (params) =>
          params.data?.observability.executionTimeFormatted ?? "",
        cellRenderer: (params: ICellRendererParams<V1ListRow>) => {
          const row = params.data;
          const value = row?.observability.executionTimeFormatted;
          return value ? (
            <span className="text-xs text-[var(--text-secondary)]">
              {value}
            </span>
          ) : (
            <span className="text-[11px] text-[var(--text-faint)]">—</span>
          );
        },
      },
      retryAttempts: {
        headerName: t("extra.retryAttempts.label"),
        colId: "retryAttempts",
        minWidth: 90,
        maxWidth: 110,
        valueGetter: (params: ValueGetterParams<V1ListRow>) =>
          params.data?.observability.retryAttempts ?? null,
        cellRenderer: (params: ICellRendererParams<V1ListRow>) => {
          const row = params.data;
          const value = row?.observability.retryAttempts;
          return value !== null && value !== undefined ? (
            <span className="text-xs text-[var(--text-secondary)]">
              {value}
            </span>
          ) : (
            <span className="text-[11px] text-[var(--text-faint)]">—</span>
          );
        },
      },
      inputTokens: {
        headerName: t("extra.inputTokens.label"),
        colId: "inputTokens",
        minWidth: 120,
        maxWidth: 150,
        valueGetter: (params: ValueGetterParams<V1ListRow>) =>
          params.data?.observability.inputTokens ?? null,
        cellRenderer: (params: ICellRendererParams<V1ListRow>) => {
          const row = params.data;
          const value = row?.observability.inputTokens;
          return value !== null && value !== undefined ? (
            <span className="text-xs text-[var(--text-secondary)]">
              {value.toLocaleString()}
            </span>
          ) : (
            <span className="text-[11px] text-[var(--text-faint)]">—</span>
          );
        },
      },
      outputTokens: {
        headerName: t("extra.outputTokens.label"),
        colId: "outputTokens",
        minWidth: 120,
        maxWidth: 150,
        valueGetter: (params: ValueGetterParams<V1ListRow>) =>
          params.data?.observability.outputTokens ?? null,
        cellRenderer: (params: ICellRendererParams<V1ListRow>) => {
          const row = params.data;
          const value = row?.observability.outputTokens;
          return value !== null && value !== undefined ? (
            <span className="text-xs text-[var(--text-secondary)]">
              {value.toLocaleString()}
            </span>
          ) : (
            <span className="text-[11px] text-[var(--text-faint)]">—</span>
          );
        },
      },
    };

    const orderedExtras: ColDef<V1ListRow>[] = [];
    for (const meta of DD_GRID_V1_EXTRA_COLUMNS) {
      if (visibleExtras.has(meta.id)) {
        const colDef = extraColumnsMap[meta.id];
        if (colDef) orderedExtras.push(colDef);
      }
    }

    return [...baseColumns, ...orderedExtras];
  }, [onOpenAtLocation, visibleExtraColumnIds, t]);

  // -----------------------------------------------------------
  // Selection
  // -----------------------------------------------------------

  const handleSelectionChanged = useCallback(
    (event: SelectionChangedEvent<V1ListRow>) => {
      if (!onSelectionChange) return;
      onSelectionChange(buildSelectionItems(event));
    },
    [onSelectionChange],
  );

  const handleGridReady = useCallback((event: GridReadyEvent<V1ListRow>) => {
    setGridApi(event.api);
    requestAnimationFrame(() => {
      try {
        event.api.sizeColumnsToFit();
      } catch {
        /* noop */
      }
    });
  }, []);

  useLayoutEffect(() => {
    if (!gridApi) return;
    const id = requestAnimationFrame(() => {
      try {
        gridApi.sizeColumnsToFit();
      } catch {
        /* noop */
      }
    });
    return () => cancelAnimationFrame(id);
  }, [gridApi, rootWidth, rowData.length, columnDefs.length]);

  const lastClearTokenRef = useRef<number | undefined>(clearSelectionToken);
  useEffect(() => {
    if (!gridApi) return;
    if (clearSelectionToken === lastClearTokenRef.current) return;
    lastClearTokenRef.current = clearSelectionToken;
    try {
      gridApi.deselectAll();
    } catch {
      /* noop */
    }
  }, [gridApi, clearSelectionToken]);

  if (!rowData.length) {
    return (
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-6 text-center text-sm text-[var(--text-secondary)] shadow-sm">
        {t("emptyState")}
      </div>
    );
  }

  const isDrawerOpen = selectedDrawer.open && selectedDrawer.row !== null;

  return (
    <div
      ref={rootRef}
      className={`flex gap-4 ${isMobile ? "" : "h-full min-h-0"}`}
    >
      <div
        className={`flex min-w-0 flex-col rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm transition-all duration-200 ${
          isMobile ? "w-full" : "h-full min-h-0 overflow-hidden"
        } ${isDrawerOpen && !isMobile ? "flex-[2_2_0%]" : "flex-1"}`}
      >
        <div
          className={
            isMobile ? "" : "min-h-0 flex-1 overflow-hidden"
          }
        >
          <div
            className={`ag-theme-legalmas w-full ${isMobile ? "" : "h-full"}`}
            style={isMobile ? undefined : { minHeight: GRID_MIN_HEIGHT_PX }}
          >
            <AgGridReact<V1ListRow>
              theme="legacy"
              rowData={rowData}
              columnDefs={columnDefs}
              defaultColDef={defaultColDef}
              rowSelection={rowSelection}
              selectionColumnDef={selectionColumnDef}
              suppressCellFocus
              tooltipShowDelay={200}
              onSelectionChanged={handleSelectionChanged}
              onGridReady={handleGridReady}
              onCellClicked={(event) => {
                if (event.column.getColId() === "ag-Grid-SelectionColumn") {
                  return;
                }
                const target = event.event?.target as HTMLElement | null;
                if (target?.closest("[data-skip-row-click]")) {
                  return;
                }
                if (event.data) {
                  openDrawerForRow(event.data);
                }
              }}
              getRowClass={(params) =>
                params.data && params.data.rowId === activeRowIdRef.current
                  ? "ag-row-active-v1"
                  : ""
              }
              getRowId={(params) => params.data.rowId}
              domLayout={isMobile ? "autoHeight" : "normal"}
            />
          </div>
        </div>
      </div>

      {isDrawerOpen && (
        <div
          className={
            isMobile
              ? "fixed inset-0 z-50 flex flex-col bg-[var(--bg-card)]"
              : "flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm"
          }
          style={
            isMobile
              ? undefined
              : { width: "clamp(360px, 38%, 640px)" }
          }
        >
          {isMobile && (
            <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-4 py-3">
              <button
                type="button"
                onClick={closeDrawer}
                className="text-sm font-medium text-[var(--accent-primary)]"
              >
                {t("backButton")}
              </button>

              <div className="text-sm font-semibold text-[var(--text-primary)]">
                {t("details")}
              </div>

              <div className="w-12" />
            </div>
          )}

          <DDGridV1Drawer
            open={true}
            onClose={closeDrawer}
            runId={runId}
            documentId={selectedDrawer.row?.v1Row.documentId ?? null}
            documentName={selectedDrawer.row?.documentName ?? null}
            drawerContent={selectedDrawer.row?.drawerContent ?? null}
            onOpenInViewer={
              onOpenAtLocation
                ? (payload) =>
                    onOpenAtLocation({
                      documentId: payload.documentId,
                      page: payload.page ?? undefined,
                      clauseUid: payload.clauseUid ?? undefined,
                      elementId: undefined,
                      segmentId: payload.segmentId ?? undefined,
                      chunkId: payload.chunkId ?? undefined,
                      chunkIndex: payload.chunkIndex ?? undefined,
                    })
                : undefined
            }
          />
        </div>
      )}
    </div>
  );
};

export default DDGridV1List;



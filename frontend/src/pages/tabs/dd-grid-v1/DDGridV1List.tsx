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
  ReviewGridRow,
  ReviewCheckColumn,
  ReviewSelectionItem,
} from "../grid/reviewGrid.types";

import type {
  DDGridV1CheckNode,
  DDGridV1DerivedModel,
  DDGridV1MatrixRow,
} from "./ddGridV1.types";

import DDGridV1Drawer from "./DDGridV1Drawer";

import "ag-grid-community/styles/ag-grid.css";
import "../../../styles/ag-theme-legalmas.css";

// -------------------------------------------------------------
// Constants
// -------------------------------------------------------------

const GRID_MIN_HEIGHT_PX = 240;
const GRID_MIN_WIDTH_PX = 1000;
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

function getReviewStatusMeta(status: string | null | undefined): {
  label: string;
  tone: ReviewStatusTone;
  sortRank: number;
} {
  if (!status || typeof status !== "string" || status.trim().length === 0) {
    return { label: "—", tone: "unknown", sortRank: 4 };
  }

  const normalized = status.trim();

  switch (normalized) {
    case "needs_review":
      return {
        label: "Требует внимания юриста",
        tone: "warning",
        sortRank: 0, // выше всех
      };
    case "no_issue_detected":
    case "ok":
      return {
        label: "Без замечаний",
        tone: "success",
        sortRank: 2,
      };
    case "not_applicable":
      return {
        label: "Неприменимо",
        tone: "muted",
        sortRank: 3,
      };
    case "unclear":
      return {
        label: "Результат не определён",
        tone: "warning",
        sortRank: 1, // между needs_review и ok
      };
    default:
      return { label: normalized, tone: "unknown", sortRank: 5 };
  }
}

function getReviewStatusIcon(tone: ReviewStatusTone): React.ReactNode {
  const iconClass = "h-3.5 w-3.5";

  switch (tone) {
    case "success":
      return <CheckCircle2 className={`${iconClass} text-emerald-600`} aria-hidden />;
    case "warning":
      return <XCircle className={`${iconClass} text-amber-600`} aria-hidden />;
    case "muted":
      return <MinusCircle className={`${iconClass} text-gray-500`} aria-hidden />;
    case "unknown":
    default:
      return <HelpCircle className={`${iconClass} text-gray-400`} aria-hidden />;
  }
}

function getReviewStatusTextToneClass(tone: ReviewStatusTone): string {
  switch (tone) {
    case "success":
      return "text-emerald-700 dark:text-emerald-300";
    case "warning":
      return "text-amber-700 dark:text-amber-300";
    case "muted":
      return "text-gray-500 dark:text-gray-400";
    case "unknown":
    default:
      return "text-gray-400 dark:text-gray-500";
  }
}

// -------------------------------------------------------------
// Location text builder
// -------------------------------------------------------------

function buildLocationText(drawer: DDGridV1DrawerContentDTO | null): string {
  if (!drawer) return "";

  // Пробуем взять первый доступный location из fields (все они обычно
  // указывают на одно и то же место в документе)
  for (const field of drawer.fields ?? []) {
    const parts: string[] = [];
    if (typeof field.location_page === "number") {
      parts.push(`стр. ${field.location_page}`);
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
): { label: string | null; tone: "success" | "error" | "warning" | "neutral" | null } {
  if (!status || status === "pending") return { label: null, tone: null };
  switch (status) {
    case "approved":
      return { label: "Одобрено", tone: "success" };
    case "rejected":
      return { label: "Отклонено", tone: "error" };
    case "needs_review":
      return { label: "Нужна проверка", tone: "warning" };
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
  legacyRows: ReviewGridRow[],
  legacyColumns: ReviewCheckColumn[],
  visibleCheckIds: readonly string[] | null,
  includePassResults: boolean,
): V1ListRow[] {
  // Индекс legacy row → qc_status/qc_comment по (documentId, checkId)
  const legacyRowByDocId = new Map<string, ReviewGridRow>();
  for (const row of legacyRows) {
    legacyRowByDocId.set(row.documentId, row);
  }

  // Индекс legacy column для metadata (не критично)
  void legacyColumns;

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
    const legacyRow = legacyRowByDocId.get(v1Row.documentId);

    for (const check of allChecks) {
      if (visibleCheckSet && !visibleCheckSet.has(check.checkId)) continue;

      const drawer =
        model.drawerContents[v1Row.documentId]?.[check.checkId] ?? null;

      // Если drawer нет для этой пары — не создаём строку
      // (значит check не выполнялся для этого документа)
      if (!drawer) continue;

      const statusMeta = getReviewStatusMeta(drawer.review_status);

      // includePassResults toggle: если false — скрываем "OK" статусы
      if (
        !includePassResults &&
        (drawer.review_status === "no_issue_detected" ||
          drawer.review_status === "ok")
      ) {
        continue;
      }

      const legacyCell = legacyRow?.cellsByCheckId[check.checkId];

      const detectionLevelInfo = resolveDDGridV1DetectionLevel(drawer);
      const confidenceInfo = resolveDDGridV1Confidence(drawer);
      const qualityFlags = resolveDDGridV1QualityFlags(drawer);
      const qcAuditInfo = resolveDDGridV1QcAuditInfo(drawer);
      const qcStatusMeta = getQcStatusMeta(qcAuditInfo.status);
      const observability = resolveDDGridV1Observability(drawer);

      const listRow: V1ListRow = {
        rowId: `${v1Row.documentId}::${check.checkId}`,
        v1Row,
        checkNode: check,
        drawerContent: drawer,
        legacyCellQcStatus: legacyCell?.qc_status ?? null,
        legacyCellQcComment: legacyCell?.qc_comment ?? null,
        documentName: v1Row.filename || "[no name]",
        docType: v1Row.docType || "—",
        checkName: check.checkName || check.checkId,
        displayText: drawer.display_text?.trim() || null,
        reviewStatus: drawer.review_status ?? null,
        reviewStatusLabel: statusMeta.label,
        reviewStatusTone: statusMeta.tone,
        locationText: buildLocationText(drawer),
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

function compareReviewStatus(a: string | null, b: string | null): number {
  const rankA = getReviewStatusMeta(a).sortRank;
  const rankB = getReviewStatusMeta(b).sortRank;
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
  rows: ReviewGridRow[];
  columns: ReviewCheckColumn[];

  /**
   * Если задан — показываем только эти check_ids.
   * Используется для интеграции с "checksScope" фильтром (все /
   * только глобальные / только по типу документа).
   */
  visibleCheckIds?: readonly string[];

  /**
   * Если false — скрываем строки со статусом "no_issue_detected" / "ok".
   * Управляется через toolbar toggle "Скрыть pass".
   */
  includePassResults?: boolean;

  /**
   * Список ID дополнительных технических колонок, которые нужно показать.
   * Управляется через toolbar панель "Дополнительные данные".
   * Пустой массив / undefined — показываем только базовые колонки.
   */
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
 * Parent (toolbar) использует этот массив для рендера чекбоксов выбора.
 */
export const DD_GRID_V1_EXTRA_COLUMNS: readonly DDGridV1ExtraColumnMeta[] = [
  {
    id: "detectionLevel",
    label: "Метод анализа",
    description: "Уровень детекции: L1 (правила), L2 (LLM), L3 (RAG+LLM), L4 (ручная)",
  },
  {
    id: "qcStatus",
    label: "QC",
    description: "Статус ручной проверки юристом",
  },
  {
    id: "confidence",
    label: "Уверенность",
    description: "Уверенность модели в результате (0.0–1.0)",
  },
  {
    id: "qualityFlags",
    label: "Предупреждения",
    description: "Технические флаги качества выполнения проверки",
  },
  {
    id: "agentName",
    label: "Агент",
    description: "Имя детектора / агента, выполнившего проверку",
  },
  {
    id: "modelVersion",
    label: "Модель",
    description: "Версия LLM модели",
  },
  {
    id: "executionTime",
    label: "Время выполнения",
    description: "Длительность выполнения проверки в мс",
  },
  {
    id: "retryAttempts",
    label: "Попытки LLM",
    description: "Количество попыток вызова LLM",
  },
  {
    id: "inputTokens",
    label: "Input tokens",
    description: "Количество входных токенов LLM",
  },
  {
    id: "outputTokens",
    label: "Output tokens",
    description: "Количество выходных токенов LLM",
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
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [rootWidth, setRootWidth] = useState<number>(0);
  const [gridApi, setGridApi] = useState<GridApi<V1ListRow> | null>(null);

  const [selectedDrawer, setSelectedDrawer] = useState<SelectedDrawerState>({
    open: false,
    row: null,
  });

  // ID активной строки для визуальной подсветки.
  // Ref используется в getRowClass, потому что AG Grid не пересоздаёт
  // callback при изменении React state — closure остаётся stale.
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
      ),
    [model, rows, columns, visibleCheckIds, includePassResults],
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
    setActiveRowId(null);
    activeRowIdRef.current = null;

    if (!gridApi || !previousActiveRowId) return;

    requestAnimationFrame(() => {
      const node = gridApi.getRowNode(previousActiveRowId);
      if (node) {
        try {
          gridApi.redrawRows({ rowNodes: [node] });
        } catch {
          /* noop */
        }
      }
    });
  }, [gridApi]);

  const openDrawerForRow = useCallback(
    (row: V1ListRow) => {
      if (!row.drawerContent) return;

      // Сохраняем ID предыдущей активной строки, чтобы принудительно
      // обновить её className в AG Grid (иначе выделение не спадёт).
      const previousActiveRowId = activeRowIdRef.current;

      setSelectedDrawer({ open: true, row });
      setActiveRowId(row.rowId);
      activeRowIdRef.current = row.rowId;

      if (!gridApi) return;

      // Redraw откладываем на следующий кадр, чтобы React успел закоммитить
      // новый activeRowId и getRowClass прочитал актуальное значение из ref.
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
        headerName: "Документ",
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
        headerName: "Тип документа",
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
        headerName: "Проверка",
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
        headerName: "Результат",
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
              Результат не сформирован
            </span>
          );
        },
      },
      {
        headerName: "Статус",
        colId: "reviewStatus",
        minWidth: 220,
        valueGetter: (params: ValueGetterParams<V1ListRow>) =>
          params.data?.reviewStatus ?? null,
        valueFormatter: (params: ValueFormatterParams<V1ListRow>): string => {
          const status = params.value as string | null;
          return getReviewStatusMeta(status).label;
        },
        comparator: (a, b) =>
          compareReviewStatus(a as string | null, b as string | null),
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
        headerName: "Локация",
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
                const pageMatch =
                  firstField.location_clause_ref?.match(/стр\.?\s*(\d+)/i);
                const page =
                  firstField.location_page ??
                  (pageMatch ? parseInt(pageMatch[1], 10) : undefined);

                onOpenAtLocation?.({
                  documentId: row.v1Row.documentId,
                  page: page ?? undefined,
                  clauseUid: firstField.location_clause_ref ?? undefined,
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
              className="text-xs text-[var(--accent-primary)] hover:underline"
              onClick={handleClick}
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

    // Все возможные extra колонки, ключ = colId (совпадает с DD_GRID_V1_EXTRA_COLUMNS.id)
    const extraColumnsMap: Record<string, ColDef<V1ListRow>> = {
      detectionLevel: {
        headerName: "Метод анализа",
        colId: "detectionLevel",
        minWidth: 120,
        maxWidth: 150,
        valueGetter: (params: ValueGetterParams<V1ListRow>) =>
          params.data?.detectionLevelBadge ?? "",
        tooltipValueGetter: (params) =>
          params.data?.detectionLevelBadge
            ? `Метод анализа: ${params.data.detectionLevelBadge}`
            : "Метод анализа не определён",
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
        headerName: "QC",
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
              ? "border-emerald-500/40 bg-emerald-100 text-emerald-900 dark:border-emerald-700/60 dark:bg-emerald-900/40 dark:text-emerald-100"
              : row.qcStatusTone === "error"
                ? "border-red-500/40 bg-red-100 text-red-900 dark:border-red-700/60 dark:bg-red-900/40 dark:text-red-100"
                : row.qcStatusTone === "warning"
                  ? "border-amber-500/40 bg-amber-100 text-amber-900 dark:border-amber-700/60 dark:bg-amber-900/40 dark:text-amber-100"
                  : "border-gray-400 bg-gray-50 text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100";

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
        headerName: "Уверенность",
        colId: "confidence",
        minWidth: 110,
        maxWidth: 130,
        valueGetter: (params: ValueGetterParams<V1ListRow>) =>
          params.data?.confidenceFormatted ?? "",
        tooltipValueGetter: (params) =>
          params.data?.confidenceFormatted
            ? `Уверенность модели: ${params.data.confidenceFormatted}`
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
              ? "text-emerald-700 dark:text-emerald-300"
              : row.confidenceTier === "medium"
                ? "text-amber-700 dark:text-amber-300"
                : "text-red-700 dark:text-red-300";
          return (
            <span className={`text-xs font-medium ${toneClass}`}>
              {row.confidenceFormatted}
            </span>
          );
        },
      },
      qualityFlags: {
        headerName: "Предупреждения",
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
                  className="inline-flex items-center rounded border border-amber-400 bg-amber-100 px-1 py-0 text-[10px] font-medium text-amber-900 dark:border-amber-600 dark:bg-amber-900/40 dark:text-amber-200"
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
        headerName: "Агент",
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
        headerName: "Модель",
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
        headerName: "Время",
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
        headerName: "Retries",
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
        headerName: "Input tokens",
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
        headerName: "Output tokens",
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

    // Сохраняем порядок из DD_GRID_V1_EXTRA_COLUMNS
    const orderedExtras: ColDef<V1ListRow>[] = [];
    for (const meta of DD_GRID_V1_EXTRA_COLUMNS) {
      if (visibleExtras.has(meta.id)) {
        const colDef = extraColumnsMap[meta.id];
        if (colDef) orderedExtras.push(colDef);
      }
    }

    return [...baseColumns, ...orderedExtras];
  }, [onOpenAtLocation, visibleExtraColumnIds]);

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
        // noop
      }
    });
  }, []);

  useLayoutEffect(() => {
    if (!gridApi) return;
    const id = requestAnimationFrame(() => {
      try {
        gridApi.sizeColumnsToFit();
      } catch {
        // noop
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
      // noop
    }
  }, [gridApi, clearSelectionToken]);

  if (!rowData.length) {
    return (
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-6 text-center text-sm text-[var(--text-secondary)] shadow-sm">
        По выбранным параметрам в DD Grid ничего не найдено.
      </div>
    );
  }

  return (
    <>
      <div
        ref={rootRef}
        className="flex h-full min-h-0 flex-col rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm"
      >
        <div className="min-h-0 flex-1 overflow-hidden">
          <div
            className="ag-theme-legalmas h-full w-full"
            style={{
              minHeight: GRID_MIN_HEIGHT_PX,
              minWidth: GRID_MIN_WIDTH_PX,
            }}
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
                // Игнорируем клик по selection колонке (checkbox)
                if (event.column.getColId() === "ag-Grid-SelectionColumn") {
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
              domLayout="normal"
            />
          </div>
        </div>
      </div>

      <DDGridV1Drawer
        open={selectedDrawer.open}
        onClose={closeDrawer}
        runId={runId}
        documentId={selectedDrawer.row?.v1Row.documentId ?? null}
        documentName={selectedDrawer.row?.documentName ?? null}
        drawerContent={selectedDrawer.row?.drawerContent ?? null}
        currentQcStatus={selectedDrawer.row?.legacyCellQcStatus ?? null}
        currentQcComment={selectedDrawer.row?.legacyCellQcComment ?? null}
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
    </>
  );
};

export default DDGridV1List;



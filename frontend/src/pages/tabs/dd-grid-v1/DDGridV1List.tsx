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

  onOpenAtLocation?: OpenViewerAtFn;
  onSelectionChange?: (selection: ReviewSelectionItem[]) => void;
  clearSelectionToken?: number;
}

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

  // ID активной строки для визуальной подсветки
  const [activeRowId, setActiveRowId] = useState<string | null>(null);

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
    setSelectedDrawer({ open: false, row: null });
    setActiveRowId(null);
  }, []);

  const openDrawerForRow = useCallback((row: V1ListRow) => {
    if (!row.drawerContent) return;
    setSelectedDrawer({ open: true, row });
    setActiveRowId(row.rowId);
  }, []);

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

  const columnDefs = useMemo<ColDef<V1ListRow>[]>(
    () => [
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
    ],
    [onOpenAtLocation, openDrawerForRow],
  );

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
                params.data && params.data.rowId === activeRowId
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



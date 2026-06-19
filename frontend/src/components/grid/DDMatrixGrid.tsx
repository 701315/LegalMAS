// =============================================================
// src/components/grid/DDMatrixGrid.tsx
// Review DD Matrix (run-scoped документ × проверка).
// Pure presentational grid: принимает готовые normalized rows
// от domain layer, а не строит их сам.
//
// Layout contract (P8.8d):
// - domLayout="normal" — AG Grid scroll внутри viewport.
// - header таблицы sticky наверху viewport.
// - контейнер получает h-full от родителя.
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
  ITooltipParams,
  SelectionChangedEvent,
  ValueFormatterParams,
  ValueGetterParams,
} from "ag-grid-community";

import type { ClassificationLevel, OpenViewerAtFn } from "../../types";
import type { MatrixCellDTO } from "../../types/dealReview";

import { SeverityBadge } from "../ui/SeverityBadge";
import { ClassificationBadge } from "../ui/ClassificationBadge";
import { QcStatusBadge } from "../ui/QcStatusBadge";
import { getCompositionBadgeDataFromMeta } from "../../utils/compositionHelpers";
import DDMatrixCellDetails, {
  type MatrixCellDetailsCell,
} from "./DDMatrixCellDetails";

import type {
  ReviewGridRow,
  ReviewCheckColumn,
  ReviewSelectionItem,
} from "../../pages/tabs/grid/reviewGrid.types";

import {
  mapReviewCellToDetailsCell,
  getCellPrimaryText,
  getCellSeverity,
  getCellStatusText,
  buildCellTooltip,
  formatRiskCellValue,
} from "./reviewCellDetails.mapper";

import "ag-grid-community/styles/ag-grid.css";
import "../../styles/ag-theme-legalmas.css";

const MATRIX_MIN_HEIGHT_PX = 240;

type MatrixGridRow = ReviewGridRow & {
  [key: `risk_${string}`]: MatrixCellDTO | undefined;
};

function toMatrixGridRow(row: ReviewGridRow): MatrixGridRow {
  const riskCells = Object.entries(row.cellsByCheckId).reduce<
    Record<`risk_${string}`, MatrixCellDTO | undefined>
  >((acc, [checkId, cell]) => {
    acc[`risk_${checkId}`] = cell;
    return acc;
  }, {} as Record<`risk_${string}`, MatrixCellDTO | undefined>);

  return {
    ...row,
    ...riskCells,
  };
}

function getRowCompositionBadgeData(row: ReviewGridRow) {
  if (row.isMultiDocument == null && row.segmentCount == null) {
    return getCompositionBadgeDataFromMeta(null);
  }

  return getCompositionBadgeDataFromMeta({
    composition_type: row.isMultiDocument ? "multi" : "single",
    segment_count: row.segmentCount ?? 1,
    primary_segment_label: row.primarySegmentLabel ?? null,
    primary_segment_id: null,
    is_composite_file: false,
  });
}

/**
 * Ключ для AG Grid change detection.
 * Включает canonical display semantics чтобы при пересчёте
 * display_text ячейка корректно перерисовывалась.
 */
function buildRiskCellDiffKey(
  cell: MatrixCellDTO | null | undefined,
): string | null {
  if (!cell) return null;
  return [
    cell.result ?? "",
    cell.severity ?? "",
    cell.qc_status ?? "",
    cell.confidence ?? "",
    cell.display_text ?? "",
    cell.review_status ?? "",
    cell.needs_manual_review ? "1" : "0",
    cell.ui_mode ?? "",
  ].join("|");
}

function areDetailsCellsEquivalent(
  a: MatrixCellDetailsCell | null | undefined,
  b: MatrixCellDetailsCell | null | undefined,
): boolean {
  if (a === b) return true;
  if (!a || !b) return false;
  return JSON.stringify(a) === JSON.stringify(b);
}

export interface DDMatrixGridProps {
  runId: string;
  rows: ReviewGridRow[];
  columns: ReviewCheckColumn[];
  onOpenAtLocation?: OpenViewerAtFn;
  onOpenDocument?: (params: {
    documentId: string;
    documentName?: string | null;
  }) => void;
  onOpenCell?: (params: {
    documentId: string;
    documentName?: string | null;
    checkId: string;
    checkName?: string | null;
    cell: MatrixCellDetailsCell;
  }) => void;
  onSelectionChange?: (selection: ReviewSelectionItem[]) => void;
  clearSelectionToken?: number;
}

/**
 * rowId добавлен для корректной идентификации ячейки в segment-based grid.
 * В отличие от documentId, rowId уникален для каждого сегмента одного файла.
 */
interface SelectedCellState {
  open: boolean;
  rowId: string | null;
  documentId: string | null;
  documentName: string | null;
  checkId: string | null;
  checkName: string | null;
  cell: MatrixCellDetailsCell | null;
}

function getHeaderTooltip(meta: ReviewCheckColumn): string {
  return [
    meta.checkName,
    meta.origin ? `Источник: ${meta.origin}` : null,
    meta.severity ? `Severity baseline: ${meta.severity}` : null,
  ]
    .filter(Boolean)
    .join("\n");
}

function buildSelectionItems(
  event: SelectionChangedEvent<MatrixGridRow>,
): ReviewSelectionItem[] {
  return event.api
    .getSelectedNodes()
    .flatMap((node) => {
      const data = node.data;
      if (!data?.rowId) {
        return [];
      }

      return [
        {
          rowId: data.rowId,
        },
      ];
    });
}

export const DDMatrixGrid: React.FC<DDMatrixGridProps> = ({
  runId,
  rows,
  columns,
  onOpenAtLocation,
  onOpenDocument,
  onOpenCell,
  onSelectionChange,
  clearSelectionToken,
}) => {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [rootWidth, setRootWidth] = useState<number>(0);
  const [gridApi, setGridApi] = useState<GridApi<MatrixGridRow> | null>(null);

  const [selectedCell, setSelectedCell] = useState<SelectedCellState>({
    open: false,
    rowId: null,
    documentId: null,
    documentName: null,
    checkId: null,
    checkName: null,
    cell: null,
  });

  const rowData = useMemo<MatrixGridRow[]>(
    () => rows.map(toMatrixGridRow),
    [rows],
  );

  // Валидация по rowId — корректно для segment-based grid,
  // где один documentId может давать несколько строк (сегментов).
  const isSelectedCellValid =
    selectedCell.open &&
    selectedCell.rowId != null &&
    selectedCell.checkId != null &&
    rows.some((row) => row.rowId === selectedCell.rowId) &&
    columns.some((col) => col.checkId === selectedCell.checkId);

  const selectedCellRef = useRef<SelectedCellState>(selectedCell);
  useEffect(() => {
    selectedCellRef.current = selectedCell;
  }, [selectedCell]);

  // Обновляем drawer при изменении данных строки/колонки.
  // Ищем по rowId, а не documentId — иначе при segment grid
  // можно попасть на другой сегмент того же файла.
  useEffect(() => {
    const sc = selectedCellRef.current;
    if (!sc.open || !sc.rowId || !sc.checkId) return;

    const currentRow = rows.find((row) => row.rowId === sc.rowId);
    if (!currentRow) return;

    const currentCell = currentRow.cellsByCheckId[sc.checkId];
    if (!currentCell) return;

    const currentColumn = columns.find((col) => col.checkId === sc.checkId);
    if (!currentColumn) return;

    const freshDetailsCell = mapReviewCellToDetailsCell(
      currentRow,
      currentColumn,
      currentCell,
    );

    setSelectedCell((prev) => {
      if (
        !prev.open ||
        prev.rowId !== currentRow.rowId ||
        prev.checkId !== currentColumn.checkId
      ) {
        return prev;
      }
      if (areDetailsCellsEquivalent(prev.cell, freshDetailsCell)) {
        return prev;
      }
      return { ...prev, cell: freshDetailsCell };
    });
  }, [rows, columns]);

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

  const closeDetails = useCallback(() => {
    setSelectedCell({
      open: false,
      rowId: null,
      documentId: null,
      documentName: null,
      checkId: null,
      checkName: null,
      cell: null,
    });
  }, []);

  const handleCellOpen = useCallback(
    (params: {
      row: ReviewGridRow;
      meta: ReviewCheckColumn;
      cell: MatrixCellDTO;
    }) => {
      const detailsCell = mapReviewCellToDetailsCell(
        params.row,
        params.meta,
        params.cell,
      );

      setSelectedCell({
        open: true,
        rowId: params.row.rowId,
        documentId: params.row.documentId,
        documentName: params.row.documentName ?? null,
        checkId: params.meta.checkId,
        checkName: params.meta.checkName ?? null,
        cell: detailsCell,
      });

      onOpenCell?.({
        documentId: params.row.documentId,
        documentName: params.row.documentName ?? null,
        checkId: params.meta.checkId,
        checkName: params.meta.checkName ?? null,
        cell: detailsCell,
      });
    },
    [onOpenCell],
  );

  const defaultColDef = useMemo<ColDef<MatrixGridRow>>(
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
      enableSelectionWithoutKeys: true,
      checkboxes: true,
      headerCheckbox: true,
      enableClickSelection: false,
    }),
    [],
  );

  const baseColumns = useMemo<ColDef<MatrixGridRow>[]>(
    () => [
      {
        headerName: "#",
        width: 64,
        pinned: "left",
        sortable: false,
        filter: false,
        valueGetter: (params: ValueGetterParams<MatrixGridRow>) =>
          params.node?.rowIndex != null ? params.node.rowIndex + 1 : "",
      },
      {
        headerName: "Документ",
        field: "documentName",
        minWidth: 240,
        flex: 2,
        pinned: "left",
        cellRenderer: (params: ICellRendererParams<MatrixGridRow>) => {
          const documentId = params.data?.documentId;
          const documentName = params.data?.documentName || "[no name]";

          if (!documentId || !onOpenDocument) {
            return (
              <span className="text-xs text-[var(--text-secondary)]">
                {documentName}
              </span>
            );
          }

          return (
            <button
              type="button"
              className="text-left text-xs text-[var(--accent-primary)] hover:underline"
              onClick={(e) => {
                e.stopPropagation();
                onOpenDocument({ documentId, documentName });
              }}
            >
              {documentName}
            </button>
          );
        },
      },
      {
        headerName: "Сегмент",
        field: "segmentTitle",
        minWidth: 220,
        flex: 1.4,
        cellRenderer: (params: ICellRendererParams<MatrixGridRow>) => {
          const row = params.data;
          if (!row) {
            return <span className="text-[11px] text-[var(--text-faint)]">—</span>;
          }

          const title =
            row.segmentTitle ||
            row.primarySegmentLabel ||
            row.segmentId ||
            (row.segmentCount && row.segmentCount > 1 ? "Root segment" : "—");

          const metaParts = [
            row.segmentType || null,
            row.segmentOrder != null ? `#${row.segmentOrder}` : null,
            row.isPrimarySegment ? "primary" : null,
          ].filter(Boolean);

          return (
            <div className="flex min-w-0 flex-col py-0.5">
              <span className="truncate text-[11px] font-medium text-[var(--text-primary)]">
                {title}
              </span>
              {metaParts.length > 0 && (
                <span className="truncate text-[10px] text-[var(--text-muted)]">
                  {metaParts.join(" · ")}
                </span>
              )}
            </div>
          );
        },
      },
      {
        headerName: "Тип документа",
        field: "docType",
        width: 150,
        valueFormatter: (params: ValueFormatterParams<MatrixGridRow>) =>
          (params.value as string | null | undefined) || "—",
      },
      {
        headerName: "Классификация",
        field: "classificationLevel",
        width: 150,
        cellRenderer: (params: ICellRendererParams<MatrixGridRow>) => {
          const level = params.data?.classificationLevel;
          const confidence = params.data?.classificationConfidence;
          if (!level) {
            return <span className="text-[11px] text-[var(--text-faint)]">—</span>;
          }
          return (
            <ClassificationBadge
              level={level as ClassificationLevel}
              confidence={confidence ?? undefined}
              showConfidence={false}
            />
          );
        },
      },
      {
        headerName: "Состав",
        field: "isMultiDocument",
        width: 180,
        cellRenderer: (params: ICellRendererParams<MatrixGridRow>) => {
          const row = params.data;
          if (!row) {
            return <span className="text-[11px] text-[var(--text-faint)]">—</span>;
          }

          const badges = getRowCompositionBadgeData(row);
          if (!badges.showMultiBadge && !badges.showSegmentCount) {
            return (
              <span className="text-[11px] text-[var(--text-muted)]">single</span>
            );
          }

          return (
            <div className="flex items-center gap-1 py-0.5">
              {badges.showMultiBadge && (
                <span className="inline-flex items-center rounded-full border border-[var(--border-accent-soft)] bg-[var(--bg-elevated-soft)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--accent-primary)]">
                  multi
                </span>
              )}
              {badges.showSegmentCount && (
                <span className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--bg-card)] px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)]">
                  {badges.segmentCount} seg
                </span>
              )}
            </div>
          );
        },
      },
      { headerName: "Crit", field: "totalCritical", width: 72 },
      { headerName: "High", field: "totalHigh", width: 72 },
      { headerName: "Med", field: "totalMedium", width: 72 },
      { headerName: "Unclear", field: "totalUnclear", width: 72 },
    ],
    [onOpenDocument],
  );

  const riskColDefs = useMemo<ColDef<MatrixGridRow>[]>(
    () =>
      columns.map((meta) => {
        const field = `risk_${meta.checkId}` as const;

        return {
          colId: field,
          headerName: meta.checkName,
          headerTooltip: getHeaderTooltip(meta),
          minWidth: 220,
          cellDataType: false,
          valueGetter: (params: ValueGetterParams<MatrixGridRow>) => {
            const cell = params.data?.[field];
            return buildRiskCellDiffKey(cell);
          },
          valueFormatter: (
            params: ValueFormatterParams<MatrixGridRow>,
          ): string => {
            const cell = params.data?.[field];
            // display_text приоритет для export/clipboard
            const displayText = cell?.display_text?.trim();
            return displayText || formatRiskCellValue(cell ?? null);
          },
          tooltipValueGetter: (
            params: ITooltipParams<MatrixGridRow>,
          ): string => {
            const cell = params.data?.[field];
            return buildCellTooltip(cell);
          },
          cellRenderer: (params: ICellRendererParams<MatrixGridRow>) => {
            const row = params.data;
            const cell = row?.[field];

            if (!row || !cell) {
              return (
                <span className="text-[11px] text-[var(--text-faint)]">—</span>
              );
            }

            // Primary: factual display_text из backend.
            // Secondary: workflow status — показываем только если отличается.
            const primaryText = getCellPrimaryText(cell);
            const secondaryText = getCellStatusText(cell);
            const showSecondary =
              !!secondaryText && secondaryText !== primaryText;
            const severity = getCellSeverity(cell);

            return (
              <div className="flex w-full flex-col items-start gap-1 py-1 text-left">
                <button
                  type="button"
                  className="w-full text-left"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleCellOpen({ row, meta, cell });
                  }}
                >
                  <div className="text-[11px] font-medium text-[var(--text-primary)]">
                    {primaryText}
                  </div>

                  {showSecondary ? (
                    <div className="mt-0.5 text-[10px] text-[var(--text-muted)]">
                      {secondaryText}
                    </div>
                  ) : null}

                  {(severity || cell.qc_status) && (
                    <div className="mt-1 flex flex-wrap items-center gap-1">
                      {severity && (
                        <div className="origin-left scale-90">
                          <SeverityBadge severity={severity} />
                        </div>
                      )}
                      {cell.qc_status ? (
                        <QcStatusBadge status={cell.qc_status} />
                      ) : null}
                    </div>
                  )}
                </button>
              </div>
            );
          },
        } satisfies ColDef<MatrixGridRow>;
      }),
    [handleCellOpen, columns],
  );

  const columnDefs = useMemo<ColDef<MatrixGridRow>[]>(
    () => [...baseColumns, ...riskColDefs],
    [baseColumns, riskColDefs],
  );

  const handleSelectionChanged = useCallback(
    (event: SelectionChangedEvent<MatrixGridRow>) => {
      if (!onSelectionChange) return;
      onSelectionChange(buildSelectionItems(event));
    },
    [onSelectionChange],
  );

  const handleGridReady = useCallback(
    (event: GridReadyEvent<MatrixGridRow>) => {
      setGridApi(event.api);
      requestAnimationFrame(() => {
        try {
          event.api.sizeColumnsToFit();
        } catch {
          /* noop */
        }
      });
    },
    [],
  );

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
        По выбранным фильтрам в DD Matrix ничего не найдено.
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
              minHeight: MATRIX_MIN_HEIGHT_PX,
              minWidth: 1200,
            }}
          >
            <AgGridReact<MatrixGridRow>
              theme="legacy"
              rowData={rowData}
              columnDefs={columnDefs}
              defaultColDef={defaultColDef}
              rowSelection={rowSelection}
              suppressCellFocus
              tooltipShowDelay={200}
              onSelectionChanged={handleSelectionChanged}
              onGridReady={handleGridReady}
              getRowId={(params) => params.data.rowId}
              domLayout="normal"
            />
          </div>
        </div>
      </div>

      <DDMatrixCellDetails
        open={isSelectedCellValid}
        onClose={closeDetails}
        runId={runId}
        documentName={selectedCell.documentName}
        documentId={selectedCell.documentId}
        checkName={selectedCell.checkName}
        checkId={selectedCell.checkId}
        cell={selectedCell.cell}
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

export default DDMatrixGrid;



// =============================================================
// src/components/grid/DDMatrixGrid.tsx
// Review DD Matrix (run-scoped документ × проверка).
// Pure presentational grid: принимает готовые normalized rows
// от domain layer, а не строит их сам.
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

import type {
  ClassificationLevel,
  OpenViewerAtFn,
} from "../../types";
import type { MatrixCellDTO } from "../../types/dealReview";

import { SeverityBadge } from "../ui/SeverityBadge";
import { ClassificationBadge } from "../ui/ClassificationBadge";
import { getCompositionBadgeDataFromMeta } from "../../utils/compositionHelpers";
import DDMatrixCellDetails, {
  type MatrixCellDetailsCell,
} from "./DDMatrixCellDetails";

import type {
  ReviewGridRow,
  ReviewCheckColumn,
} from "../../pages/tabs/grid/reviewGrid.types";

import {
  mapReviewCellToDetailsCell,
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
  onSelectionChange?: (rowIds: string[]) => void;
}

interface SelectedCellState {
  open: boolean;
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

function getSelectedRowIds(
  event: SelectionChangedEvent<MatrixGridRow>,
): string[] {
  return event.api
    .getSelectedNodes()
    .map((node) => node.data?.rowId)
    .filter((value): value is string => Boolean(value));
}

export const DDMatrixGrid: React.FC<DDMatrixGridProps> = ({
  runId,
  rows,
  columns,
  onOpenAtLocation,
  onOpenDocument,
  onOpenCell,
  onSelectionChange,
}) => {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [rootWidth, setRootWidth] = useState<number>(0);
  const [gridApi, setGridApi] = useState<GridApi<MatrixGridRow> | null>(null);

  const [selectedCell, setSelectedCell] = useState<SelectedCellState>({
    open: false,
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
      documentId: null,
      documentName: null,
      checkId: null,
      checkName: null,
      cell: null,
    });
  }, []);

  useEffect(() => {
    if (!selectedCell.open || !selectedCell.documentId || !selectedCell.checkId) {
      return;
    }

    const rowStillExists = rows.some(
      (row) => row.documentId === selectedCell.documentId,
    );
    const columnStillExists = columns.some(
      (col) => col.checkId === selectedCell.checkId,
    );

    if (!rowStillExists || !columnStillExists) {
      setSelectedCell({
        open: false,
        documentId: null,
        documentName: null,
        checkId: null,
        checkName: null,
        cell: null,
      });
    }
  }, [
    rows,
    columns,
    selectedCell.open,
    selectedCell.documentId,
    selectedCell.checkId,
  ]);

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
                onOpenDocument({
                  documentId,
                  documentName,
                });
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
            return (
              <span className="text-[11px] text-[var(--text-faint)]">—</span>
            );
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
            return (
              <span className="text-[11px] text-[var(--text-faint)]">—</span>
            );
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
            return (
              <span className="text-[11px] text-[var(--text-faint)]">—</span>
            );
          }

          const badges = getRowCompositionBadgeData(row);

          if (!badges.showMultiBadge && !badges.showSegmentCount) {
            return (
              <span className="text-[11px] text-[var(--text-muted)]">
                single
              </span>
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
          field,
          minWidth: 220,
          cellDataType: false,
          valueFormatter: (
            params: ValueFormatterParams<
              MatrixGridRow,
              MatrixCellDTO | null | undefined
            >,
          ): string => formatRiskCellValue(params.value),
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

            const statusText = getCellStatusText(cell);
            const severity = getCellSeverity(cell);

            return (
              <div className="flex w-full flex-col items-start gap-1 py-1 text-left">
                <button
                  type="button"
                  className="w-full text-left"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleCellOpen({
                      row,
                      meta,
                      cell,
                    });
                  }}
                >
                  <div className="text-[11px] text-[var(--text-primary)]">
                    {statusText}
                  </div>
                  {severity && (
                    <div className="mt-1 origin-left scale-90">
                      <SeverityBadge severity={severity} />
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
      onSelectionChange(getSelectedRowIds(event));
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
        className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm"
      >
        <div className="overflow-x-auto">
          <div
            className="ag-theme-legalmas w-full"
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
              domLayout="autoHeight"
            />
          </div>
        </div>
      </div>

      <DDMatrixCellDetails
        open={selectedCell.open}
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




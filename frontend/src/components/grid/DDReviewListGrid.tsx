// =============================================================
// src/components/grid/DDReviewListGrid.tsx
// Flat review findings grid.
//
// Presents normalized review matrix data as a one-row-per-finding list.
// Reuses the same details drawer and viewer navigation model as DDMatrixGrid.
//
// Production notes:
// - findings-only list by default (pass results hidden at mapper level)
// - stable row IDs for AG Grid getRowId
// - legacy AG Grid theme mode to stay compatible with CSS theme imports
// - object-valued review cells are rendered through explicit getters/formatters
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
  ValueFormatterParams,
  ValueGetterParams,
} from "ag-grid-community";

import type {
  ClassificationLevel,
  OpenViewerAtFn,
} from "../../types";

import { SeverityBadge } from "../ui/SeverityBadge";
import { ClassificationBadge } from "../ui/ClassificationBadge";
import DDMatrixCellDetails, {
  type MatrixCellDetailsCell,
} from "./DDMatrixCellDetails";

import type {
  ReviewGridRow,
  ReviewCheckColumn,
} from "../../pages/tabs/grid/reviewGrid.types";
import type { FindingListRow } from "./reviewListGrid.types";

import {
  buildCellTooltip,
  formatRiskCellValue,
  getCellLocationText,
  getCellSegmentText,
  getCellSeverity,
  getCellStatusText,
  mapReviewCellToDetailsCell,
} from "./reviewCellDetails.mapper";
import { buildReviewListRows } from "./reviewListGrid.mapper";

import "ag-grid-community/styles/ag-grid.css";
import "../../styles/ag-theme-legalmas.css";

const GRID_MIN_HEIGHT_PX = 240;

export interface DDReviewListGridProps {
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

function getSelectedRowIds(
  event: SelectionChangedEvent<FindingListRow>,
): string[] {
  return event.api
    .getSelectedNodes()
    .map((node) => node.data?.rowId)
    .filter((value): value is string => Boolean(value));
}

function formatPercent(value: number | null | undefined): string {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "—";
}

export const DDReviewListGrid: React.FC<DDReviewListGridProps> = ({
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
  const [gridApi, setGridApi] = useState<GridApi<FindingListRow> | null>(null);

  const [selectedCell, setSelectedCell] = useState<SelectedCellState>({
    open: false,
    documentId: null,
    documentName: null,
    checkId: null,
    checkName: null,
    cell: null,
  });

  const rowData = useMemo(
    () => buildReviewListRows(rows, columns, { includePass: false }),
    [rows, columns],
  );

  const defaultColDef = useMemo<ColDef<FindingListRow>>(
    () => ({
      sortable: true,
      filter: true,
      resizable: true,
      suppressHeaderMenuButton: false,
      tooltipShowDelay: 200,
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

    const findingStillExists = rowData.some(
      (row) =>
        row.documentId === selectedCell.documentId &&
        row.checkId === selectedCell.checkId,
    );

    if (!findingStillExists) {
      closeDetails();
    }
  }, [
    rowData,
    selectedCell.open,
    selectedCell.documentId,
    selectedCell.checkId,
    closeDetails,
  ]);

  const handleCellOpen = useCallback(
    (row: FindingListRow) => {
      const detailsCell = mapReviewCellToDetailsCell(
        row.sourceRow,
        row.sourceColumn,
        row.cell,
      );

      setSelectedCell({
        open: true,
        documentId: row.documentId,
        documentName: row.documentName ?? null,
        checkId: row.checkId,
        checkName: row.checkName ?? null,
        cell: detailsCell,
      });

      onOpenCell?.({
        documentId: row.documentId,
        documentName: row.documentName ?? null,
        checkId: row.checkId,
        checkName: row.checkName ?? null,
        cell: detailsCell,
      });
    },
    [onOpenCell],
  );

  const columnDefs = useMemo<ColDef<FindingListRow>[]>(
    () => [
      {
        headerName: "Документ",
        field: "documentName",
        minWidth: 260,
        pinned: "left",
        checkboxSelection: true,
        headerCheckboxSelection: true,
        tooltipValueGetter: (params) => params.data?.documentName ?? "",
        cellRenderer: (params: ICellRendererParams<FindingListRow>) => {
          const row = params.data;
          if (!row) {
            return (
              <span className="text-[11px] text-[var(--text-faint)]">—</span>
            );
          }

          const documentLabel = row.documentName || "[no name]";

          if (!onOpenDocument) {
            return (
              <span className="text-xs text-[var(--text-secondary)]">
                {documentLabel}
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
                  documentId: row.documentId,
                  documentName: row.documentName,
                });
              }}
            >
              {documentLabel}
            </button>
          );
        },
      },
      {
        headerName: "Проверка",
        field: "checkName",
        minWidth: 260,
        tooltipValueGetter: (params) => params.data?.checkName ?? "",
      },
      {
        headerName: "Результат",
        colId: "result",
        minWidth: 190,
        cellDataType: false,
        valueGetter: (params: ValueGetterParams<FindingListRow>) =>
          params.data?.cell ?? null,
        valueFormatter: (
          params: ValueFormatterParams<FindingListRow>
        ): string => formatRiskCellValue(params.value),
        tooltipValueGetter: (params) => buildCellTooltip(params.data?.cell),
        cellRenderer: (params: ICellRendererParams<FindingListRow>) => {
          const row = params.data;
          if (!row) {
            return (
              <span className="text-[11px] text-[var(--text-faint)]">—</span>
            );
          }

          const severity = getCellSeverity(row.cell);
          const statusText = getCellStatusText(row.cell);

          return (
            <button
              type="button"
              className="flex w-full flex-col items-start gap-1 py-1 text-left"
              onClick={(e) => {
                e.stopPropagation();
                handleCellOpen(row);
              }}
            >
              <span className="text-[11px] text-[var(--text-primary)]">
                {statusText}
              </span>
              {severity ? (
                <div className="origin-left scale-90">
                  <SeverityBadge severity={severity} />
                </div>
              ) : null}
            </button>
          );
        },
      },
      {
        headerName: "QC",
        minWidth: 120,
        valueGetter: (params) => params.data?.cell.qc_status ?? "—",
        tooltipValueGetter: (params) => params.data?.cell.qc_status ?? "",
      },
      {
        headerName: "Confidence",
        minWidth: 110,
        valueGetter: (params) => params.data?.cell.confidence ?? null,
        valueFormatter: (params) => formatPercent(params.value as number | null),
      },
      {
        headerName: "Evidence",
        minWidth: 420,
        flex: 1,
        sortable: false,
        valueGetter: (params) => params.data?.cell.snippet?.trim() ?? "",
        tooltipValueGetter: (params) => params.data?.cell.snippet?.trim() ?? "",
        cellRenderer: (params: ICellRendererParams<FindingListRow>) => {
          const snippet = params.data?.cell.snippet?.trim();
          return snippet ? (
            <div className="line-clamp-2 py-1 text-[11px] leading-5 text-[var(--text-primary)]">
              {snippet}
            </div>
          ) : (
            <span className="text-[11px] text-[var(--text-faint)]">—</span>
          );
        },
      },
      {
        headerName: "Локация",
        minWidth: 180,
        sortable: false,
        valueGetter: (params) => {
          const cell = params.data?.cell;
          return cell ? getCellLocationText(cell) : "";
        },
        tooltipValueGetter: (params) => {
          const cell = params.data?.cell;
          return cell ? getCellLocationText(cell) : "";
        },
      },
      {
        headerName: "Сегмент",
        minWidth: 200,
        sortable: false,
        valueGetter: (params) => {
          const cell = params.data?.cell;
          return cell ? getCellSegmentText(cell) : "";
        },
        tooltipValueGetter: (params) => {
          const cell = params.data?.cell;
          return cell ? getCellSegmentText(cell) : "";
        },
      },
      {
        headerName: "Тип документа",
        field: "docType",
        minWidth: 140,
        tooltipValueGetter: (params) => params.data?.docType ?? "",
      },
      {
        headerName: "Классификация",
        field: "classificationLevel",
        minWidth: 150,
        tooltipValueGetter: (params) => params.data?.classificationLevel ?? "",
        cellRenderer: (params: ICellRendererParams<FindingListRow>) => {
          const row = params.data;
          if (!row?.classificationLevel) {
            return (
              <span className="text-[11px] text-[var(--text-faint)]">—</span>
            );
          }

          return (
            <ClassificationBadge
              level={row.classificationLevel as ClassificationLevel}
              confidence={row.classificationConfidence ?? undefined}
              showConfidence={false}
            />
          );
        },
      },
      {
        headerName: "Источник",
        field: "origin",
        minWidth: 140,
        tooltipValueGetter: (params) => params.data?.origin ?? "",
      },
    ],
    [handleCellOpen, onOpenDocument],
  );

  const handleSelectionChanged = useCallback(
    (event: SelectionChangedEvent<FindingListRow>) => {
      if (!onSelectionChange) return;
      onSelectionChange(getSelectedRowIds(event));
    },
    [onSelectionChange],
  );

  const handleGridReady = useCallback(
    (event: GridReadyEvent<FindingListRow>) => {
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
        По выбранным фильтрам в review list ничего не найдено.
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
              minHeight: GRID_MIN_HEIGHT_PX,
              minWidth: 1200,
            }}
          >
            <AgGridReact<FindingListRow>
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

export default DDReviewListGrid;




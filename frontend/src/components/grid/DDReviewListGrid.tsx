// =============================================================
// src/components/grid/DDReviewListGrid.tsx
// Flat review findings grid.
//
// Presents normalized review matrix data as a one-row-per-finding list.
// Reuses the same details drawer and viewer navigation model as DDMatrixGrid.
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
  SelectionChangedEvent,
  SelectionColumnDef,
  ValueFormatterParams,
  ValueGetterParams,
} from "ag-grid-community";

import type { ClassificationLevel, OpenViewerAtFn } from "../../types";

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
const GRID_MIN_WIDTH_PX = 1200;
const SELECTION_COLUMN_WIDTH_PX = 52;

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

function normalizeComparable(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value.trim();
  return String(value);
}

function areStringArraysEqual(
  left: string[] | null | undefined,
  right: string[] | null | undefined,
): boolean {
  const a = left ?? [];
  const b = right ?? [];
  if (a.length !== b.length) return false;
  return a.every((value, index) => value === b[index]);
}

function areDetailsCellsEquivalent(
  left: MatrixCellDetailsCell | null | undefined,
  right: MatrixCellDetailsCell | null | undefined,
): boolean {
  if (left === right) return true;
  if (!left || !right) return false;

  const leftFlags = left.qualityFlags ?? {};
  const rightFlags = right.qualityFlags ?? {};
  const leftFlagKeys = Object.keys(leftFlags).sort();
  const rightFlagKeys = Object.keys(rightFlags).sort();

  if (!areStringArraysEqual(leftFlagKeys, rightFlagKeys)) return false;
  if (!leftFlagKeys.every((key) => Boolean(leftFlags[key]) === Boolean(rightFlags[key])))
    return false;

  const leftFields = left.extractedFields ?? [];
  const rightFields = right.extractedFields ?? [];
  if (leftFields.length !== rightFields.length) return false;

  for (let index = 0; index < leftFields.length; index += 1) {
    const lf = leftFields[index];
    const rf = rightFields[index];

    if (
      normalizeComparable(lf.fieldName) !== normalizeComparable(rf.fieldName) ||
      normalizeComparable(lf.fieldValue) !== normalizeComparable(rf.fieldValue) ||
      normalizeComparable(lf.fieldFormat) !== normalizeComparable(rf.fieldFormat) ||
      normalizeComparable(lf.fieldSource) !== normalizeComparable(rf.fieldSource) ||
      normalizeComparable(lf.page) !== normalizeComparable(rf.page) ||
      normalizeComparable(lf.clauseUid) !== normalizeComparable(rf.clauseUid) ||
      normalizeComparable(lf.segmentId) !== normalizeComparable(rf.segmentId) ||
      normalizeComparable(lf.chunkId) !== normalizeComparable(rf.chunkId) ||
      normalizeComparable(lf.chunkIndex) !== normalizeComparable(rf.chunkIndex)
    )
      return false;
  }

  return (
    normalizeComparable(left.result) === normalizeComparable(right.result) &&
    normalizeComparable(left.severity) === normalizeComparable(right.severity) &&
    normalizeComparable(left.snippet) === normalizeComparable(right.snippet) &&
    normalizeComparable(left.page) === normalizeComparable(right.page) &&
    normalizeComparable(left.clauseUid) === normalizeComparable(right.clauseUid) &&
    normalizeComparable(left.confidence) === normalizeComparable(right.confidence) &&
    normalizeComparable(left.qcStatus) === normalizeComparable(right.qcStatus) &&
    normalizeComparable(left.conditionalTriggered) ===
      normalizeComparable(right.conditionalTriggered) &&
    normalizeComparable(left.triggerName) === normalizeComparable(right.triggerName) &&
    normalizeComparable(left.origin) === normalizeComparable(right.origin) &&
    normalizeComparable(left.createdAt) === normalizeComparable(right.createdAt) &&
    normalizeComparable(left.qcComment) === normalizeComparable(right.qcComment) &&
    normalizeComparable(left.docType) === normalizeComparable(right.docType) &&
    normalizeComparable(left.docClassificationLevel) ===
      normalizeComparable(right.docClassificationLevel) &&
    normalizeComparable(left.docClassificationConfidence) ===
      normalizeComparable(right.docClassificationConfidence) &&
    normalizeComparable(left.segmentId) === normalizeComparable(right.segmentId) &&
    normalizeComparable(left.segmentTitle) === normalizeComparable(right.segmentTitle) &&
    normalizeComparable(left.segmentType) === normalizeComparable(right.segmentType) &&
    normalizeComparable(left.segmentOrder) === normalizeComparable(right.segmentOrder) &&
    normalizeComparable(left.isPrimarySegment) ===
      normalizeComparable(right.isPrimarySegment) &&
    normalizeComparable(left.chunkId) === normalizeComparable(right.chunkId) &&
    normalizeComparable(left.chunkIndex) === normalizeComparable(right.chunkIndex)
  );
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

  const isSelectedCellValid =
    selectedCell.open &&
    selectedCell.documentId != null &&
    selectedCell.checkId != null &&
    rowData.some(
      (row) =>
        row.documentId === selectedCell.documentId &&
        row.checkId === selectedCell.checkId,
    );

  const selectedCellRef = useRef<SelectedCellState>(selectedCell);
  useEffect(() => {
    selectedCellRef.current = selectedCell;
  }, [selectedCell]);

  useEffect(() => {
    const sc = selectedCellRef.current;
    if (!sc.open || !sc.documentId || !sc.checkId) return;

    const currentListRow = rowData.find(
      (row) =>
        row.documentId === sc.documentId && row.checkId === sc.checkId,
    );
    if (!currentListRow) return;

    const freshDetailsCell = mapReviewCellToDetailsCell(
      currentListRow.sourceRow,
      currentListRow.sourceColumn,
      currentListRow.cell,
    );

    setSelectedCell((prev) => {
      if (
        !prev.open ||
        prev.documentId !== currentListRow.documentId ||
        prev.checkId !== currentListRow.checkId
      ) {
        return prev;
      }
      if (areDetailsCellsEquivalent(prev.cell, freshDetailsCell)) {
        return prev;
      }
      return { ...prev, cell: freshDetailsCell };
    });
  }, [rowData]);

  const defaultColDef = useMemo<ColDef<FindingListRow>>(
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
        tooltipValueGetter: (params) => params.data?.documentName ?? "",
        cellRenderer: (params: ICellRendererParams<FindingListRow>) => {
          const row = params.data;
          if (!row) {
            return <span className="text-[11px] text-[var(--text-faint)]">—</span>;
          }
          const documentLabel = row.documentName || "[no name]";
          if (!onOpenDocument) {
            return (
              <span className="text-xs text-[var(--text-secondary)]">{documentLabel}</span>
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
        valueFormatter: (params: ValueFormatterParams<FindingListRow>): string =>
          formatRiskCellValue(params.value),
        tooltipValueGetter: (params) => buildCellTooltip(params.data?.cell),
        cellRenderer: (params: ICellRendererParams<FindingListRow>) => {
          const row = params.data;
          if (!row) {
            return <span className="text-[11px] text-[var(--text-faint)]">—</span>;
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
            return <span className="text-[11px] text-[var(--text-faint)]">—</span>;
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
          // noop
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
        // noop
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
            <AgGridReact<FindingListRow>
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

export default DDReviewListGrid;



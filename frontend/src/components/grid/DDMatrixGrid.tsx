// =============================================================
// src/components/grid/DDMatrixGrid.tsx
// Review DD Matrix (run-scoped документ × проверка).
// Pure presentational grid: принимает готовые normalized rows
// от domain layer, а не строит их сам.
// =============================================================

import React, {
  useCallback,
  useEffect,
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
  SeverityLevel,
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
  // NEW: runId needed for QC mutations
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

function isRiskSeverity(
  value: string | null | undefined,
): value is SeverityLevel {
  return value === "critical" || value === "high" || value === "medium";
}

function getCellStatusText(cell: MatrixCellDTO): string {
  if (cell.result === "fail") {
    if (cell.severity === "critical" || cell.severity === "high") {
      return "Требует внимания юриста";
    }
    return "Идентифицирован";
  }

  if (cell.result === "unclear") {
    return "Требует внимания юриста";
  }

  return "Не найден";
}

function getCellSeverity(cell: MatrixCellDTO): SeverityLevel | null {
  return isRiskSeverity(cell.severity) ? cell.severity : null;
}

function getCellLocationText(cell: MatrixCellDTO): string {
  const pageText = cell.page != null ? `стр. ${cell.page}` : "";
  const clauseText = cell.clause_uid ? cell.clause_uid : "";

  if (pageText && clauseText) return `${pageText} · ${clauseText}`;
  return pageText || clauseText || "";
}

function getCellSegmentText(cell: MatrixCellDTO): string {
  const segmentText = cell.segment_title || cell.segment_id || "";
  const chunkText =
    cell.chunk_index != null ? `Chunk #${cell.chunk_index}` : "";

  if (segmentText && chunkText) return `${segmentText} · ${chunkText}`;
  return segmentText || chunkText || "";
}

function getCellCreatedAt(cell: MatrixCellDTO): string | null {
  const candidate = (cell as { created_at?: unknown }).created_at;
  return typeof candidate === "string" ? candidate : null;
}

function getCellQcComment(cell: MatrixCellDTO): string | null {
  const candidate = (cell as { qc_comment?: unknown }).qc_comment;
  return typeof candidate === "string" ? candidate : null;
}

function getCellQualityFlags(
  cell: MatrixCellDTO,
): Record<string, boolean> | null {
  const candidate = (cell as { quality_flags?: unknown }).quality_flags;
  if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) {
    return null;
  }

  return Object.fromEntries(
    Object.entries(candidate).filter(
      ([, value]) => typeof value === "boolean",
    ),
  ) as Record<string, boolean>;
}

function mapReviewCellToDetailsCell(
  row: ReviewGridRow,
  meta: ReviewCheckColumn,
  cell: MatrixCellDTO,
): MatrixCellDetailsCell {
  return {
    result: cell.result,
    severity: getCellSeverity(cell),
    snippet: cell.snippet ?? null,
    page: cell.page ?? null,
    clauseUid: cell.clause_uid ?? null,
    confidence: cell.confidence ?? null,
    qcStatus: cell.qc_status ?? null,
    conditionalTriggered: !!cell.conditional_check_triggered,
    triggerName: cell.trigger_name ?? null,

    origin: meta.origin ?? null,
    createdAt: getCellCreatedAt(cell),
    qcComment: getCellQcComment(cell),
    qualityFlags: getCellQualityFlags(cell),

    docType: row.docType ?? null,
    docClassificationLevel: row.classificationLevel ?? null,
    docClassificationConfidence: row.classificationConfidence ?? null,

    segmentId: cell.segment_id ?? row.segmentId ?? null,
    segmentTitle: cell.segment_title ?? row.segmentTitle ?? null,
    segmentType: cell.segment_type ?? row.segmentType ?? null,
    segmentOrder: cell.segment_order ?? row.segmentOrder ?? null,
    isPrimarySegment: cell.is_primary_segment ?? row.isPrimarySegment ?? null,
    chunkId: cell.chunk_id ?? null,
    chunkIndex: cell.chunk_index ?? null,

    extractedFields: Array.isArray(cell.extracted)
      ? cell.extracted.map((field) => ({
          fieldName: field.field_name,
          fieldValue: field.field_value,
          fieldFormat: field.field_format ?? null,
          fieldSource:
            typeof (field as { field_source?: unknown }).field_source ===
            "string"
              ? ((field as { field_source?: string }).field_source ?? null)
              : null,
          page:
            typeof (field as { page?: unknown }).page === "number"
              ? ((field as { page?: number }).page ?? null)
              : null,
          clauseUid:
            typeof (field as { clause_uid?: unknown }).clause_uid === "string"
              ? ((field as { clause_uid?: string }).clause_uid ?? null)
              : null,
          segmentId:
            typeof (field as { segment_id?: unknown }).segment_id === "string"
              ? ((field as { segment_id?: string }).segment_id ?? null)
              : null,
          chunkId:
            typeof (field as { chunk_id?: unknown }).chunk_id === "string"
              ? ((field as { chunk_id?: string }).chunk_id ?? null)
              : null,
          chunkIndex:
            typeof (field as { chunk_index?: unknown }).chunk_index === "number"
              ? ((field as { chunk_index?: number }).chunk_index ?? null)
              : null,
        }))
      : [],
  };
}

function buildCellTooltip(cell: MatrixCellDTO): string {
  return (
    cell.snippet ||
    getCellLocationText(cell) ||
    getCellSegmentText(cell) ||
    getCellStatusText(cell)
  );
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

// -------------------------------------------------------------
// Component
// -------------------------------------------------------------

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
    if (!selectedCell.open) return;
    closeDetails();
  }, [rowData, columns, closeDetails, selectedCell.open]);

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
          headerName: meta.checkName,
          headerTooltip: getHeaderTooltip(meta),
          field,
          minWidth: 220,
          tooltipValueGetter: (
            params: ITooltipParams<MatrixGridRow>,
          ): string => {
            const cell = params.data?.[field];
            return cell ? buildCellTooltip(cell) : "";
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

  useEffect(() => {
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
              rowData={rowData}
              columnDefs={columnDefs}
              defaultColDef={defaultColDef}
              rowSelection={{
                mode: "multiRow",
                enableSelectionWithoutKeys: true,
                checkboxes: true,
                headerCheckbox: true,
                enableClickSelection: false,
              }}
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




// =============================================================
// src/components/grid/DDMatrixGrid.tsx
// Review DD Matrix (run-scoped документ × проверка).
// Продакшн-версия с autoHeight (без debug-лейаута).
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
import type {
  DDMatrixResponseDTO,
  DocumentMatrixRowDTO,
  MatrixCellDTO,
  ExtractedFieldDTO,
} from "../../types/dealReview";

import { SeverityBadge } from "../ui/SeverityBadge";
import { ClassificationBadge } from "../ui/ClassificationBadge";
import { getCompositionBadgeDataFromMeta } from "../../utils/compositionHelpers";
import DDMatrixCellDetails, {
  type MatrixCellDetailsCell,
} from "./DDMatrixCellDetails";

import "ag-grid-community/styles/ag-grid.css";
import "../../styles/ag-theme-legalmas.css";

const MATRIX_MIN_HEIGHT_PX = 240;

function getRowCompositionBadgeData(row: MatrixRowBase) {
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
  data: DDMatrixResponseDTO | null | undefined;
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
  onSelectionChange?: (documentIds: string[]) => void;
  multiDocumentOnly?: boolean;
  criticalOnly?: boolean;
}

interface MatrixRowBase {
  documentId: string;
  documentName: string;
  docType?: string | null;
  folderPath?: string | null;

  classificationLevel?: ClassificationLevel | string | null;
  classificationConfidence?: number | null;
  requiresManualReview?: boolean;

  isMultiDocument?: boolean;
  segmentCount?: number | null;
  primarySegmentLabel?: string | null;

  totalCritical: number;
  totalHigh: number;
  totalMedium: number;
  totalUnclear: number;
}

type MatrixRow = MatrixRowBase & {
  [key: `risk_${string}`]: MatrixCellDTO | undefined;
};

interface MatrixColumnMeta {
  checkId: string;
  checkName: string;
  origin?: string | null;
  severity?: string | null;
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

function mapExtractedFieldToDetailsField(field: ExtractedFieldDTO): {
  fieldName: string;
  fieldValue: string;
  fieldFormat?: string | null;
} {
  return {
    fieldName: field.field_name,
    fieldValue: field.field_value,
    fieldFormat: field.field_format ?? null,
  };
}

function mapMatrixCellToDetailsCell(cell: MatrixCellDTO): MatrixCellDetailsCell {
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

    segmentId: cell.segment_id ?? null,
    segmentTitle: cell.segment_title ?? null,
    segmentType: cell.segment_type ?? null,
    segmentOrder: cell.segment_order ?? null,
    isPrimarySegment: cell.is_primary_segment ?? null,
    chunkId: cell.chunk_id ?? null,
    chunkIndex: cell.chunk_index ?? null,

    extractedFields: Array.isArray(cell.extracted)
      ? cell.extracted.map(mapExtractedFieldToDetailsField)
      : [],
  };
}

function buildMatrixRows(data: DDMatrixResponseDTO): {
  rowData: MatrixRow[];
  riskColumns: MatrixColumnMeta[];
} {
  const riskColumns: MatrixColumnMeta[] = data.checks.map((check) => ({
    checkId: check.check_id,
    checkName: check.check_name || check.check_id,
    origin: check.origin ?? null,
    severity: check.severity ?? null,
  }));

  const rowData: MatrixRow[] = data.documents.map(
    (doc: DocumentMatrixRowDTO) => {
      const cells = Object.values(doc.results ?? {});

      const row: MatrixRow = {
        documentId: doc.document_id,
        documentName: doc.document_name || "[no name]",
        docType: doc.doc_type ?? null,
        folderPath: doc.folder_path ?? null,

        classificationLevel: doc.classification_level ?? null,
        classificationConfidence: doc.classification_confidence ?? null,
        requiresManualReview: doc.requires_manual_review ?? false,

        isMultiDocument: doc.is_multi_document ?? false,
        segmentCount: doc.segment_count ?? null,
        primarySegmentLabel: doc.primary_segment_label ?? null,

        totalCritical: cells.filter((c) => c?.severity === "critical").length,
        totalHigh: cells.filter((c) => c?.severity === "high").length,
        totalMedium: cells.filter((c) => c?.severity === "medium").length,
        totalUnclear: cells.filter((c) => c?.result === "unclear").length,
      };

      for (const check of data.checks) {
        const colKey = `risk_${check.check_id}` as const;
        row[colKey] = doc.results?.[check.check_id];
      }

      return row;
    },
  );

  return { rowData, riskColumns };
}

function buildCellTooltip(cell: MatrixCellDTO): string {
  return (
    cell.snippet ||
    getCellLocationText(cell) ||
    getCellSegmentText(cell) ||
    getCellStatusText(cell)
  );
}

function getHeaderTooltip(meta: MatrixColumnMeta): string {
  return [
    meta.checkName,
    meta.origin ? `Источник: ${meta.origin}` : null,
    meta.severity ? `Severity baseline: ${meta.severity}` : null,
  ]
    .filter(Boolean)
    .join("\n");
}

function getSelectedDocumentIds(
  event: SelectionChangedEvent<MatrixRow>,
): string[] {
  return event.api
    .getSelectedNodes()
    .map((node) => node.data?.documentId)
    .filter((value): value is string => Boolean(value));
}

// -------------------------------------------------------------
// Component
// -------------------------------------------------------------

export const DDMatrixGrid: React.FC<DDMatrixGridProps> = ({
  data,
  onOpenAtLocation,
  onOpenDocument,
  onOpenCell,
  onSelectionChange,
  multiDocumentOnly = false,
  criticalOnly = false,
}) => {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [rootWidth, setRootWidth] = useState<number>(0);
  const [gridApi, setGridApi] = useState<GridApi<MatrixRow> | null>(null);

  const [selectedCell, setSelectedCell] = useState<SelectedCellState>({
    open: false,
    documentId: null,
    documentName: null,
    checkId: null,
    checkName: null,
    cell: null,
  });

  const hasValidData = Boolean(
    data && Array.isArray(data.documents) && Array.isArray(data.checks),
  );

  const { rowData, riskColumns } = useMemo(() => {
    if (!hasValidData || !data) {
      return {
        rowData: [] as MatrixRow[],
        riskColumns: [] as MatrixColumnMeta[],
      };
    }

    const built = buildMatrixRows(data);
    let filtered = built.rowData;

    if (multiDocumentOnly) {
      filtered = filtered.filter((row) => row.isMultiDocument === true);
    }

    if (criticalOnly) {
      filtered = filtered.filter((row) => row.totalCritical > 0);
    }

    return {
      rowData: filtered,
      riskColumns: built.riskColumns,
    };
  }, [data, hasValidData, multiDocumentOnly, criticalOnly]);

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
  }, [data, multiDocumentOnly, criticalOnly, closeDetails, selectedCell.open]);

  const handleCellOpen = useCallback(
    (params: {
      documentId: string;
      documentName?: string | null;
      checkId: string;
      checkName?: string | null;
      cell: MatrixCellDTO;
    }) => {
      const detailsCell = mapMatrixCellToDetailsCell(params.cell);

      setSelectedCell({
        open: true,
        documentId: params.documentId,
        documentName: params.documentName ?? null,
        checkId: params.checkId,
        checkName: params.checkName ?? null,
        cell: detailsCell,
      });

      onOpenCell?.({
        documentId: params.documentId,
        documentName: params.documentName ?? null,
        checkId: params.checkId,
        checkName: params.checkName ?? null,
        cell: detailsCell,
      });
    },
    [onOpenCell],
  );

  const defaultColDef = useMemo<ColDef<MatrixRow>>(
    () => ({
      sortable: true,
      filter: true,
      resizable: true,
      suppressHeaderMenuButton: false,
    }),
    [],
  );

  const baseColumns = useMemo<ColDef<MatrixRow>[]>(
    () => [
      {
        headerName: "#",
        width: 64,
        pinned: "left",
        sortable: false,
        filter: false,
        valueGetter: (params: ValueGetterParams<MatrixRow>) =>
          params.node?.rowIndex != null ? params.node.rowIndex + 1 : "",
      },
      {
        headerName: "Документ",
        field: "documentName",
        minWidth: 240,
        flex: 2,
        pinned: "left",
        cellRenderer: (params: ICellRendererParams<MatrixRow>) => {
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
        headerName: "Тип документа",
        field: "docType",
        width: 150,
        valueFormatter: (params: ValueFormatterParams<MatrixRow>) =>
          (params.value as string | null | undefined) || "—",
      },
      {
        headerName: "Классификация",
        field: "classificationLevel",
        width: 150,
        cellRenderer: (params: ICellRendererParams<MatrixRow>) => {
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
        cellRenderer: (params: ICellRendererParams<MatrixRow>) => {
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
      { headerName: "Unclear", field: "totalUnclear", width: 88 },
    ],
    [onOpenDocument],
  );

  const riskColDefs = useMemo<ColDef<MatrixRow>[]>(
    () =>
      riskColumns.map((meta) => {
        const field = `risk_${meta.checkId}` as const;

        return {
          headerName: meta.checkName,
          headerTooltip: getHeaderTooltip(meta),
          field,
          minWidth: 220,
          tooltipValueGetter: (params: ITooltipParams<MatrixRow>): string => {
            const cell = params.data?.[field];
            return cell ? buildCellTooltip(cell) : "";
          },
          cellRenderer: (params: ICellRendererParams<MatrixRow>) => {
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
                      documentId: row.documentId,
                      documentName: row.documentName,
                      checkId: meta.checkId,
                      checkName: meta.checkName,
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
        } satisfies ColDef<MatrixRow>;
      }),
    [handleCellOpen, riskColumns],
  );

  const columnDefs = useMemo<ColDef<MatrixRow>[]>(
    () => [...baseColumns, ...riskColDefs],
    [baseColumns, riskColDefs],
  );

  const handleSelectionChanged = useCallback(
    (event: SelectionChangedEvent<MatrixRow>) => {
      if (!onSelectionChange) return;
      onSelectionChange(getSelectedDocumentIds(event));
    },
    [onSelectionChange],
  );

  const handleGridReady = useCallback((event: GridReadyEvent<MatrixRow>) => {
    setGridApi(event.api);
    requestAnimationFrame(() => {
      try {
        event.api.sizeColumnsToFit();
      } catch {
        /* noop */
      }
    });
  }, []);

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

  if (!hasValidData) {
    return (
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-6 text-center text-sm text-[var(--text-secondary)] shadow-sm">
        Нет данных review-матрицы для отображения.
      </div>
    );
  }

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
            <AgGridReact<MatrixRow>
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
              getRowId={(params) => params.data.documentId}
              domLayout="autoHeight"
              theme="legacy"
            />
          </div>
        </div>
      </div>

      <DDMatrixCellDetails
        open={selectedCell.open}
        onClose={closeDetails}
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




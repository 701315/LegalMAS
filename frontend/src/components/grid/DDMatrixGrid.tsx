// =============================================================
// src/components/grid/DDMatrixGrid.tsx
// Review-only DD Matrix grid.
// Работает ИСКЛЮЧИТЕЛЬНО поверх DDMatrixResponseDTO и не зависит
// от legacy CheckResult[] модели.
//
// Основные задачи:
// - рендер document × check matrix из backend dd-matrix DTO;
// - открыть side panel с деталями ячейки;
// - открыть viewer в evidence context;
// - показать segment/chunk provenance, если backend его отдает.
// =============================================================

import React, { useCallback, useMemo, useState } from "react";
import { AgGridReact } from "ag-grid-react";
import type {
  ColDef,
  ICellRendererParams,
  ITooltipParams,
  SelectionChangedEvent,
  ValueFormatterParams,
} from "ag-grid-community";

import type { OpenViewerAtFn, SeverityLevel } from "../../types";
import type {
  DDMatrixResponseDTO,
  DocumentMatrixRowDTO,
  MatrixCellDTO,
  ExtractedFieldDTO,
} from "../../types/dealReview";

import { SeverityBadge } from "../ui/SeverityBadge";
import DDMatrixCellDetails, {
  type MatrixCellDetailsCell,
} from "./DDMatrixCellDetails";

// AG Grid styles
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-alpine.css";

// -------------------------------------------------------------
// Props
// -------------------------------------------------------------

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

  height?: number;
}

// -------------------------------------------------------------
// Internal row/view models
// -------------------------------------------------------------

interface MatrixRowBase {
  documentId: string;
  documentName: string;
  docType?: string | null;
  folderPath?: string | null;

  classificationLevel?: string | null;
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

// -------------------------------------------------------------
// Helpers
// -------------------------------------------------------------

function isRiskSeverity(value: string | null | undefined): value is SeverityLevel {
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

  const rowData: MatrixRow[] = data.documents.map((doc: DocumentMatrixRowDTO) => {
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
  });

  return { rowData, riskColumns };
}

// -------------------------------------------------------------
// Main component
// -------------------------------------------------------------

export const DDMatrixGrid: React.FC<DDMatrixGridProps> = ({
  data,
  onOpenAtLocation,
  onOpenDocument,
  onOpenCell,
  onSelectionChange,
  height = 600,
}) => {
  const [selectedCell, setSelectedCell] = useState<SelectedCellState>({
    open: false,
    documentId: null,
    documentName: null,
    checkId: null,
    checkName: null,
    cell: null,
  });

  const { rowData, riskColumns } = useMemo(() => {
    if (!data || !Array.isArray(data.documents) || !Array.isArray(data.checks)) {
      return {
        rowData: [] as MatrixRow[],
        riskColumns: [] as MatrixColumnMeta[],
      };
    }

    return buildMatrixRows(data);
  }, [data]);

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
        valueGetter: (params) =>
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
            return <span className="text-xs text-gray-700">{documentName}</span>;
          }

          return (
            <button
              type="button"
              className="text-left text-xs text-blue-700 hover:underline"
              onClick={(e) => {
                e.stopPropagation();
                onOpenDocument({
                  documentId,
                  documentName,
                });
              }}
              title="Открыть документ"
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
        headerName: "Состав",
        width: 160,
        valueGetter: (params) => {
          const row = params.data;
          if (!row) return "—";
          if (row.isMultiDocument) {
            return row.segmentCount != null
              ? `multi-document · ${row.segmentCount}`
              : "multi-document";
          }
          return "single-document";
        },
      },
      {
        headerName: "Primary segment",
        field: "primarySegmentLabel",
        width: 160,
        valueFormatter: (params: ValueFormatterParams<MatrixRow>) =>
          (params.value as string | null | undefined) || "—",
      },
      {
        headerName: "Нужна проверка",
        field: "requiresManualReview",
        width: 145,
        cellRenderer: (params: ICellRendererParams<MatrixRow>) => {
          const value = params.data?.requiresManualReview;
          if (!value) {
            return <span className="text-[11px] text-gray-300">—</span>;
          }

          return (
            <span className="inline-flex items-center rounded border border-yellow-200 bg-yellow-50 px-1.5 py-0.5 text-[11px] text-yellow-700">
              Нужна проверка
            </span>
          );
        },
      },
      {
        headerName: "Crit",
        field: "totalCritical",
        width: 72,
      },
      {
        headerName: "High",
        field: "totalHigh",
        width: 72,
      },
      {
        headerName: "Med",
        field: "totalMedium",
        width: 72,
      },
      {
        headerName: "Unclear",
        field: "totalUnclear",
        width: 88,
      },
    ],
    [onOpenDocument],
  );

  const riskColDefs = useMemo<ColDef<MatrixRow>[]>(
    () =>
      riskColumns.map((meta) => {
        const field = `risk_${meta.checkId}` as const;

        return {
          headerName: meta.checkName,
          field,
          minWidth: 220,
          flex: 1,
          tooltipValueGetter: (params: ITooltipParams<MatrixRow>): string => {
          const cell = params.data?.[field];
          return cell?.snippet || "";
          },

          valueFormatter: (params: ValueFormatterParams<MatrixRow>) => {
            const cell = params.data?.[field];
            if (!cell) return "";
            if (cell.result === "fail") {
              return cell.severity ? `fail (${cell.severity})` : "fail";
            }
            return cell.result;
          },
          cellRenderer: (params: ICellRendererParams<MatrixRow>) => {
            const row = params.data;
            const cell = row?.[field];

            if (!row || !cell) {
              return <span className="text-[11px] text-gray-300">—</span>;
            }

            const statusText = getCellStatusText(cell);
            const severity = getCellSeverity(cell);
            const locationText = getCellLocationText(cell);
            const segmentText = getCellSegmentText(cell);

            return (
              <div className="flex w-full flex-col items-start gap-1 py-1 text-left">
                <button
                  type="button"
                  className="w-full text-left"
                  title={cell.snippet || ""}
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
                  <div className="text-[11px] text-gray-900">{statusText}</div>
                  {severity && (
                    <div className="mt-1 origin-left scale-90">
                      <SeverityBadge severity={severity} />
                    </div>
                  )}
                </button>

                <div className="flex w-full items-center justify-between gap-2">
                  <div className="min-w-0 truncate text-[10px] text-gray-500">
                    {locationText || "—"}
                  </div>

                  {onOpenAtLocation && (
                    <button
                      type="button"
                      className="shrink-0 text-[10px] text-blue-700 hover:underline"
                      onClick={(e) => {
                        e.stopPropagation();
                        onOpenAtLocation({
                          documentId: row.documentId,
                          page: cell.page ?? null,
                          clauseUid: cell.clause_uid ?? null,
                          elementId: null,
                          segmentId: cell.segment_id ?? null,
                          chunkId: cell.chunk_id ?? null,
                          chunkIndex: cell.chunk_index ?? null,
                        });
                      }}
                    >
                      В документ
                    </button>
                  )}
                </div>

                {segmentText && (
                  <div className="text-[10px] text-gray-500">{segmentText}</div>
                )}
              </div>
            );
          },
        } satisfies ColDef<MatrixRow>;
      }),
    [handleCellOpen, onOpenAtLocation, riskColumns],
  );

  const columnDefs = useMemo<ColDef<MatrixRow>[]>(
    () => [...baseColumns, ...riskColDefs],
    [baseColumns, riskColDefs],
  );

  const handleSelectionChanged = useCallback(
    (event: SelectionChangedEvent<MatrixRow>) => {
      if (!onSelectionChange) return;
      const ids = event.api
        .getSelectedNodes()
        .map((node) => node.data?.documentId)
        .filter((value): value is string => Boolean(value));
      onSelectionChange(ids);
    },
    [onSelectionChange],
  );

  if (!data || !rowData.length) {
    return (
      <div className="rounded-md border border-gray-200 bg-white p-4 text-sm text-gray-500">
        Нет данных для отображения в DD Matrix.
      </div>
    );
  }

  return (
    <>
      <div className="ag-theme-alpine" style={{ height, width: "100%" }}>
        <AgGridReact<MatrixRow>
          rowData={rowData}
          columnDefs={columnDefs}
          defaultColDef={defaultColDef}
          rowSelection={{
            mode: "multiRow",
            enableSelectionWithoutKeys: true,
            checkboxes: true,
            headerCheckbox: true,
          }}
          suppressCellFocus
          onSelectionChanged={handleSelectionChanged}
          getRowId={(params) => params.data.documentId}
          theme="legacy"
        />
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
                  page: payload.page ?? null,
                  clauseUid: payload.clauseUid ?? null,
                  elementId: null,
                  segmentId: payload.segmentId ?? null,
                  chunkId: payload.chunkId ?? null,
                  chunkIndex: payload.chunkIndex ?? null,
                })
            : undefined
        }
      />
    </>
  );
};

export default DDMatrixGrid;

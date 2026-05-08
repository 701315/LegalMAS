// =============================================================
// src/components/grid/DDGrid.tsx
// Legacy DD Grid:
// - режим 1: «плоский» список CheckResult (AG Grid);
// - режим 2: матрица документ × риск (wide-format, AG Grid).
// - источник данных: ТОЛЬКО legacy CheckResult[].
//   Новая review-матрица живёт в отдельном DDMatrixGrid.tsx.
// =============================================================

import React, { useMemo } from "react";
import { AgGridReact } from "ag-grid-react";
import type {
  ColDef,
  ICellRendererParams,
  ITooltipParams,
  SelectionChangedEvent,
  ValueFormatterParams,
  ValueGetterParams,
} from "ag-grid-community";

import type {
  CheckResult,
  DocumentCompositionMeta,
  OpenViewerAtFn,
  SeverityLevel,
  StructuredField,
} from "../../types";
import { SeverityBadge } from "../ui/SeverityBadge";
import { ClassificationBadge } from "../ui/ClassificationBadge";
import {
  getCompositionBadgeDataFromMeta,
  getCompositionCellValueFromMeta,
} from "../../utils/compositionHelpers";
import { buildViewerLocationPayload } from "../../utils/viewerLocation";
import QCCellRenderer from "../qc/QCCellRenderer";
import QualityFlagRenderer from "../qc/QualityFlagRenderer";

import type {
  BaseCellParams,
  GridContext,
  MatrixColumnMeta,
  MatrixRow,
} from "./gridTypes";
import {
  getLegacyManualReviewFlag,
  getLegacyPageInfo,
  getRowCompositionMeta,
} from "./gridLegacyHelpers";
import {
  buildMatrixCellTooltip,
  buildSeverityTooltip,
  getMatrixResultLabel,
  getSelectedDocumentIds,
  getSelectedResultIds,
} from "./gridHelpers";

import "ag-grid-community/styles/ag-grid.css";
import "../../styles/ag-theme-legalmas.css";

// -------------------------------------------------------------
// Props
// -------------------------------------------------------------

interface DDGridProps {
  results: CheckResult[];

  onEyeClick?: (result: CheckResult) => void;
  onDocumentClick?: (result: CheckResult) => void;
  onCheckClick?: (result: CheckResult) => void;
  onQcChange?: (
    result: CheckResult,
    newStatus: "approved" | "rejected",
  ) => void;

  /**
   * Для bulk QC:
   * - list-режим: ids результатов (CheckResult.id)
   * - matrix-режим: ids документов (document_id)
   */
  onSelectionChange?: (ids: string[]) => void;

  mode?: "matrix" | "list";

  onOpenAtLocation?: OpenViewerAtFn;

  /**
   * Словарь documentId → composition metadata.
   * Строится в GridTab из DocumentListItem[].
   * При отсутствии: composition-колонки скрыты, поведение идентично текущему.
   */
  compositionByDocId?: Map<string, DocumentCompositionMeta>;

  /**
   * Фильтр: показывать только строки с compositionType === "multi".
   * Игнорируется если compositionByDocId не передан.
   */
  onlyMultiDocument?: boolean;
}

// -------------------------------------------------------------
// Main component
// -------------------------------------------------------------

export const DDGrid: React.FC<DDGridProps> = ({ mode = "matrix", ...rest }) => {
  if (mode === "list") {
    return <ListGrid {...rest} />;
  }

  return <MatrixGrid {...rest} />;
};

export default DDGrid;

// -------------------------------------------------------------
// Shared layout
// -------------------------------------------------------------

const GRID_MIN_HEIGHT_PX = 240;

// -------------------------------------------------------------
// Matrix grid: документ × риск
// -------------------------------------------------------------

const MatrixGrid: React.FC<DDGridProps> = ({
  results,
  onEyeClick,
  onDocumentClick,
  onCheckClick,
  onSelectionChange,
  onOpenAtLocation,
  compositionByDocId,
  onlyMultiDocument,
}) => {
  const context = useMemo<GridContext>(
    () => ({
      onEyeClick,
      onDocumentClick,
      onCheckClick,
      onQcChange: undefined,
      onOpenAtLocation,
    }),
    [onEyeClick, onDocumentClick, onCheckClick, onOpenAtLocation],
  );

  const { rowData, riskColumns, legacyResultByDocumentId } = useMemo(() => {
    const docMap = new Map<string, MatrixRow>();
    const riskMetaMap = new Map<string, MatrixColumnMeta>();
    const firstResultByDocumentId = new Map<string, CheckResult>();

    for (const result of results) {
      const documentId = result.document_id;
      const checkId = result.check_id;

      if (!documentId || !checkId) {
        continue;
      }

      let row = docMap.get(documentId);

      if (!row) {
        const composition = compositionByDocId?.get(documentId) ?? null;

        row = {
          documentId,
          documentName: result.document_name || "[no name]",
          docType: result.doc_type ?? null,
          classificationLevel: result.doc_classification_level ?? null,
          classificationConfidence:
            result.doc_classification_confidence ?? null,
          requiresManualReview: getLegacyManualReviewFlag(result),

          totalCritical: 0,
          totalHigh: 0,
          totalMedium: 0,
          totalUnclear: 0,

          compositionType: composition?.composition_type ?? null,
          segmentCount: composition?.segment_count ?? null,
          primarySegmentLabel: composition?.primary_segment_label ?? null,
          isCompositeFile: composition?.is_composite_file ?? null,
        };

        docMap.set(documentId, row);
      }

      if (!riskMetaMap.has(checkId)) {
        riskMetaMap.set(checkId, {
          checkId,
          checkName: result.check_name || checkId,
          origin: result.origin ?? null,
        });
      }

      if (!firstResultByDocumentId.has(documentId)) {
        firstResultByDocumentId.set(documentId, result);
      }

      const colKey = `risk_${checkId}` as const;
      row[colKey] = result;

      if (result.severity === "critical") row.totalCritical += 1;
      if (result.severity === "high") row.totalHigh += 1;
      if (result.severity === "medium") row.totalMedium += 1;
      if (result.result === "unclear") row.totalUnclear += 1;
    }

    return {
      rowData: Array.from(docMap.values()),
      riskColumns: Array.from(riskMetaMap.values()),
      legacyResultByDocumentId: firstResultByDocumentId,
    };
  }, [results, compositionByDocId]);

  const filteredRowData = useMemo(() => {
    if (!onlyMultiDocument || !compositionByDocId) {
      return rowData;
    }

    return rowData.filter((row) => row.compositionType === "multi");
  }, [rowData, onlyMultiDocument, compositionByDocId]);

  const baseColumns = useMemo<ColDef<MatrixRow>[]>(
    () => [
      {
        headerName: "#",
        width: 60,
        pinned: "left",
        sortable: false,
        filter: false,
        valueGetter: (params: ValueGetterParams<MatrixRow>) =>
          params.node?.rowIndex != null ? params.node.rowIndex + 1 : "",
      },
      {
        headerName: "Документ",
        field: "documentName",
        minWidth: 220,
        flex: 2,
        pinned: "left",
        cellRenderer: (params: ICellRendererParams<MatrixRow>) => {
          const value =
            typeof params.value === "string" ? params.value : undefined;

          if (!value) {
            return (
              <span className="text-xs text-[var(--text-faint)]">
                [no name]
              </span>
            );
          }

          if (!onDocumentClick || legacyResultByDocumentId.size === 0) {
            return (
              <span className="text-xs text-[var(--text-primary)]">
                {value}
              </span>
            );
          }

          const handleClick = (event: React.MouseEvent<HTMLButtonElement>) => {
            event.stopPropagation();

            const documentId = params.data?.documentId;
            if (!documentId) return;

            const firstResult = legacyResultByDocumentId.get(documentId);
            if (firstResult) {
              onDocumentClick(firstResult);
            }
          };

          return (
            <button
              type="button"
              onClick={handleClick}
              className="text-xs text-[var(--accent-primary)] hover:underline"
              title="Показать все результаты по документу"
              aria-label={`Показать все результаты по документу ${value}`}
            >
              {value}
            </button>
          );
        },
      },
      {
        headerName: "Тип документа",
        field: "docType",
        width: 140,
        valueFormatter: (params: ValueFormatterParams<MatrixRow>) =>
          typeof params.value === "string" && params.value ? params.value : "—",
      },
      {
        headerName: "Классификация",
        field: "classificationLevel",
        width: 140,
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
              level={level}
              confidence={confidence ?? undefined}
              showConfidence={false}
            />
          );
        },
      },
      {
        headerName: "Нужна проверка",
        field: "requiresManualReview",
        width: 150,
        cellRenderer: (params: ICellRendererParams<MatrixRow>) => {
          const value = params.data?.requiresManualReview;

          if (!value) {
            return (
              <span className="text-[11px] text-[var(--text-faint)]">—</span>
            );
          }

          return (
            <span
              className="inline-flex items-center rounded-full border border-[var(--border-warning-soft)] bg-[var(--bg-warning-soft)] px-1.5 py-0.5 text-[11px] font-medium text-[var(--text-warning-strong)]"
              title="Классификатор пометил документ как требующий ручной проверки"
            >
              Нужна проверка
            </span>
          );
        },
      },
      ...(compositionByDocId && compositionByDocId.size > 0
        ? ([
            {
              headerName: "Состав",
              field: "compositionType" as keyof MatrixRow,
              width: 100,
              pinned: "left" as const,
              cellRenderer: (params: ICellRendererParams<MatrixRow>) => {
                const meta = getRowCompositionMeta(params.data);
                const badges = getCompositionBadgeDataFromMeta(meta);

                if (!meta) {
                  return (
                    <span className="text-[11px] text-[var(--text-faint)]">
                      —
                    </span>
                  );
                }

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
            {
              headerName: "Основной сегмент",
              colId: "primary_segment_label",
              width: 180,
              valueGetter: (params: ValueGetterParams<MatrixRow>) => {
                const meta = getRowCompositionMeta(params.data);
                const value = getCompositionCellValueFromMeta(
                  "primary_segment_label",
                  meta,
                );

                return value || "—";
              },
            },
          ] as ColDef<MatrixRow>[])
        : []),
      {
        headerName: "Crit",
        field: "totalCritical",
        width: 70,
      },
      {
        headerName: "High",
        field: "totalHigh",
        width: 70,
      },
      {
        headerName: "Med",
        field: "totalMedium",
        width: 70,
      },
      {
        headerName: "Unclear",
        field: "totalUnclear",
        width: 80,
      },
    ],
    [onDocumentClick, legacyResultByDocumentId, compositionByDocId],
  );

  const riskColumnsDefs = useMemo<ColDef<MatrixRow>[]>(
    () =>
      riskColumns.map((meta) => {
        const field = `risk_${meta.checkId}` as const;

        return {
          headerName: meta.checkName,
          headerTooltip: [
            meta.checkName,
            meta.origin ? `Источник: ${meta.origin}` : null,
          ]
            .filter(Boolean)
            .join("\n"),
          field,
          minWidth: 180,
          flex: 1,
          tooltipValueGetter: (params: ITooltipParams<MatrixRow>): string => {
            const result = params.data?.[field];
            return result ? buildMatrixCellTooltip(result) : "";
          },
          valueFormatter: (params: ValueFormatterParams<MatrixRow>) => {
            const result = params.data?.[field];
            if (!result) return "";

            if (result.result === "fail") {
              return result.severity ? `fail (${result.severity})` : "fail";
            }

            return result.result;
          },
          cellRenderer: (params: ICellRendererParams<MatrixRow>) => {
            const result = params.data?.[field];

            if (!result) {
              return (
                <span className="text-[11px] text-[var(--text-faint)]">—</span>
              );
            }

            const pageInfo = getLegacyPageInfo(result);

            const handleEyeClick = (
              event: React.MouseEvent<HTMLButtonElement>,
            ) => {
              event.stopPropagation();
              context.onEyeClick?.(result);
            };

            const handleOpenInDocument = (
              event: React.MouseEvent<HTMLButtonElement>,
            ) => {
              event.stopPropagation();

              if (!context.onOpenAtLocation || !result.document_id) {
                return;
              }

              const firstFieldWithLocation = result.structured_data
                ? Object.values(
                    result.structured_data as Record<string, StructuredField>,
                  ).find(
                    (fieldValue): fieldValue is StructuredField =>
                      Boolean(fieldValue?.location),
                  )
                : null;

              const location = firstFieldWithLocation?.location;
              context.onOpenAtLocation(
                buildViewerLocationPayload(result.document_id, location),
              );
            };

            return (
              <div className="flex w-full flex-col items-start gap-0.5 text-left">
                <button
                  type="button"
                  onClick={handleEyeClick}
                  className="w-full text-left"
                  title={buildMatrixCellTooltip(result)}
                  aria-label={`Открыть подробности риска для проверки ${meta.checkName}`}
                >
                  <span className="text-[11px] text-[var(--text-primary)]">
                    {getMatrixResultLabel(result)}
                  </span>

                  {result.severity && (
                    <div className="mt-0.5 origin-left scale-90">
                      <SeverityBadge severity={result.severity} />
                    </div>
                  )}
                </button>

                <div className="mt-0.5 flex w-full items-center justify-between gap-1">
                  <div className="text-[9px] text-[var(--text-secondary)]">
                    {pageInfo.page != null && <>стр. {pageInfo.page}</>}
                    {pageInfo.page != null && pageInfo.clauseUid && " · "}
                    {pageInfo.clauseUid}
                  </div>

                  {context.onOpenAtLocation && (
                    <button
                      type="button"
                      className="text-[9px] text-[var(--accent-primary)] hover:underline"
                      onClick={handleOpenInDocument}
                    >
                      В документ
                    </button>
                  )}
                </div>
              </div>
            );
          },
        } satisfies ColDef<MatrixRow>;
      }),
    [riskColumns, context],
  );

  const columnDefs = useMemo<ColDef<MatrixRow>[]>(
    () => [...baseColumns, ...riskColumnsDefs],
    [baseColumns, riskColumnsDefs],
  );

  const defaultColDef = useMemo<ColDef<MatrixRow>>(
    () => ({
      sortable: true,
      filter: true,
      resizable: true,
    }),
    [],
  );

  const handleSelectionChanged = (event: SelectionChangedEvent<MatrixRow>) => {
    if (!onSelectionChange) return;
    onSelectionChange(getSelectedDocumentIds(event));
  };

  if (!filteredRowData.length) {
    return (
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-3 text-xs text-[var(--text-muted)] shadow-sm">
        Нет данных для отображения в матрице.
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
      <div
        className="ag-theme-legalmas w-full"
        style={{ minHeight: GRID_MIN_HEIGHT_PX, width: "100%" }}
      >
        <AgGridReact<MatrixRow>
          rowData={filteredRowData}
          columnDefs={columnDefs}
          defaultColDef={defaultColDef}
          context={context}
          domLayout="autoHeight"
          rowSelection={{
            mode: "multiRow",
            enableSelectionWithoutKeys: true,
            checkboxes: true,
            headerCheckbox: true,
          }}
          suppressCellFocus
          suppressRowClickSelection
          onSelectionChanged={handleSelectionChanged}
          getRowId={(params) => params.data.documentId}
        />
      </div>
    </div>
  );
};

// -------------------------------------------------------------
// List grid: legacy flat CheckResult[] mode
// -------------------------------------------------------------

const ListGrid: React.FC<DDGridProps> = ({
  results,
  onEyeClick,
  onDocumentClick,
  onCheckClick,
  onQcChange,
  onSelectionChange,
  onOpenAtLocation,
}) => {
  const context = useMemo<GridContext>(
    () => ({
      onEyeClick,
      onDocumentClick,
      onCheckClick,
      onQcChange,
      onOpenAtLocation,
    }),
    [onEyeClick, onDocumentClick, onCheckClick, onQcChange, onOpenAtLocation],
  );

  const columnDefs = useMemo<ColDef<CheckResult>[]>(
    () => [
      {
        headerName: "",
        width: 40,
        pinned: "left",
        sortable: false,
        filter: false,
      },
      {
        headerName: "Risk",
        field: "severity",
        width: 170,
        pinned: "left",
        tooltipValueGetter: (params: ITooltipParams<CheckResult>) =>
          params.data ? buildSeverityTooltip(params.data) : "",
        cellRenderer: SeverityCellRenderer,
      },
      {
        headerName: "Summary",
        field: "value_text",
        flex: 2,
        minWidth: 260,
        valueGetter: (params: ValueGetterParams<CheckResult>) =>
          params.data?.value_text || "",
      },
      {
        headerName: "Check",
        field: "check_name",
        flex: 1.8,
        minWidth: 220,
        cellRenderer: CheckNameCellRenderer,
      },
      {
        headerName: "Document",
        field: "document_name",
        flex: 2,
        minWidth: 220,
        cellRenderer: DocumentCellRenderer,
      },
      {
        headerName: "Doc Type",
        field: "doc_type",
        flex: 1,
        minWidth: 120,
      },
      {
        headerName: "Class.",
        field: "doc_classification_level",
        width: 130,
        cellRenderer: (params: ICellRendererParams<CheckResult>) => {
          const level = params.data?.doc_classification_level;
          const confidence = params.data?.doc_classification_confidence;

          if (!level) {
            return (
              <span className="text-[11px] text-[var(--text-faint)]">—</span>
            );
          }

          return (
            <ClassificationBadge
              level={level}
              confidence={confidence ?? undefined}
            />
          );
        },
      },
      {
        headerName: "Result",
        field: "result",
        flex: 0.8,
        minWidth: 110,
      },
      {
        headerName: "Conf.",
        field: "confidence",
        width: 90,
        valueFormatter: (params: ValueFormatterParams<CheckResult>) => {
          const value =
            typeof params.value === "number" ? params.value : undefined;
          if (value == null) return "";
          return `${Math.round(value * 100)}%`;
        },
      },
      {
        headerName: "QC",
        field: "qc_status",
        width: 160,
        cellRenderer: (params: ICellRendererParams<CheckResult>) => (
          <QCCellRenderer
            value={params.data?.qc_status ?? undefined}
            data={params.data as CheckResult}
            onQcChange={context.onQcChange}
          />
        ),
      },
      {
        headerName: "Flags",
        field: "quality_flags",
        width: 90,
        valueFormatter: (params: ValueFormatterParams<CheckResult>) =>
          params.value ? JSON.stringify(params.value) : "",
        cellRenderer: (params: ICellRendererParams<CheckResult>) => (
          <QualityFlagRenderer result={params.data as CheckResult} />
        ),
      },
      {
        headerName: "Cond.",
        field: "conditional_check_triggered",
        width: 90,
        cellRenderer: ConditionalCellRenderer,
      },
      {
        headerName: "Trigger",
        field: "trigger_name",
        flex: 1,
        minWidth: 140,
        cellRenderer: (params: ICellRendererParams<CheckResult>) => {
          const triggered = params.data?.conditional_check_triggered;
          const name = params.data?.trigger_name;

          if (!triggered) {
            return (
              <span className="text-[11px] text-[var(--text-faint)]">—</span>
            );
          }

          return (
            <span
              className="inline-flex items-center gap-1 rounded-full border border-[var(--border-conditional-soft)] bg-[var(--bg-conditional-soft)] px-1.5 py-0.5 text-[11px] text-[var(--text-conditional-strong)]"
              title={name || "Conditional check triggered"}
            >
              ⚡ {name || "Conditional"}
            </span>
          );
        },
      },
      {
        headerName: "Detector",
        field: "detector_used",
        flex: 0.8,
        minWidth: 110,
      },
      {
        headerName: "Extracted",
        colId: "structured_data",
        flex: 1.4,
        minWidth: 220,
        valueGetter: (params: ValueGetterParams<CheckResult>) => {
          const structuredData = params.data?.structured_data as
            | Record<string, StructuredField>
            | null
            | undefined;

          if (!structuredData || typeof structuredData !== "object") {
            return "";
          }

          const entries = Object.entries(structuredData);
          if (!entries.length) {
            return "";
          }

          return entries
            .slice(0, 2)
            .map(([name, field]) => {
              const value = field?.value != null ? String(field.value) : "—";
              return `${name}: ${value}`;
            })
            .join("; ");
        },
        cellRenderer: StructuredDataCellRenderer,
      },
      {
        headerName: "Origin",
        field: "origin",
        flex: 0.8,
        minWidth: 130,
      },
      {
        headerName: "Created",
        field: "created_at",
        minWidth: 160,
        hide: true,
        valueFormatter: (params: ValueFormatterParams<CheckResult>) => {
          if (!params.value) return "";
          const date = new Date(String(params.value));
          return date.toLocaleString();
        },
      },
    ],
    [context.onQcChange],
  );

  const defaultColDef = useMemo<ColDef<CheckResult>>(
    () => ({
      sortable: true,
      filter: true,
      resizable: true,
    }),
    [],
  );

  const handleSelectionChanged = (
    event: SelectionChangedEvent<CheckResult>,
  ) => {
    if (!onSelectionChange) return;
    onSelectionChange(getSelectedResultIds(event));
  };

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
      <div
        className="ag-theme-legalmas w-full"
        style={{ minHeight: GRID_MIN_HEIGHT_PX, width: "100%" }}
      >
        <AgGridReact<CheckResult>
          rowData={results}
          columnDefs={columnDefs}
          defaultColDef={defaultColDef}
          context={context}
          domLayout="autoHeight"
          rowSelection={{
            mode: "multiRow",
            enableSelectionWithoutKeys: true,
            checkboxes: true,
            headerCheckbox: true,
          }}
          suppressCellFocus
          suppressRowClickSelection
          onSelectionChanged={handleSelectionChanged}
          getRowId={(params) => params.data.id}
        />
      </div>
    </div>
  );
};

// -------------------------------------------------------------
// List mode cell renderers
// -------------------------------------------------------------

const SeverityCellRenderer: React.FC<BaseCellParams> = ({
  value,
  data,
  context,
}) => {
  const handleEyeClick = (event: React.MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    context.onEyeClick?.(data);
  };

  const showConditional = data.conditional_check_triggered;
  const severityValue =
    typeof value === "string" ? (value as SeverityLevel) : undefined;

  return (
    <div className="flex items-center gap-2">
      <div className="flex items-center gap-1">
        {severityValue ? (
          <SeverityBadge severity={severityValue} />
        ) : (
          <span className="text-[11px] text-[var(--text-faint)]">—</span>
        )}

        {showConditional && (
          <span
            className="text-[13px]"
            title={data.trigger_name || "Conditional check triggered"}
          >
            ⚡
          </span>
        )}
      </div>

      <button
        type="button"
        className="rounded-md border border-[var(--border-subtle)] px-1 py-0.5 text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)]"
        onClick={handleEyeClick}
        title="Открыть подробности"
        aria-label="Открыть подробности результата"
      >
        👁
      </button>
    </div>
  );
};

const DocumentCellRenderer: React.FC<BaseCellParams> = ({
  value,
  data,
  context,
}) => {
  const handleClick = (event: React.MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    context.onDocumentClick?.(data);
  };

  const documentName = typeof value === "string" ? value : "";

  if (!documentName) {
    return <span className="text-[var(--text-faint)]">[no name]</span>;
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      className="text-xs text-[var(--accent-primary)] hover:underline"
      title="Показать все результаты по документу"
      aria-label={`Показать все результаты по документу ${documentName}`}
    >
      {documentName}
    </button>
  );
};

const CheckNameCellRenderer: React.FC<BaseCellParams> = ({
  value,
  data,
  context,
}) => {
  const handleClick = (event: React.MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    context.onCheckClick?.(data);
  };

  const checkName = typeof value === "string" ? value : "";

  if (!checkName) {
    return null;
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      className="text-xs text-[var(--accent-primary)] hover:underline"
      title="Показать все результаты этой проверки"
      aria-label={`Показать все результаты проверки ${checkName}`}
    >
      {checkName}
    </button>
  );
};

const ConditionalCellRenderer: React.FC<BaseCellParams> = ({ data }) => {
  const triggered = data.conditional_check_triggered;
  const triggerName = data.trigger_name;

  if (!triggered) {
    return <span className="text-[11px] text-[var(--text-faint)]">—</span>;
  }

  return (
    <span
      className="text-[11px] text-[var(--text-conditional-strong)]"
      title={triggerName || "Conditional check triggered"}
    >
      ⚡
    </span>
  );
};

const StructuredDataCellRenderer: React.FC<BaseCellParams> = ({
  data,
  context,
}) => {
  const structuredData = data.structured_data as
    | Record<string, StructuredField>
    | null
    | undefined;

  if (!structuredData || typeof structuredData !== "object") {
    return <span className="text-[11px] text-[var(--text-faint)]">—</span>;
  }

  const entries = Object.entries(structuredData);
  if (!entries.length) {
    return <span className="text-[11px] text-[var(--text-faint)]">—</span>;
  }

  const maxShown = 2;
  const shown = entries.slice(0, maxShown);
  const rest = entries.length - shown.length;

  const handleOpen = (field: StructuredField) => {
    if (!field.location || !context.onOpenAtLocation) {
      return;
    }

    context.onOpenAtLocation(
      buildViewerLocationPayload(data.document_id, field.location),
    );
  };

  return (
    <div className="flex flex-col gap-0.5 text-[11px]">
      {shown.map(([name, field]) => {
        const structuredField = (field || {}) as StructuredField;
        const value =
          structuredField.value != null ? String(structuredField.value) : "—";
        const confidence =
          typeof structuredField.confidence === "number"
            ? `${Math.round(structuredField.confidence * 100)}%`
            : "";
        const source = structuredField.source || "";
        const hasLocation = Boolean(structuredField.location);

        return (
          <div key={name} className="flex items-center gap-1">
            <span className="max-w-[35%] truncate text-[var(--text-muted)]">
              {name}
            </span>

            <span className="flex-1 truncate text-right text-[var(--text-primary)]">
              {value}
              {confidence && (
                <span className="ml-1 text-[var(--text-faint)]">
                  ({confidence})
                </span>
              )}
              {source && (
                <span className="ml-1 text-[var(--text-faint)]">
                  [{source}]
                </span>
              )}
            </span>

            {hasLocation && (
              <button
                type="button"
                className="ml-1 whitespace-nowrap text-[var(--accent-primary)] hover:underline"
                onClick={(event) => {
                  event.stopPropagation();
                  handleOpen(structuredField);
                }}
                title="Открыть фрагмент документа"
                aria-label={`Открыть фрагмент документа для поля ${name}`}
              >
                Фрагмент
              </button>
            )}
          </div>
        );
      })}

      {rest > 0 && (
        <span className="text-[var(--text-faint)]">… ещё {rest}</span>
      )}
    </div>
  );
};




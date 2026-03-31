// =============================================================
// src/components/grid/DDGrid.tsx
// DD Grid:
// - режим 1: «плоский» список CheckResult (AG Grid);
// - режим 2: матрица документ × риск (wide-format, AG Grid).
// =============================================================

import React, { useMemo } from "react";
import { AgGridReact } from "ag-grid-react";
import type {
  ColDef,
  ICellRendererParams,
  ValueGetterParams,
  SelectionChangedEvent,
  ITooltipParams,
} from "ag-grid-community";

import type {
  CheckResult,
  OpenViewerAtFn,
  StructuredField,
  ClassificationLevel,
  SeverityLevel,
} from "../../types";
import { SeverityBadge } from "../ui/SeverityBadge";
import { ClassificationBadge } from "../ui/ClassificationBadge";
import QCCellRenderer from "../qc/QCCellRenderer";
import QualityFlagRenderer from "../qc/QualityFlagRenderer";

// AG Grid стили
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-alpine.css";

interface DDGridProps {
  results: CheckResult[];
  onEyeClick?: (result: CheckResult) => void;
  onDocumentClick?: (result: CheckResult) => void;
  onCheckClick?: (result: CheckResult) => void;
  onQcChange?: (
    result: CheckResult,
    newStatus: "approved" | "rejected",
  ) => void;

  // для bulk QC:
  // - в режиме list: ids результатов (CheckResult.id)
  // - в режиме matrix: ids документов (document_id)
  onSelectionChange?: (ids: string[]) => void;

  // Режим отображения: матрица или список
  mode?: "matrix" | "list";

  // Открыть viewer на конкретном фрагменте
  onOpenAtLocation?: OpenViewerAtFn;
}

interface GridContext {
  onEyeClick?: (result: CheckResult) => void;
  onDocumentClick?: (result: CheckResult) => void;
  onCheckClick?: (result: CheckResult) => void;
  onQcChange?: (
    result: CheckResult,
    newStatus: "approved" | "rejected",
  ) => void;
  onOpenAtLocation?: OpenViewerAtFn;
}

// -------------------------------------------------------------
// Типы для матричного режима (строка = документ)
// -------------------------------------------------------------

interface MatrixRowBase {
  documentId: string;
  documentName: string;
  docType?: string | null;
  classificationLevel?: ClassificationLevel | null;
  classificationConfidence?: number | null;
  requiresManualReview?: boolean; // NEW: флаг manual review из DD Matrix

  totalCritical: number;
  totalHigh: number;
  totalMedium: number;
  totalUnclear: number;
}

// динамические поля: risk_<checkId> -> CheckResult
type MatrixRow = MatrixRowBase & {
  [key: `risk_${string}`]: CheckResult | undefined;
};

interface MatrixColumnMeta {
  checkId: string;
  checkName: string;
  origin?: string | null;
}

// -------------------------------------------------------------
// Главный компонент
// -------------------------------------------------------------

export const DDGrid: React.FC<DDGridProps> = ({ mode = "matrix", ...rest }) => {
  if (mode === "list") {
    return <ListGrid {...rest} />;
  }
  return <MatrixGrid {...rest} />;
};

export default DDGrid;

// -------------------------------------------------------------
// Матричный grid: документ × риск (AG Grid)
// -------------------------------------------------------------

const MatrixGrid: React.FC<DDGridProps> = ({
  results,
  onEyeClick,
  onDocumentClick,
  onCheckClick,
  onSelectionChange,
  onOpenAtLocation, // пока не используем в матрице, но оставляем в пропсах
}) => {
  const { rowData, riskColumns } = useMemo(() => {
    const docMap = new Map<string, MatrixRow>();
    const riskMetaMap = new Map<string, MatrixColumnMeta>();

    for (const r of results) {
      const docId = r.document_id;
      const checkId = r.check_id;

      if (!docId || !checkId) continue;

      let row = docMap.get(docId);
      if (!row) {
        row = {
          documentId: docId,
          documentName: r.document_name || "[no name]",
          docType: r.doc_type ?? null,
          classificationLevel: r.doc_classification_level ?? null,
          classificationConfidence: r.doc_classification_confidence ?? null,
          // Для матричного режима CheckResult приходит из DD Matrix:
          // backend кладёт туда метаданные документа (в т. ч. флаг manual review).
          requiresManualReview: r.doc_requires_manual_review ?? false,
          totalCritical: 0,
          totalHigh: 0,
          totalMedium: 0,
          totalUnclear: 0,
        };
        docMap.set(docId, row);
      }

      if (!riskMetaMap.has(checkId)) {
        riskMetaMap.set(checkId, {
          checkId,
          checkName: r.check_name || checkId,
          origin: r.origin ?? null,
        });
      }

      const colKey = `risk_${checkId}` as const;
      row[colKey] = r;

      if (r.severity === "critical") row.totalCritical += 1;
      if (r.severity === "high") row.totalHigh += 1;
      if (r.severity === "medium") row.totalMedium += 1;
      if (r.result === "unclear") row.totalUnclear += 1;
    }

    return {
      rowData: Array.from(docMap.values()),
      riskColumns: Array.from(riskMetaMap.values()),
    };
  }, [results]);

  const context: GridContext = {
    onEyeClick,
    onDocumentClick,
    onCheckClick,
    onQcChange: undefined,
    onOpenAtLocation,
  };

  const baseColumns = useMemo<ColDef<MatrixRow>[]>(
    () => [
      {
        headerName: "#",
        width: 60,
        valueGetter: (params) =>
          params.node?.rowIndex != null ? params.node.rowIndex + 1 : "",
        pinned: "left",
      },
      {
        headerName: "Документ",
        field: "documentName",
        minWidth: 220,
        flex: 2,
        pinned: "left",
        cellRenderer: (p: ICellRendererParams<MatrixRow>) => {
          const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
            e.stopPropagation();
            if (!onDocumentClick) return;
            const docId = p.data?.documentId;
            if (!docId) return;
            const first = results.find((r) => r.document_id === docId);
            if (first) onDocumentClick(first);
          };
          return (
            <button
              type="button"
              onClick={handleClick}
              className="text-xs text-blue-600 hover:underline"
            >
              {p.value}
            </button>
          );
        },
      },
      {
        headerName: "Тип документа",
        field: "docType",
        width: 140,
      },
      {
        headerName: "Классификация",
        field: "classificationLevel",
        width: 140,
        cellRenderer: (params: ICellRendererParams<MatrixRow>) => {
          const level = params.data?.classificationLevel;
          const conf = params.data?.classificationConfidence;
          if (!level) {
            return <span className="text-[11px] text-gray-300">—</span>;
          }
          return (
            <ClassificationBadge
              level={level}
              confidence={conf ?? undefined}
              showConfidence={false}
            />
          );
        },
      },
      {
        headerName: "Нужна проверка",
        field: "requiresManualReview",
        width: 140,
        cellRenderer: (params: ICellRendererParams<MatrixRow>) => {
          const v = params.data?.requiresManualReview;
          if (!v) {
            return <span className="text-[11px] text-gray-300">—</span>;
          }
          return (
            <span
              className="inline-flex items-center px-1.5 py-0.5 rounded bg-yellow-50 text-[11px] text-yellow-700 border border-yellow-200"
              title="Классификатор пометил документ как требующий ручной проверки"
            >
              Нужна проверка
            </span>
          );
        },
      },
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
    [onDocumentClick, results],
  );

  const riskCols = useMemo<ColDef<MatrixRow>[]>(
    () =>
      riskColumns.map((meta) => {
        const field = `risk_${meta.checkId}` as const;

        return {
          headerName: meta.checkName,
          field,
          minWidth: 180,
          flex: 1,
          valueFormatter: (params) => {
            const res = params.data?.[field];
            if (!res) return "";
            if (res.result === "fail") {
              return res.severity ? `fail (${res.severity})` : "fail";
            }
            return res.result;
          },
          tooltipValueGetter: (
            params: ITooltipParams<MatrixRow>,
          ): string => {
            const res = params.data?.[field];
            return res?.value_text || "";
          },
          cellRenderer: (p: ICellRendererParams<MatrixRow>) => {
            const res = p.data?.[field];
            if (!res) {
              return (
                <span className="text-[11px] text-gray-300">—</span>
              );
            }

            const { result, severity } = res;

            let textStatus = "";
            if (result === "fail") {
              if (severity === "critical" || severity === "high") {
                textStatus = "Требует внимания юриста";
              } else {
                textStatus = "Идентифицирован";
              }
            } else if (result === "unclear") {
              textStatus = "Требует внимания юриста";
            } else {
              textStatus = "Не найден";
            }

            const handleClick = (
              e: React.MouseEvent<HTMLButtonElement>,
            ) => {
              e.stopPropagation();
              onEyeClick?.(res);
            };

            return (
              <button
                type="button"
                onClick={handleClick}
                className="flex flex-col items-start gap-0.5 text-left w-full"
                title={res.value_text || ""}
              >
                <span className="text-[11px]">{textStatus}</span>
                {severity && (
                  <div className="scale-90 origin-left">
                    <SeverityBadge severity={severity} />
                  </div>
                )}
              </button>
            );
          },
        } satisfies ColDef<MatrixRow>;
      }),
    [riskColumns, onEyeClick],
  );

  const columnDefs = useMemo<ColDef<MatrixRow>[]>(
    () => [...baseColumns, ...riskCols],
    [baseColumns, riskCols],
  );

  const defaultColDef = useMemo<ColDef>(
    () => ({
      sortable: true,
      filter: true,
      resizable: true,
    }),
    [],
  );

  const handleSelectionChanged = (
    event: SelectionChangedEvent<MatrixRow>,
  ) => {
    if (!onSelectionChange) return;
    const ids: string[] = event.api
      .getSelectedNodes()
      .map((n) => n.data!.documentId);
    onSelectionChange(ids);
  };

  if (!rowData.length) {
    return (
      <div className="text-xs text-gray-400 p-3">
        Нет результатов проверок для отображения.
      </div>
    );
  }

  return (
    <div className="ag-theme-alpine" style={{ height: 600, width: "100%" }}>
      <AgGridReact<MatrixRow>
        rowData={rowData}
        columnDefs={columnDefs}
        defaultColDef={defaultColDef}
        context={context}
        rowSelection={{
          mode: "multiRow",
          enableSelectionWithoutKeys: true,
          checkboxes: true,
          headerCheckbox: true,
        }}
        suppressCellFocus={true}
        onSelectionChanged={handleSelectionChanged}
        getRowId={(params) => params.data.documentId}
        theme="legacy"
      />
    </div>
  );
};

// -------------------------------------------------------------
// Список (AG Grid) — для режима mode="list"
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
  const context: GridContext = {
    onEyeClick,
    onDocumentClick,
    onCheckClick,
    onQcChange,
    onOpenAtLocation,
  };

  const columnDefs = useMemo<ColDef<CheckResult>[]>(
    () => [
      {
        headerName: "",
        width: 40,
        pinned: "left",
      },
      {
        headerName: "Risk",
        field: "severity",
        width: 170,
        pinned: "left",
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
          const conf = params.data?.doc_classification_confidence;
          if (!level) {
            return (
              <span className="text-[11px] text-gray-300">—</span>
            );
          }
          return (
            <ClassificationBadge
              level={level}
              confidence={conf}
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
        valueFormatter: (params) => {
          const v = params.value as number | null | undefined;
          if (v == null) return "";
          return `${Math.round(v * 100)}%`;
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
        valueFormatter: (params) =>
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
              <span className="text-[11px] text-gray-300">—</span>
            );
          }
          return (
            <span
              className="inline-flex items=center gap-1 px-1.5 py-0.5 rounded bg-purple-50 text-purple-700 border border-purple-200 text-[11px]"
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
        field: "structured_data",
        flex: 1.4,
        minWidth: 220,
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
        valueFormatter: (params) => {
          if (!params.value) return "";
          const d = new Date(params.value as string);
          return d.toLocaleString();
        },
      },
    ],
    [context.onQcChange],
  );

  const defaultColDef = useMemo<ColDef>(
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
    const ids: string[] = event.api
      .getSelectedNodes()
      .map((n) => (n.data as CheckResult).id);
    onSelectionChange(ids);
  };

  return (
    <div className="ag-theme-alpine" style={{ height: 600, width: "100%" }}>
      <AgGridReact<CheckResult>
        rowData={results}
        columnDefs={columnDefs}
        defaultColDef={defaultColDef}
        context={context}
        rowSelection={{
          mode: "multiRow",
          enableSelectionWithoutKeys: true,
          checkboxes: true,
          headerCheckbox: true,
        }}
        suppressCellFocus={true}
        onSelectionChanged={handleSelectionChanged}
        getRowId={(params) => params.data.id}
        theme="legacy"
      />
    </div>
  );
};

// -------------------------------------------------------------
// Cell renderers для списка
// -------------------------------------------------------------

interface BaseCellParams
  extends ICellRendererParams<CheckResult, SeverityLevel | undefined> {
  context: GridContext;
  data: CheckResult;
}

const SeverityCellRenderer: React.FC<BaseCellParams> = (props) => {
  const { value, data, context } = props;

  const handleEyeClick = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    context.onEyeClick?.(data);
  };

  const showConditional = data.conditional_check_triggered;

  return (
    <div className="flex items-center gap-2">
      <div className="flex items-center gap-1">
        {value ? (
          <SeverityBadge severity={value} />
        ) : (
          <span className="text-[11px] text-gray-300">—</span>
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
        className="text-xs px-1 py-0.5 border rounded hover:bg-gray-100"
        onClick={handleEyeClick}
        title="Открыть подробности"
      >
        👁
      </button>
    </div>
  );
};

const DocumentCellRenderer: React.FC<BaseCellParams> = (props) => {
  const { value, data, context } = props;

  const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    context.onDocumentClick?.(data);
  };

  if (!value) return <span className="text-gray-400">[no name]</span>;

  return (
    <button
      type="button"
      onClick={handleClick}
      className="text-xs text-blue-600 hover:underline"
      title="Показать все результаты по документу"
    >
      {value}
    </button>
  );
};

const CheckNameCellRenderer: React.FC<BaseCellParams> = (props) => {
  const { value, data, context } = props;

  const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    context.onCheckClick?.(data);
  };

  if (!value) return null;

  return (
    <button
      type="button"
      onClick={handleClick}
      className="text-xs text-blue-600 hover:underline"
      title="Показать все результаты этой проверки"
    >
      {value}
    </button>
  );
};

const ConditionalCellRenderer: React.FC<BaseCellParams> = (props) => {
  const { data } = props;
  const triggered = data.conditional_check_triggered;
  const triggerName = data.trigger_name;

  if (!triggered) {
    return <span className="text-[11px] text-gray-300">—</span>;
  }

  return (
    <span
      className="text-[11px] text-purple-700"
      title={triggerName || "Conditional check triggered"}
    >
      ⚡
    </span>
  );
};

// Краткий renderer извлечённых данных для list‑таблицы.
// Показываем до 2 полей и даём клик "Фрагмент" при наличии location.
const StructuredDataCellRenderer: React.FC<BaseCellParams> = (props) => {
  const { data, context } = props;
  const sd = data.structured_data as
    | Record<string, StructuredField>
    | null
    | undefined;

  if (!sd || typeof sd !== "object") {
    return <span className="text-[11px] text-gray-300">—</span>;
  }

  const entries = Object.entries(sd);
  if (!entries.length) {
    return <span className="text-[11px] text-gray-300">—</span>;
  }

  const maxShown = 2;
  const shown = entries.slice(0, maxShown);
  const rest = entries.length - shown.length;

  const handleOpen = (field: StructuredField) => {
    if (!field.location || !context.onOpenAtLocation) return;
    context.onOpenAtLocation({
      documentId: data.document_id,
      page: field.location.page ?? field.location.start_page ?? null,
      clauseUid: field.location.clause_uid ?? null,
      elementId: field.location.element_id ?? null,
    });
  };

  return (
    <div className="flex flex-col gap-0.5 text-[11px]">
      {shown.map(([name, field]) => {
        const f = (field || {}) as StructuredField;
        const value = f.value != null ? String(f.value) : "—";
        const conf =
          typeof f.confidence === "number"
            ? `${Math.round(f.confidence * 100)}%`
            : "";
        const source = f.source || "";
        const hasLocation = !!f.location;

        return (
          <div key={name} className="flex items-center gap-1">
            <span className="text-gray-500 truncate max-w-[35%]">
              {name}
            </span>
            <span className="text-gray-800 truncate flex-1 text-right">
              {value}
              {conf && (
                <span className="text-gray-400 ml-1">({conf})</span>
              )}
              {source && (
                <span className="text-gray-400 ml-1">[{source}]</span>
              )}
            </span>
            {hasLocation && (
              <button
                type="button"
                className="ml-1 text-blue-600 hover:underline whitespace-nowrap"
                onClick={(e) => {
                  e.stopPropagation();
                  handleOpen(f);
                }}
                title="Открыть фрагмент документа"
              >
                Фрагмент
              </button>
            )}
          </div>
        );
      })}
      {rest > 0 && (
        <span className="text-gray-400">… ещё {rest}</span>
      )}
    </div>
  );
};

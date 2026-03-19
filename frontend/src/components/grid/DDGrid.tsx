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
} from "ag-grid-community";

import type { CheckResult } from "../../types";
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
  onQcChange?: (result: CheckResult, newStatus: "approved" | "rejected") => void;

  // для bulk QC:
  // - в режиме list: ids результатов (CheckResult.id)
  // - в режиме matrix: ids документов (document_id)
  onSelectionChange?: (ids: string[]) => void;

  // Режим отображения: матрица или список
  mode?: "matrix" | "list";
}

interface GridContext {
  onEyeClick?: (result: CheckResult) => void;
  onDocumentClick?: (result: CheckResult) => void;
  onCheckClick?: (result: CheckResult) => void;
  onQcChange?: (result: CheckResult, newStatus: "approved" | "rejected") => void;
}

// -------------------------------------------------------------
// Типы для матричного режима (строка = документ)
// -------------------------------------------------------------

interface MatrixRow {
  documentId: string;
  documentName: string;
  docType?: string | null;
  classificationLevel?: string | null;
  classificationConfidence?: number | null;

  totalCritical: number;
  totalHigh: number;
  totalMedium: number;
  totalUnclear: number;

  [key: string]: any;
}

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

      const colKey = `risk_${checkId}`;
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
          const handleClick = (e: React.MouseEvent) => {
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
              level={level as any}
              confidence={conf ?? undefined}
              showConfidence={false}
            />
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
        const field = `risk_${meta.checkId}`;
        return {
          headerName: meta.checkName,
          field,
          minWidth: 180,
          flex: 1,
          tooltipValueGetter: (p: any) => {
            const res: CheckResult | undefined = p.data?.[field];
            return res?.value_text || "";
          },
          cellRenderer: (p: ICellRendererParams<MatrixRow>) => {
            const res: CheckResult | undefined = p.data?.[field];
            if (!res) {
              return <span className="text-[11px] text-gray-300">—</span>;
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

            const handleClick = (e: React.MouseEvent) => {
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
                    <SeverityBadge severity={severity as any} />
                  </div>
                )}
              </button>
            );
          },
        } as ColDef<MatrixRow>;
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

  const handleSelectionChanged = (event: any) => {
    if (!onSelectionChange) return;
    const ids: string[] = event.api
      .getSelectedNodes()
      .map((n: any) => (n.data as MatrixRow).documentId);
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
}) => {
  const context: GridContext = {
    onEyeClick,
    onDocumentClick,
    onCheckClick,
    onQcChange,
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
            return <span className="text-[11px] text-gray-300">—</span>;
          }
          return <ClassificationBadge level={level} confidence={conf} />;
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
            value={params.value as string | undefined}
            data={params.data as CheckResult}
            onQcChange={context.onQcChange}
          />
        ),
      },
      {
        headerName: "Flags",
        field: "quality_flags",
        width: 90,
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
            return <span className="text-[11px] text-gray-300">—</span>;
          }
          return (
            <span
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-purple-50 text-purple-700 border border-purple-200 text-[11px]"
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
      // ВРЕМЕННАЯ колонка для отладки origin
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

  const handleSelectionChanged = (event: any) => {
    if (!onSelectionChange) return;
    const ids: string[] = event.api
      .getSelectedNodes()
      .map((n: any) => (n.data as CheckResult).id);
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

interface BaseCellParams extends ICellRendererParams<CheckResult, any> {
  context: GridContext;
  data: CheckResult;
}

const SeverityCellRenderer: React.FC<BaseCellParams> = (props) => {
  const { value, data, context } = props;

  const handleEyeClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    context.onEyeClick?.(data);
  };

  const showConditional = data.conditional_check_triggered;

  return (
    <div className="flex items-center gap-2">
      <div className="flex items-center gap-1">
        <SeverityBadge severity={value as any} />
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

  const handleClick = (e: React.MouseEvent) => {
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

  const handleClick = (e: React.MouseEvent) => {
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

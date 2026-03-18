// =============================================================
// src/components/grid/DDGrid.tsx
// DD Grid:
// - режим 1: «плоский» список CheckResult (AG Grid);
// - режим 2: матрица документ × риск (wide-format).
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

  // для bulk QC
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
// Новый матричный вариант
// -------------------------------------------------------------

interface MatrixDoc {
  id: string;
  name: string;
  docType?: string | null;
  classificationLevel?: string | null;
  classificationConfidence?: number | null;
}

interface MatrixCheck {
  id: string;
  name: string;
}

export const DDGrid: React.FC<DDGridProps> = ({ mode = "matrix", ...rest }) => {
  if (mode === "list") {
    return <ListGrid {...rest} />;
  }
  return <MatrixGrid {...rest} />;
};

// -------------------------------------------------------------
// Матричный grid: документ × риск
// -------------------------------------------------------------

const MatrixGrid: React.FC<DDGridProps> = ({
  results,
  onEyeClick,
  onDocumentClick,
  onCheckClick,
}) => {
  // Собираем уникальные документы и проверки + матрицу result'ов
  const { documents, checks, matrix } = useMemo(() => {
    const docsMap = new Map<string, MatrixDoc>();
    const checksMap = new Map<string, MatrixCheck>();
    const m = new Map<string, Map<string, CheckResult>>();

    for (const r of results) {
      const docId = r.document_id;
      const checkId = r.check_id;

      if (!docId || !checkId) continue;

      // Документы
      if (!docsMap.has(docId)) {
        docsMap.set(docId, {
          id: docId,
          name: r.document_name || "[no name]",
          docType: r.doc_type,
          classificationLevel: r.doc_classification_level,
          classificationConfidence: r.doc_classification_confidence ?? null,
        });
      }

      // Чеки
      if (!checksMap.has(checkId)) {
        checksMap.set(checkId, {
          id: checkId,
          name: r.check_name || checkId,
        });
      }

      // Матрица
      let row = m.get(docId);
      if (!row) {
        row = new Map<string, CheckResult>();
        m.set(docId, row);
      }
      row.set(checkId, r);
    }

    return {
      documents: Array.from(docsMap.values()),
      checks: Array.from(checksMap.values()),
      matrix: m,
    };
  }, [results]);

  if (documents.length === 0 || checks.length === 0) {
    return (
      <div className="text-xs text-gray-400 p-3">
        Нет результатов проверок для отображения.
      </div>
    );
  }

  const getCell = (docId: string, checkId: string): CheckResult | undefined => {
    const row = matrix.get(docId);
    return row?.get(checkId);
  };

  return (
    <div className="w-full overflow-auto border border-gray-200 rounded-md bg-white">
      <table className="min-w-full text-xs border-collapse">
        <thead>
          <tr className="bg-gray-50">
            <th className="px-2 py-2 text-left text-gray-500 font-semibold sticky left-0 bg-gray-50 z-10">
              Документ
            </th>
            {checks.map((check) => (
              <th
                key={check.id}
                className="px-2 py-2 text-center text-gray-500 font-semibold border-l border-gray-200"
                title={check.name}
              >
                <button
                  type="button"
                  className="text-[11px] text-blue-600 hover:underline"
                  onClick={() => {
                    // при клике по заголовку: показать все результаты этого чека
                    const first = results.find((r) => r.check_id === check.id);
                    if (first && onCheckClick) onCheckClick(first);
                  }}
                >
                  {check.name}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {documents.map((doc, rowIdx) => (
            <tr
              key={doc.id}
              className={rowIdx % 2 === 0 ? "bg-white" : "bg-gray-50/50"}
            >
              {/* Левый столбец: документ + классификация */}
              <td className="px-2 py-2 sticky left-0 bg-white z-10 border-t border-gray-100">
                <div className="flex flex-col gap-0.5">
                  <button
                    type="button"
                    className="text-xs text-blue-600 hover:underline text-left"
                    onClick={() => {
                      const first = results.find((r) => r.document_id === doc.id);
                      if (first && onDocumentClick) onDocumentClick(first);
                    }}
                  >
                    {doc.name}
                  </button>
                  <div className="flex items-center gap-1">
                    <span className="text-[11px] text-gray-500">
                      {doc.docType || "Тип не определён"}
                    </span>
                    {doc.classificationLevel && (
                      <ClassificationBadge
                        level={doc.classificationLevel as any}
                        confidence={doc.classificationConfidence ?? undefined}
                        showConfidence={false}
                      />
                    )}
                  </div>
                </div>
              </td>

              {/* Остальные столбцы: проверки/риски */}
              {checks.map((check) => {
                const cell = getCell(doc.id, check.id);

                if (!cell) {
                  return (
                    <td
                      key={check.id}
                      className="px-1 py-2 text-center border-t border-l border-gray-100 text-gray-300"
                    >
                      —
                    </td>
                  );
                }

                const hasRisk = cell.result === "fail";
                const isUnclear = cell.result === "unclear";

                const handleEye = (e: React.MouseEvent) => {
                  e.stopPropagation();
                  onEyeClick?.(cell);
                };

                return (
                  <td
                    key={check.id}
                    className="px-1 py-1 text-center border-t border-l border-gray-100 align-middle"
                  >
                    <div className="flex flex-col items-center gap-1">
                      <button
                        type="button"
                        className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] ${
                          hasRisk
                            ? "bg-red-100 text-red-700"
                            : isUnclear
                            ? "bg-yellow-100 text-yellow-800"
                            : "bg-green-100 text-green-700"
                        }`}
                        title={
                          cell.value_text ||
                          (hasRisk
                            ? "Обнаружен риск"
                            : isUnclear
                            ? "Неоднозначный результат"
                            : "Риск не обнаружен")
                        }
                        onClick={handleEye}
                      >
                        {hasRisk ? "!" : isUnclear ? "?" : "✓"}
                      </button>
                      {cell.severity && (
                        <SeverityBadge severity={cell.severity as any} />
                      )}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

// -------------------------------------------------------------
// Старый список (AG Grid) — для режима mode="list"
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

export default DDGrid;

// -------------------------------------------------------------
// Cell renderers для списка
// -------------------------------------------------------------

interface BaseCellParams extends ICellRendererParams<CheckResult, any> {
  context: GridContext;
  data: CheckResult;
}

// Severity + ⚡ + 👁
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

// Документ — кликабелен
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

// Проверка — кликабельна
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

// Conditional / Trigger (флаг)
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

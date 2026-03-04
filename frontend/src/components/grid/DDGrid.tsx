// =============================================================
// src/components/grid/DDGrid.tsx
// DD Grid на базе AG Grid для юристов:
// - приоритет по риску и summary;
// - QC-статус, confidence, conditional-иконка;
// - клики по документу/проверке;
// - выбор строк для bulk QC;
// - классификация документа и триггер условной проверки.
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

// AG Grid стили (можно вынести в глобальный импорт один раз)
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
}

interface GridContext {
  onEyeClick?: (result: CheckResult) => void;
  onDocumentClick?: (result: CheckResult) => void;
  onCheckClick?: (result: CheckResult) => void;
  onQcChange?: (result: CheckResult, newStatus: "approved" | "rejected") => void;
}

export const DDGrid: React.FC<DDGridProps> = ({
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
      // 0) Колонка выбора (чекбоксы)
      {
        headerName: "",
        checkboxSelection: true,
        headerCheckboxSelection: true,
        width: 40,
        pinned: "left",
      },

      // 1) Риск / Severity + Eye
      {
        headerName: "Risk",
        field: "severity",
        width: 170,
        pinned: "left",
        cellRenderer: SeverityCellRenderer,
      },

      // 2) Краткое описание / summary
      {
        headerName: "Summary",
        field: "value_text",
        flex: 2,
        minWidth: 260,
        valueGetter: (params: ValueGetterParams<CheckResult>) =>
          params.data?.value_text || "",
      },

      // 3) Проверка
      {
        headerName: "Check",
        field: "check_name",
        flex: 1.8,
        minWidth: 220,
        cellRenderer: CheckNameCellRenderer,
      },

      // 4) Документ
      {
        headerName: "Document",
        field: "document_name",
        flex: 2,
        minWidth: 220,
        cellRenderer: DocumentCellRenderer,
      },

      // 5) Тип документа
      {
        headerName: "Doc Type",
        field: "doc_type",
        flex: 1,
        minWidth: 120,
      },

      // 6) Классификация документа
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
          return (
            <ClassificationBadge
              level={level}
              confidence={conf}
            />
          );
        },
      },

      // 7) Result (pass/fail/unclear)
      {
        headerName: "Result",
        field: "result",
        flex: 0.8,
        minWidth: 110,
      },

      // 8) Confidence (0–1)
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

      // 9) QC статус и быстрый QC (отдельный компонент)
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

      // 10) Флаги качества
      {
        headerName: "Flags",
        field: "quality_flags",
        width: 90,
        cellRenderer: (params: ICellRendererParams<CheckResult>) => (
          <QualityFlagRenderer result={params.data as CheckResult} />
        ),
      },

      // 11) Conditional / Trigger (флаг)
      {
        headerName: "Cond.",
        field: "conditional_check_triggered",
        width: 90,
        cellRenderer: ConditionalCellRenderer,
      },

      // 12) Trigger name (чип)
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

      // 13) Detector
      {
        headerName: "Detector",
        field: "detector_used",
        flex: 0.8,
        minWidth: 110,
      },

      // 14) Created at (можно скрыть по умолчанию)
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
        rowSelection="multiple"
        rowMultiSelectWithClick={true}
        suppressCellFocus={true}
        onSelectionChanged={handleSelectionChanged}
        getRowId={(params) => params.data.id}
      />
    </div>
  );
};

export default DDGrid;

// -------------------------------------------------------------
// Cell renderers
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

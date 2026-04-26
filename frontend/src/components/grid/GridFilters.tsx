// =============================================================
// src/components/grid/GridFilters.tsx
// =============================================================

import React from "react";

export type QuickFilter =
  | "all"
  | "critical"
  | "high"
  | "unclear"
  | "no_qc"
  | "important"
  | "conditional"
  | "low_confidence";

interface GridFiltersProps {
  searchText: string;
  onSearchChange: (text: string) => void;
  activeFilter: QuickFilter;
  onFilterChange: (filter: QuickFilter) => void;
  totalCount: number;
  filteredCount: number;

  availableDocTypes: string[];
  selectedDocType: string | null;
  onDocTypeChange: (value: string | null) => void;

  hasStructuredDataOnly: boolean;
  onHasStructuredDataChange: (value: boolean) => void;

  /**
   * Фильтр "только multi-document файлы".
   * Скрыт если hasCompositionData=false (нет данных — нет фильтра).
   */
  onlyMultiDocument: boolean;
  onOnlyMultiDocumentChange: (value: boolean) => void;
  hasCompositionData?: boolean;
  
  criticalOnly?: boolean;
  onCriticalOnlyChange?: (value: boolean) => void;
}

const QUICK_FILTERS: { key: QuickFilter; label: string }[] = [
  { key: "all", label: "Все" },
  { key: "critical", label: "Критические" },
  { key: "high", label: "Высокие" },
  { key: "unclear", label: "Неясные" },
  { key: "no_qc", label: "Без QC" },
  { key: "important", label: "Важные без QC" },
  { key: "conditional", label: "Conditional" },
  { key: "low_confidence", label: "Low confidence" },
];

const GridFilters: React.FC<GridFiltersProps> = ({
  searchText,
  onSearchChange,
  activeFilter,
  onFilterChange,
  totalCount,
  filteredCount,
  availableDocTypes,
  selectedDocType,
  onDocTypeChange,
  hasStructuredDataOnly,
  onHasStructuredDataChange,
  onlyMultiDocument,
  onOnlyMultiDocumentChange,
  hasCompositionData = false,
  criticalOnly,
  onCriticalOnlyChange,
}) => {
  return (
    <div className="flex flex-wrap gap-3 items-center justify-between">
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={searchText}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Поиск по документу или проверке…"
          className="text-xs border rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-blue-400"
        />
        <span className="text-[11px] text-gray-400">
          Всего: {totalCount}, после фильтра: {filteredCount}
        </span>
      </div>

      <div className="flex items-center gap-3 text-xs">
        <div className="flex items-center gap-1">
          <span className="text-gray-500">Тип документа:</span>
          <select
            className="border rounded px-2 py-1 text-xs"
            value={selectedDocType ?? ""}
            onChange={(e) => onDocTypeChange(e.target.value === "" ? null : e.target.value)}
          >
            <option value="">Все</option>
            {availableDocTypes.map((dt) => (
              <option key={dt} value={dt}>{dt}</option>
            ))}
          </select>
        </div>

        <label className="inline-flex items-center gap-1 cursor-pointer">
          <input
            type="checkbox"
            className="h-3 w-3"
            checked={hasStructuredDataOnly}
            onChange={(e) => onHasStructuredDataChange(e.target.checked)}
          />
          <span className="text-gray-500">Только со структурированными данными</span>
        </label>

        {hasCompositionData && (
          <label className="inline-flex items-center gap-1 cursor-pointer">
            <input
              type="checkbox"
              className="h-3 w-3"
              checked={onlyMultiDocument}
              onChange={(e) => onOnlyMultiDocumentChange(e.target.checked)}
            />
            <span className="text-gray-500">Только multi-document</span>
          </label>
        )}

        {criticalOnly !== undefined && onCriticalOnlyChange && (
          <label className="inline-flex items-center gap-1 cursor-pointer">
            <input
              type="checkbox"
              className="h-3 w-3"
              checked={criticalOnly}
              onChange={(e) => onCriticalOnlyChange(e.target.checked)}
            />
            <span className="text-red-600 font-medium">Только Critical</span>
          </label>
        )}

      </div>

      <div className="flex flex-wrap gap-1.5 text-xs">
        {QUICK_FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            onClick={() => onFilterChange(f.key)}
            className={
              activeFilter === f.key
                ? "px-2 py-1 rounded-full bg-blue-600 text-white"
                : "px-2 py-1 rounded-full bg-gray-100 text-gray-600 hover:bg-gray-200"
            }
          >
            {f.label}
          </button>
        ))}
      </div>
    </div>
  );
};

export default GridFilters;



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

function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

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
    <div className="flex flex-wrap items-start justify-between gap-3 rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-3 py-2.5">
      {/* Левая часть: поиск + счётчики */}
      <div className="flex min-w-[220px] flex-1 flex-col gap-1">
        <div className="relative">
          <input
            type="text"
            value={searchText}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Поиск по документу или проверке…"
            className="input-base !h-7 !py-1 text-xs"
          />
        </div>
        <span className="text-[11px] text-[var(--text-muted)]">
          Всего: {totalCount}, после фильтра: {filteredCount}
        </span>
      </div>

      {/* Правая часть: doc type + чекбоксы */}
      <div className="flex flex-wrap items-center justify-end gap-3 text-xs">
        <div className="flex items-center gap-1">
          <span className="text-[var(--text-muted)]">Тип документа:</span>
          <select
            className="input-base h-7 px-2 py-1 text-xs"
            value={selectedDocType ?? ""}
            onChange={(e) =>
              onDocTypeChange(e.target.value === "" ? null : e.target.value)
            }
          >
            <option value="">Все</option>
            {availableDocTypes.map((dt) => (
              <option key={dt} value={dt}>
                {dt}
              </option>
            ))}
          </select>
        </div>

        <label className="inline-flex items-center gap-1 cursor-pointer">
          <input
            type="checkbox"
            className="h-3 w-3 rounded border-[var(--border-subtle)] text-[var(--accent-primary)]"
            checked={hasStructuredDataOnly}
            onChange={(e) => onHasStructuredDataChange(e.target.checked)}
          />
          <span className="text-[var(--text-muted)]">
            Только со структурированными данными
          </span>
        </label>

        {hasCompositionData && (
          <label className="inline-flex items-center gap-1 cursor-pointer">
            <input
              type="checkbox"
              className="h-3 w-3 rounded border-[var(--border-subtle)] text-[var(--accent-primary)]"
              checked={onlyMultiDocument}
              onChange={(e) => onOnlyMultiDocumentChange(e.target.checked)}
            />
            <span className="text-[var(--text-muted)]">
              Только multi-document
            </span>
          </label>
        )}

        {criticalOnly !== undefined && onCriticalOnlyChange && (
          <label className="inline-flex items-center gap-1 cursor-pointer">
            <input
              type="checkbox"
              className="h-3 w-3 rounded border-[var(--border-subtle)] text-[var(--accent-primary)]"
              checked={criticalOnly}
              onChange={(e) => onCriticalOnlyChange(e.target.checked)}
            />
            <span className="font-medium text-[var(--color-error)]">
              Только Critical
            </span>
          </label>
        )}
      </div>

      {/* Быстрые фильтры */}
      <div className="flex w-full flex-wrap gap-1.5 pt-1 text-xs">
        {QUICK_FILTERS.map((f) => {
          const isActive = activeFilter === f.key;
          return (
            <button
              key={f.key}
              type="button"
              onClick={() => onFilterChange(f.key)}
              className={cn(
                "inline-flex items-center rounded-full border px-2 py-1 transition-colors",
                isActive
                  ? "border-[var(--accent-primary)] bg-[var(--accent-primary)] text-[var(--text-on-accent)]"
                  : "border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--text-secondary)] hover:bg-[var(--bg-elevated-soft)]",
              )}
            >
              {f.label}
            </button>
          );
        })}
      </div>
    </div>
  );
};

export default GridFilters;





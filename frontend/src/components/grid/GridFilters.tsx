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
}) => {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] px-4 py-4">
      <div className="relative">
        <input
          type="text"
          value={searchText}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Поиск по документу или проверке…"
          className="input-base min-h-10 text-sm"
        />
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {QUICK_FILTERS.map((f) => {
          const isActive = activeFilter === f.key;

          return (
            <button
              key={f.key}
              type="button"
              onClick={() => onFilterChange(f.key)}
              className={cn(
                "inline-flex items-center rounded-full border px-3 py-1.5 text-[12px] font-medium transition-colors",
                isActive
                  ? "border-[var(--accent-primary)] bg-[var(--accent-primary)] text-[var(--text-inverse)] shadow-sm"
                  : "border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--text-secondary)] hover:bg-[var(--bg-card-hover)]",
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



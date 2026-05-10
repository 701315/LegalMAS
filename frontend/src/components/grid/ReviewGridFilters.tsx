// =============================================================
// src/components/grid/ReviewGridFilters.tsx
// Review-native filters for DD Matrix / legal review workspace.
// Чистый presentational component без business logic.
// =============================================================

import React from "react";
import type {
  ReviewFilterState,
  ReviewQuickFilter,
} from "../../pages/tabs/grid/reviewGrid.types";

interface ReviewGridFiltersProps {
  filterState: ReviewFilterState;
  onFilterStateChange: (next: ReviewFilterState) => void;
  availableDocTypes: string[];
  availableOrigins: string[];
}

const QUICK_FILTERS: Array<{ key: ReviewQuickFilter; label: string }> = [
  { key: "all", label: "Все" },
  { key: "critical", label: "Критические" },
  { key: "high", label: "Высокие" },
  { key: "unclear", label: "Неясные" },
  { key: "no_qc", label: "Без QC" },
  { key: "important", label: "Важные без QC" },
  { key: "conditional", label: "Conditional" },
  { key: "low_confidence", label: "Low confidence" },
];

const ORIGIN_LABELS: Record<string, string> = {
  GLOBAL_PLAYBOOK: "Глобальный плейбук",
  DOCUMENT_TYPE: "По типу документа",
  CONDITIONAL: "Условные проверки",
};

function getOriginLabel(origin: string): string {
  return ORIGIN_LABELS[origin] ?? origin;
}

function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

function toggleArrayValue(values: string[], value: string): string[] {
  return values.includes(value)
    ? values.filter((item) => item !== value)
    : [...values, value];
}

const ReviewGridFilters: React.FC<ReviewGridFiltersProps> = ({
  filterState,
  onFilterStateChange,
  availableDocTypes,
  availableOrigins,
}) => {
  const setPartialState = (patch: Partial<ReviewFilterState>) => {
    onFilterStateChange({
      ...filterState,
      ...patch,
    });
  };

  const hasAdvancedFilters =
    filterState.multiDocumentOnly ||
    filterState.criticalOnly ||
    filterState.selectedDocTypes.length > 0 ||
    filterState.selectedOrigins.length > 0;

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] px-4 py-4">
      <div className="flex flex-col gap-4">
        <div>
          <input
            type="text"
            value={filterState.searchText}
            onChange={(e) => setPartialState({ searchText: e.target.value })}
            placeholder="Поиск по документу, сегменту, проверке или evidence…"
            className="input-base min-h-10 text-sm"
          />
        </div>

        <div className="flex flex-wrap gap-2">
          {QUICK_FILTERS.map((item) => {
            const isActive = filterState.quickFilter === item.key;

            return (
              <button
                key={item.key}
                type="button"
                onClick={() => setPartialState({ quickFilter: item.key })}
                className={cn(
                  "inline-flex items-center rounded-full border px-3 py-1.5 text-[12px] font-medium transition-colors",
                  isActive
                    ? "border-[var(--accent-primary)] bg-[var(--accent-primary)] text-[var(--text-inverse)] shadow-sm"
                    : "border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--text-secondary)] hover:bg-[var(--bg-card-hover)]",
                )}
              >
                {item.label}
              </button>
            );
          })}
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() =>
              setPartialState({
                multiDocumentOnly: !filterState.multiDocumentOnly,
              })
            }
            className={cn(
              "inline-flex items-center rounded-full border px-3 py-1.5 text-[12px] font-medium transition-colors",
              filterState.multiDocumentOnly
                ? "border-[var(--accent-primary)] bg-[var(--accent-primary)] text-[var(--text-inverse)] shadow-sm"
                : "border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--text-secondary)] hover:bg-[var(--bg-card-hover)]",
            )}
          >
            Только multi-document
          </button>

          <button
            type="button"
            onClick={() =>
              setPartialState({
                criticalOnly: !filterState.criticalOnly,
              })
            }
            className={cn(
              "inline-flex items-center rounded-full border px-3 py-1.5 text-[12px] font-medium transition-colors",
              filterState.criticalOnly
                ? "border-[var(--accent-primary)] bg-[var(--accent-primary)] text-[var(--text-inverse)] shadow-sm"
                : "border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--text-secondary)] hover:bg-[var(--bg-card-hover)]",
            )}
          >
            Только critical
          </button>

          {hasAdvancedFilters && (
            <button
              type="button"
              onClick={() =>
                onFilterStateChange({
                  searchText: filterState.searchText,
                  quickFilter: filterState.quickFilter,
                  multiDocumentOnly: false,
                  criticalOnly: false,
                  selectedDocTypes: [],
                  selectedOrigins: [],
                })
              }
              className="inline-flex items-center rounded-full border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-1.5 text-[12px] font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-card-hover)]"
            >
              Сбросить доп. фильтры
            </button>
          )}
        </div>

        {availableDocTypes.length > 0 && (
          <div className="flex flex-col gap-2">
            <div className="text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--text-muted)]">
              Тип документа
            </div>
            <div className="flex flex-wrap gap-2">
              {availableDocTypes.map((docType) => {
                const isActive = filterState.selectedDocTypes.includes(docType);

                return (
                  <button
                    key={docType}
                    type="button"
                    onClick={() =>
                      setPartialState({
                        selectedDocTypes: toggleArrayValue(
                          filterState.selectedDocTypes,
                          docType,
                        ),
                      })
                    }
                    className={cn(
                      "inline-flex items-center rounded-full border px-3 py-1.5 text-[12px] transition-colors",
                      isActive
                        ? "border-[var(--accent-primary)] bg-[var(--bg-elevated)] text-[var(--accent-primary)]"
                        : "border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--text-secondary)] hover:bg-[var(--bg-card-hover)]",
                    )}
                  >
                    {docType}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {availableOrigins.length > 0 && (
          <div className="flex flex-col gap-2">
            <div className="text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--text-muted)]">
              Область проверок
            </div>
            <div className="flex flex-wrap gap-2">
              {availableOrigins.map((origin) => {
                const isActive = filterState.selectedOrigins.includes(origin);

                return (
                  <button
                    key={origin}
                    type="button"
                    onClick={() =>
                      setPartialState({
                        selectedOrigins: toggleArrayValue(
                          filterState.selectedOrigins,
                          origin,
                        ),
                      })
                    }
                    className={cn(
                      "inline-flex items-center rounded-full border px-3 py-1.5 text-[12px] transition-colors",
                      isActive
                        ? "border-[var(--accent-primary)] bg-[var(--bg-elevated)] text-[var(--accent-primary)]"
                        : "border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--text-secondary)] hover:bg-[var(--bg-card-hover)]",
                    )}
                  >
                    {getOriginLabel(origin)}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ReviewGridFilters;






// =============================================================
// src/components/requests/shared/RequestStructuredValuesList.tsx
// Shared UI компонент для отображения извлечённых значений (structured values).
// =============================================================

import React from "react";
import type { StructuredValueView } from "../../../viewAdapters/requestPresentation";

interface RequestStructuredValuesListProps {
  values: StructuredValueView[];
  /**
   * Максимальная высота списка в пикселях (для overflow-y-auto).
   */
  maxHeight?: string;
}

function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

/**
 * Отображает список извлечённых значений в виде таблицы ключ-значение.
 * Поддерживает форматы: money, date, entity_name, text.
 */
export const RequestStructuredValuesList: React.FC<
  RequestStructuredValuesListProps
> = ({ values, maxHeight = "10rem" }) => {
  if (values.length === 0) {
    return (
      <div className="py-2 text-center text-xs text-[var(--text-faint)]">
        Извлечённые данные отсутствуют
      </div>
    );
  }

  return (
    <div
      className="overflow-y-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] p-2"
      style={{ maxHeight }}
    >
      <div className="space-y-1">
        {values.map((sv, index) => (
          <div
            key={index}
            className={cn(
              "flex items-start justify-between gap-3 rounded-lg border border-transparent px-2 py-1.5",
              "bg-[var(--bg-card)]/50",
            )}
          >
            {/* Ключ (название поля) */}
            <span className="min-w-0 shrink text-[var(--text-muted)]">
              <span className="capitalize">{sv.key.replace(/_/g, " ")}</span>
              {sv.format && (
                <span className="ml-1 normal-case text-[var(--text-faint)]">
                  ({sv.format})
                </span>
              )}
            </span>

            {/* Значение */}
            <span className="max-w-[60%] break-words text-right text-[var(--text-primary)] font-medium">
              {sv.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default RequestStructuredValuesList;



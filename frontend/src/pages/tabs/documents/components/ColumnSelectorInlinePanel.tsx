// =============================================================
// src/pages/tabs/documents/components/ColumnSelectorInlinePanel.tsx
// =============================================================

import React from "react";
import type { DocumentColumnId } from "../../../../types";
import { ALL_DOCUMENT_COLUMNS } from "../../../../types";
import Button from "../../../../components/ui/Button";

interface ColumnSelectorInlinePanelProps {
  tempSelectedIds: DocumentColumnId[];
  hasChanges: boolean;
  onToggle: (id: DocumentColumnId) => void;
  onApply: () => void;
  onReset: () => void;
  onCancel: () => void;
}

const ColumnSelectorInlinePanel: React.FC<
  ColumnSelectorInlinePanelProps
> = ({
  tempSelectedIds,
  hasChanges,
  onToggle,
  onApply,
  onReset,
  onCancel,
}) => (
  <div className="border-b border-[var(--border-subtle)] bg-[var(--bg-card)] px-5 py-3">
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated-soft)]">
      <div className="border-b border-[var(--border-subtle)] px-4 py-3">
        <p className="text-sm font-semibold text-[var(--text-primary)]">
          Отображаемые колонки
        </p>
        <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
          Нажмите на поле, чтобы показать или скрыть его в таблице
        </p>
      </div>

      <div className="px-4 py-4">
        <div className="flex flex-wrap gap-2">
          {ALL_DOCUMENT_COLUMNS.map((col) => {
            const isSelected = tempSelectedIds.includes(col.id);

            return (
              <Button
                key={col.id}
                type="button"
                size="sm"
                variant={isSelected ? "outline" : "secondary"}
                onClick={() => onToggle(col.id)}
                aria-pressed={isSelected}
                title={col.description}
                className={
                  isSelected
                    ? "border-[var(--accent-primary)] bg-[var(--accent-muted)] text-[var(--text-primary)] shadow-sm hover:bg-[var(--accent-muted)]"
                    : ""
                }
              >
                {col.label}
              </Button>
            );
          })}
        </div>
      </div>

      <div className="flex items-center justify-between gap-2 border-t border-[var(--border-subtle)] px-4 py-3">
        <Button size="sm" variant="ghost" onClick={onReset}>
          По умолчанию
        </Button>

        <div className="flex gap-2">
          <Button size="sm" variant="secondary" onClick={onCancel}>
            Отмена
          </Button>

          <Button
            size="sm"
            variant="secondary"
            onClick={onApply}
            disabled={!hasChanges}
            title={
              hasChanges
                ? "Применить изменения отображаемых колонок"
                : "Сначала измените набор отображаемых колонок"
            }
            className={
              hasChanges
                ? ""
                : "disabled:opacity-100 disabled:border-[var(--border-subtle)] disabled:bg-[var(--bg-elevated-soft)] disabled:text-[var(--text-muted)] disabled:shadow-none disabled:ring-0"
            }
          >
            Применить
          </Button>
        </div>
      </div>
    </div>
  </div>
);

export default ColumnSelectorInlinePanel;



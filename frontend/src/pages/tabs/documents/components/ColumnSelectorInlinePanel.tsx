// =============================================================
// src/pages/tabs/documents/components/ColumnSelectorInlinePanel.tsx
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
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
}) => {
  const { t } = useTranslation("documents");

  return (
    // Внешний wrapper — только визуальные отступы. Не участвует в скролле.
    <div className="border-b border-[var(--border-subtle)] bg-[var(--bg-card)] px-5 py-3">
      {/* Основной контейнер панели:
          - flex flex-col — вертикальный стек header / body / footer;
          - min-h-0 — разрешает внутреннему flex-child со скроллом
            корректно сжиматься;
          - max-height ограничивает высоту панели, чтобы она не
            "съедала" таблицу под ней. */}
      <div className="flex flex-col rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] lg:overflow-hidden lg:[max-height:min(60vh,480px)]">
        {/* Header — на десктопе фиксирован сверху (shrink-0), не скроллится. */}
        <div className="border-b border-[var(--border-subtle)] px-4 py-3 lg:shrink-0">
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            {t("documentsTab.columnSelector.title")}
          </p>
          <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
            {t("documentsTab.columnSelector.subtitle")}
          </p>
        </div>

        {/* Body — на десктопе единственная скроллируемая секция. */}
        <div className="px-4 py-4 lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:overscroll-contain">
          <div className="flex flex-wrap gap-2">
            {ALL_DOCUMENT_COLUMNS.map((col) => {
              const isSelected = tempSelectedIds.includes(col.id);

              const colLabel = col.labelKey
                ? t(col.labelKey, { defaultValue: col.label })
                : col.label;

              const colDescription = col.descriptionKey
                ? t(col.descriptionKey, { defaultValue: col.description })
                : col.description;

              return (
                <Button
                  key={col.id}
                  type="button"
                  size="sm"
                  variant={isSelected ? "outline" : "secondary"}
                  onClick={() => onToggle(col.id)}
                  aria-pressed={isSelected}
                  title={colDescription}
                  className={
                    isSelected
                      ? "border-[var(--accent-primary)] bg-[var(--accent-muted)] text-[var(--text-primary)] shadow-sm hover:bg-[var(--accent-muted)]"
                      : ""
                  }
                >
                  {colLabel}
                </Button>
              );
            })}
          </div>
        </div>

        {/* Footer — на десктопе фиксирован снизу (shrink-0). */}
        <div className="flex items-center justify-between gap-2 border-t border-[var(--border-subtle)] px-4 py-3 lg:shrink-0">
          <Button size="sm" variant="ghost" onClick={onReset}>
            {t("documentsTab.columnSelector.defaults")}
          </Button>

          <div className="flex gap-2">
            <Button size="sm" variant="secondary" onClick={onCancel}>
              {t("documentsTab.columnSelector.cancel")}
            </Button>

            <Button
              size="sm"
              variant="secondary"
              onClick={onApply}
              disabled={!hasChanges}
              title={
                hasChanges
                  ? t("documentsTab.columnSelector.applyTitle")
                  : t("documentsTab.columnSelector.applyTitleDisabled")
              }
              className={
                hasChanges
                  ? ""
                  : "disabled:opacity-100 disabled:border-[var(--border-subtle)] disabled:bg-[var(--bg-elevated-soft)] disabled:text-[var(--text-muted)] disabled:shadow-none disabled:ring-0"
              }
            >
              {t("documentsTab.columnSelector.apply")}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ColumnSelectorInlinePanel;



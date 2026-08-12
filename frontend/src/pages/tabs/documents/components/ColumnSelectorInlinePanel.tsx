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
  // Внешний wrapper — только визуальные отступы. Не участвует в скролле.
  <div className="border-b border-[var(--border-subtle)] bg-[var(--bg-card)] px-5 py-3">
    {/* Основной контейнер панели:
        - flex flex-col — вертикальный стек header / body / footer;
        - min-h-0 — разрешает внутреннему flex-child со скроллом
          корректно сжиматься;
        - max-height ограничивает высоту панели, чтобы она не
          "съедала" таблицу под ней. Используется min() от 60vh
          и абсолютного 480px — на большом экране 480px, на низком
          мобильном viewport 60vh (что меньше). */}
    <div
      className="flex flex-col rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] lg:overflow-hidden lg:[max-height:min(60vh,480px)]"
    >
      {/* Header — на десктопе фиксирован сверху (shrink-0), не скроллится.
          На мобильном занимает натуральную высоту в общем потоке. */}
      <div className="border-b border-[var(--border-subtle)] px-4 py-3 lg:shrink-0">
        <p className="text-sm font-semibold text-[var(--text-primary)]">
          Отображаемые колонки
        </p>
        <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
          Нажмите на поле, чтобы показать или скрыть его в таблице
        </p>
      </div>

      {/* Body — на десктопе единственная скроллируемая секция
          (min-h-0 + overflow-y-auto). На мобильном — натуральная высота,
          без внутреннего скролла: панель полностью раскрывается вниз,
          и скроллится вся страница. */}
      <div className="px-4 py-4 lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:overscroll-contain">
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

      {/* Footer — на десктопе фиксирован снизу (shrink-0), всегда виден.
          На мобильном — в потоке под списком колонок. */}
      <div className="flex items-center justify-between gap-2 border-t border-[var(--border-subtle)] px-4 py-3 lg:shrink-0">
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



// =============================================================
// src/pages/tabs/dd-grid-v1/DDGridV1ViewSettings.tsx
// Панель настроек отображения DD Grid V1.
//
// Содержит три независимых toggle:
// - Формат представления данных     (matrix / list)
// - Отображение результатов проверок (all / global_only / doc_type_only)
// - Группировка документов           (all_docs / by_type)
//
// Правила:
// - каждый toggle имеет свою подпись сверху;
// - "Группировка документов" скрывается когда format = list (Q23 = C);
// - все state читаются/пишутся через useDDGridV1UIStore.
// =============================================================

import React from "react";

import {
  useDDGridV1UIStore,
  type DDGridV1ChecksScope,
  type DDGridV1DocGrouping,
  type DDGridV1GridFormat,
} from "./ddGridV1.collapseStore";

// -------------------------------------------------------------
// Toggle option types
// -------------------------------------------------------------

interface ToggleOption<T extends string> {
  value: T;
  label: string;
  title: string;
}

const FORMAT_OPTIONS: readonly ToggleOption<DDGridV1GridFormat>[] = [
  {
    value: "matrix",
    label: "Матрица",
    title: "Табличное представление документов и проверок",
  },
  {
    value: "list",
    label: "Список",
    title: "Плоский список findings",
  },
] as const;

const CHECKS_SCOPE_OPTIONS: readonly ToggleOption<DDGridV1ChecksScope>[] = [
  {
    value: "all",
    label: "Все проверки",
    title: "Показывать global и doc-type проверки",
  },
  {
    value: "global_only",
    label: "Только глобальные",
    title: "Только global playbook проверки",
  },
  {
    value: "doc_type_only",
    label: "Только по типу документа",
    title: "Только проверки, специфичные для типа документа",
  },
] as const;

const DOC_GROUPING_OPTIONS: readonly ToggleOption<DDGridV1DocGrouping>[] = [
  {
    value: "all_docs",
    label: "Все документы",
    title: "Все документы в одной таблице",
  },
  {
    value: "by_type",
    label: "По типам документов",
    title: "Отдельная таблица на каждый тип документа",
  },
] as const;

// -------------------------------------------------------------
// Toggle button visual
// -------------------------------------------------------------

function getTabClassName<T extends string>(current: T, value: T): string {
  return current === value
    ? "rounded-lg bg-[var(--bg-card)] px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] shadow-sm"
    : "rounded-lg px-3 py-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)]";
}

interface ToggleGroupProps<T extends string> {
  label: string;
  ariaLabel: string;
  value: T;
  options: readonly ToggleOption<T>[];
  onChange: (value: T) => void;
}

function ToggleGroup<T extends string>({
  label,
  ariaLabel,
  value,
  options,
  onChange,
}: ToggleGroupProps<T>) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
        {label}
      </span>
      <div
        className="inline-flex items-center rounded-xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] p-1"
        role="tablist"
        aria-label={ariaLabel}
      >
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={value === option.value}
            title={option.title}
            onClick={() => onChange(option.value)}
            className={getTabClassName(value, option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

// -------------------------------------------------------------
// Main component
// -------------------------------------------------------------

export const DDGridV1ViewSettings: React.FC = () => {
  const format = useDDGridV1UIStore((state) => state.format);
  const setFormat = useDDGridV1UIStore((state) => state.setFormat);

  const checksScope = useDDGridV1UIStore((state) => state.checksScope);
  const setChecksScope = useDDGridV1UIStore((state) => state.setChecksScope);

  const docGrouping = useDDGridV1UIStore((state) => state.docGrouping);
  const setDocGrouping = useDDGridV1UIStore((state) => state.setDocGrouping);

  // Q23 = C: группировка скрывается когда format = list
  const showGrouping = format === "matrix";

  return (
    <div className="flex flex-wrap items-start gap-6">
      <ToggleGroup
        label="Формат представления данных"
        ariaLabel="Формат представления данных"
        value={format}
        options={FORMAT_OPTIONS}
        onChange={setFormat}
      />

      <ToggleGroup
        label="Отображение результатов проверок"
        ariaLabel="Отображение результатов проверок"
        value={checksScope}
        options={CHECKS_SCOPE_OPTIONS}
        onChange={setChecksScope}
      />

      {showGrouping ? (
        <ToggleGroup
          label="Группировка документов"
          ariaLabel="Группировка документов"
          value={docGrouping}
          options={DOC_GROUPING_OPTIONS}
          onChange={setDocGrouping}
        />
      ) : null}
    </div>
  );
};

export default DDGridV1ViewSettings;




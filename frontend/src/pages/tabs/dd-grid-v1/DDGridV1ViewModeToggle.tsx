// =============================================================
// src/pages/tabs/dd-grid-v1/DDGridV1ViewModeToggle.tsx
// Compact toggle для переключения между matrix и list.
// Использует format из useDDGridV1UIStore (matrix | list).
// =============================================================

import React from "react";

import {
  useDDGridV1UIStore,
  type DDGridV1GridFormat,
} from "./ddGridV1.collapseStore";

interface ViewModeOption {
  value: DDGridV1GridFormat;
  label: string;
  title: string;
}

const VIEW_MODE_OPTIONS: readonly ViewModeOption[] = [
  {
    value: "matrix",
    label: "Матрица",
    title: "Табличное представление: документы × проверки",
  },
  {
    value: "list",
    label: "Список",
    title: "Плоский список findings",
  },
] as const;

function getTabClassName(
  current: DDGridV1GridFormat,
  value: DDGridV1GridFormat,
): string {
  return current === value
    ? "rounded-lg bg-[var(--bg-card)] px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] shadow-sm"
    : "rounded-lg px-3 py-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)]";
}

export const DDGridV1ViewModeToggle: React.FC = () => {
  const format = useDDGridV1UIStore((state) => state.format);
  const setFormat = useDDGridV1UIStore((state) => state.setFormat);

  return (
    <div
      className="inline-flex items-center rounded-xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] p-1"
      role="tablist"
      aria-label="DD Grid V1 view mode"
    >
      {VIEW_MODE_OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          role="tab"
          aria-selected={format === option.value}
          title={option.title}
          onClick={() => setFormat(option.value)}
          className={getTabClassName(format, option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
};

export default DDGridV1ViewModeToggle;
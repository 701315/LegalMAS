// =============================================================
// src/pages/tabs/dd-grid-v1/DDGridV1ViewModeToggle.tsx
// Matrix-only toggle для режима представления DD Grid V1.
//
// Режимы:
// - by_doc_type   — отдельная таблица на каждый doc_type;
// - all_documents — одна сводная таблица со всеми check-ами;
// - global_only   — одна сводная таблица только с global checks.
//
// Источник состояния — zustand store useDDGridV1UIStore.
// =============================================================

import React from "react";

import {
  useDDGridV1UIStore,
  type DDGridV1ViewMode,
} from "./ddGridV1.collapseStore";

interface ViewModeOption {
  value: DDGridV1ViewMode;
  label: string;
  title: string;
}

const VIEW_MODE_OPTIONS: readonly ViewModeOption[] = [
  {
    value: "by_doc_type",
    label: "По типам",
    title: "Отдельная таблица для каждого типа документа",
  },
  {
    value: "all_documents",
    label: "Все документы",
    title: "Одна таблица со всеми документами и всеми доступными проверками",
  },
  {
    value: "global_only",
    label: "Только глобальные",
    title: "Одна таблица со всеми документами и только глобальными проверками",
  },
] as const;

function getTabClassName(
  current: DDGridV1ViewMode,
  value: DDGridV1ViewMode,
): string {
  return current === value
    ? "rounded-lg bg-[var(--bg-card)] px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] shadow-sm"
    : "rounded-lg px-3 py-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)]";
}

export const DDGridV1ViewModeToggle: React.FC = () => {
  const viewMode = useDDGridV1UIStore((state) => state.viewMode);
  const setViewMode = useDDGridV1UIStore((state) => state.setViewMode);

  return (
    <div
      className="inline-flex items-center rounded-xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] p-1"
      role="tablist"
      aria-label="DD Grid V1 matrix view mode"
    >
      {VIEW_MODE_OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          role="tab"
          aria-selected={viewMode === option.value}
          title={option.title}
          onClick={() => setViewMode(option.value)}
          className={getTabClassName(viewMode, option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
};

export default DDGridV1ViewModeToggle;



// =============================================================
// src/components/new-project/ReadinessRail.tsx
//
// Правая колонка страницы "Запуск нового проекта".
//
// Содержит:
//   1. Готовность к запуску — обязательные условия
//   2. Сводка проекта       — текущие значения параметров
// =============================================================

import React from "react";
import { Check, Circle } from "lucide-react";

import FlowSummary from "./FlowSummary";
import type { FlowSummaryData } from "./FlowSummary";

export interface ReadinessRailData {
  hasProject: boolean;
  hasDocuments: boolean;
  hasPlaybook: boolean;
  hasLanguage: boolean;
}

interface ReadinessRailProps {
  readiness: ReadinessRailData;
  summary: FlowSummaryData;
}

interface ReadinessItemProps {
  label: string;
  isDone: boolean;
}

const ReadinessItem: React.FC<ReadinessItemProps> = ({
  label,
  isDone,
}) => {
  return (
    <div className="flex items-center gap-2.5 py-2">
      <div
        className={[
          "flex h-4 w-4 shrink-0 items-center justify-center rounded-full",
          isDone
            ? "text-[var(--color-success-text)]"
            : "text-[var(--text-faint)]",
        ]
          .filter(Boolean)
          .join(" ")}
        aria-hidden="true"
      >
        {isDone ? (
          <Check className="h-3 w-3" strokeWidth={2.5} />
        ) : (
          <Circle className="h-2 w-2 fill-current" strokeWidth={0} />
        )}
      </div>

      <span
        className={[
          "text-[12px]",
          isDone
            ? "text-[var(--text-primary)]"
            : "text-[var(--text-secondary)]",
        ]
          .filter(Boolean)
          .join(" ")}
      >
        {label}
      </span>
    </div>
  );
};

const ReadinessRail: React.FC<ReadinessRailProps> = ({
  readiness,
  summary,
}) => {
  const allReady =
    readiness.hasProject &&
    readiness.hasDocuments &&
    readiness.hasPlaybook &&
    readiness.hasLanguage;

  return (
    <aside className="sticky top-4 flex flex-col gap-4">
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-4 shadow-sm">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Готовность к запуску
          </h3>

          {allReady ? (
            <span className="rounded-full border border-[var(--color-success-border)] bg-[var(--color-success-bg)] px-2 py-0.5 text-[10px] font-semibold text-[var(--color-success-text)]">
              Готов
            </span>
          ) : null}
        </div>

        <div className="divide-y divide-[var(--border-subtle)]">
          <ReadinessItem
            label="Проект создан"
            isDone={readiness.hasProject}
          />
          <ReadinessItem
            label="Документы загружены"
            isDone={readiness.hasDocuments}
          />
          <ReadinessItem
            label="Playbook выбран"
            isDone={readiness.hasPlaybook}
          />
          <ReadinessItem
            label="Основной язык выбран"
            isDone={readiness.hasLanguage}
          />
        </div>
      </section>

      <FlowSummary data={summary} />
    </aside>
  );
};

export default ReadinessRail;



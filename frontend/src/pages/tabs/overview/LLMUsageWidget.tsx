// =============================================================
// src/pages/tabs/overview/LLMUsageWidget.tsx
// Виджет потребления LLM-токенов по проекту.
// Встраивается в правую колонку ProjectDomainDetailsPanel.
// =============================================================

import React from "react";
import type { LLMUsageSummary, LLMStageUsage } from "../../../api/deals";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}k`;
  return String(n);
}

const STAGE_LABELS: Record<string, string> = {
  classification_l4: "Классификация L4",
  checks_detection_llm: "Проверки — детекция",
  checks_extraction_llm: "Проверки — извлечение",
  structure_semantic_enrichment: "Обогащение",
  heading_refiner: "Заголовки",
};

// ---------------------------------------------------------------------------
// StageRow
// ---------------------------------------------------------------------------

const StageRow: React.FC<{ stage: LLMStageUsage }> = ({ stage }) => {
  const label = STAGE_LABELS[stage.stage] ?? stage.stage;

  return (
    <div className="flex items-start justify-between gap-2 py-1.5">
      <div className="min-w-0 flex-1">
        <p className="truncate text-[11px] text-[var(--text-secondary)]">
          {label}
        </p>
        <p className="text-[10px] text-[var(--text-muted)]">
          {stage.calls} вызовов
          {stage.parse_failures > 0 && (
            <span className="ml-1 text-[var(--color-warning)]">
              · {stage.parse_failures} ошибок
            </span>
          )}
        </p>
      </div>
      <span className="shrink-0 text-[12px] font-semibold tabular-nums text-[var(--text-primary)]">
        {formatTokens(stage.total_tokens)}
      </span>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

export const LLMUsageWidgetSkeleton: React.FC = () => (
  <div className="animate-pulse space-y-2">
    <div className="h-3 w-20 rounded-lg bg-[var(--bg-elevated-soft)]" />
    <div className="h-7 w-28 rounded-lg bg-[var(--bg-elevated-soft)]" />
    <div className="space-y-1.5 pt-1">
      {[1, 2, 3].map((i) => (
        <div
          key={i}
          className="h-8 rounded-lg bg-[var(--bg-elevated-soft)]"
        />
      ))}
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

export const LLMUsageWidgetEmpty: React.FC = () => (
  <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-base)] px-3 py-4 text-center">
    <p className="text-[11px] text-[var(--text-muted)]">
      Токены ещё не использованы
    </p>
    <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
      Данные появятся после запуска анализа
    </p>
  </div>
);

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

interface LLMUsageWidgetProps {
  data: LLMUsageSummary | undefined;
  isLoading: boolean;
  isError: boolean;
}

export const LLMUsageWidget: React.FC<LLMUsageWidgetProps> = ({
  data,
  isLoading,
  isError,
}) => {
  if (isLoading) return <LLMUsageWidgetSkeleton />;

  if (isError || !data) {
    return (
      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-3">
        <p className="text-[11px] text-[var(--text-muted)]">
          Не удалось загрузить данные
        </p>
      </div>
    );
  }

  if (data.total_calls === 0) return <LLMUsageWidgetEmpty />;

  const model = data.by_stage[0]?.model;

  return (
    <div className="space-y-2">
      {/* Итого */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-3">
        <p className="text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">
          Итого токенов
        </p>
        <p className="mt-1 text-2xl font-bold tabular-nums text-[var(--text-primary)]">
          {formatTokens(data.total_tokens)}
        </p>
        <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
          {data.total_calls} LLM-вызовов
        </p>
        {model && (
          <p className="mt-1 truncate text-[10px] text-[var(--text-muted)]">
            Модель: {model}
          </p>
        )}
      </div>

      {/* По стадиям */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-2">
        <p className="mb-0.5 text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">
          По стадиям
        </p>
        <div className="divide-y divide-[var(--border-subtle)]">
          {data.by_stage.map((stage) => (
            <StageRow
              key={`${stage.stage}-${stage.model}`}
              stage={stage}
            />
          ))}
        </div>
      </div>
    </div>
  );
};

export default LLMUsageWidget;


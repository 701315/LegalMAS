// =============================================================
// src/pages/tabs/overview/DocumentsPipelinePanel.tsx
// Панель pipeline progress для вкладки Документы.
// =============================================================

import React from "react";
import { useRunProgress } from "../../../api/runs";
import { PipelineStepCard } from "./PipelineStepCard";

function formatElapsed(seconds: number | undefined | null): string {
  if (seconds == null) return "";
  if (seconds < 60) return `${seconds} сек`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h} ч ${m} мин`;
  return `${m} мин`;
}

function formatTime(iso: string | undefined | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatRelativeTime(iso: string | undefined | null): string {
  if (!iso) return "";
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 5) return "только что";
  if (diff < 60) return `${diff} сек назад`;
  if (diff < 3600) return `${Math.floor(diff / 60)} мин назад`;
  return `${Math.floor(diff / 3600)} ч назад`;
}

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

const SkeletonCard: React.FC = () => (
  <div className="animate-pulse rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3">
    <div className="flex items-center gap-3">
      <div className="h-5 w-5 rounded-full bg-[var(--bg-elevated-soft)]" />
      <div className="h-4 w-40 rounded-lg bg-[var(--bg-elevated-soft)]" />
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// DocumentsPipelinePanel
// ---------------------------------------------------------------------------

export const DocumentsPipelinePanel: React.FC<{
  runId: string | null;
}> = ({ runId }) => {
  const { data, isLoading, isError } = useRunProgress(runId);

  if (!runId) {
    return (
      <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-4 py-6 text-center">
        <p className="text-sm text-[var(--text-muted)]">Анализ ещё не запускался</p>
        <p className="mt-1 text-[11px] text-[var(--text-muted)]">
          Запустите анализ чтобы увидеть прогресс пайплайна
        </p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4">
        <p className="text-sm text-[var(--text-muted)]">
          Не удалось загрузить прогресс анализа
        </p>
      </div>
    );
  }

  const isTerminal =
    data.run_status === "completed" ||
    data.run_status === "completed_with_errors" ||
    data.run_status === "failed";

  const statusLabel = (() => {
    if (data.run_status === "completed") return "Анализ завершён";
    if (data.run_status === "completed_with_errors")
      return "Анализ завершён с ошибками";
    if (data.run_status === "failed") return "Анализ завершился с ошибкой";
    if (data.run_status === "running") return "Анализ выполняется";
    return "Ожидание";
  })();

  const statusColor = (() => {
    if (data.run_status === "completed") return "text-[var(--color-success)]";
    if (data.run_status === "completed_with_errors") return "text-[var(--color-warning)]";
    if (data.run_status === "failed") return "text-[var(--color-error)]";
    if (data.run_status === "running") return "text-[var(--accent-primary)]";
    return "text-[var(--text-muted)]";
  })();

  return (
    <div className="space-y-2">
      {/* Header */}
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 px-1">
        <div className="flex items-baseline gap-2">
          <span className={`text-sm font-semibold ${statusColor}`}>
            {statusLabel}
          </span>
          {data.started_at && (
            <span className="text-[11px] text-[var(--text-muted)]">
              · запущен {formatTime(data.started_at)}
            </span>
          )}
          {data.elapsed_seconds != null && (
            <span className="text-[11px] text-[var(--text-muted)]">
              · {isTerminal ? "за" : "идёт"}{" "}
              {formatElapsed(data.elapsed_seconds)}
            </span>
          )}
        </div>
        {data.last_activity_at && !isTerminal && (
          <span className="text-[10px] text-[var(--text-muted)]">
            обновлено {formatRelativeTime(data.last_activity_at)}
          </span>
        )}
      </div>

      {/* Stale warning */}
      {data.is_stale && (
        <div className="rounded-xl border border-[var(--color-warning)] bg-[color:color-mix(in_srgb,var(--color-warning)_8%,var(--bg-card))] px-3 py-2">
          <p className="text-[11px] font-medium text-[var(--color-warning)]">
            ⚠ Нет активности более {data.stale_threshold_minutes} минут
          </p>
          <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
            Возможно, worker завис или потерял соединение.
          </p>
        </div>
      )}

      {/* Steps */}
      {data.steps.map((step) => (
        <PipelineStepCard key={step.code} step={step} />
      ))}

      {/* Summary footer for terminal */}
      {isTerminal && (data.documents_failed > 0 || data.documents_quarantine > 0) && (
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-3 py-2">
          <p className="text-[11px] text-[var(--text-muted)]">
            {data.documents_failed > 0 && (
              <span className="text-[var(--color-error)]">
                Ошибок: {data.documents_failed}
              </span>
            )}
            {data.documents_failed > 0 && data.documents_quarantine > 0 && (
              <span> · </span>
            )}
            {data.documents_quarantine > 0 && (
              <span className="text-[var(--color-warning)]">
                Карантин: {data.documents_quarantine}
              </span>
            )}
          </p>
        </div>
      )}
    </div>
  );
};

export default DocumentsPipelinePanel;



// src/pages/tabs/overview/DocumentsPipelinePanel.tsx

import React from "react";
import { useTranslation } from "react-i18next";
import { useRunProgress } from "../../../api/runs";
import { PipelineStepCard } from "./PipelineStepCard";
import { usePipelineLayout } from "./pipelineLayoutContext";

type TranslateFn = (key: string, options?: Record<string, unknown>) => string;

function formatElapsed(seconds: number | undefined | null, tFn: TranslateFn): string {
  if (seconds == null) return "";
  if (seconds < 60) return tFn("overviewPanels.pipelinePanel.elapsedSec", { defaultValue: "{{count}} sec", count: seconds });
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) {
    return tFn("overviewPanels.pipelinePanel.elapsedHrMin", {
      defaultValue: "{{h}} h {{m}} min",
      h,
      m,
    });
  }
  return tFn("overviewPanels.pipelinePanel.elapsedMin", {
    defaultValue: "{{count}} min",
    count: m,
  });
}

function formatTime(iso: string | undefined | null, locale: string): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString(locale, {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatRelativeTime(iso: string | undefined | null, tFn: TranslateFn): string {
  if (!iso) return "";
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 5) return tFn("overviewPanels.pipelinePanel.justNow", { defaultValue: "just now" });
  if (diff < 60) return tFn("overviewPanels.pipelinePanel.secAgo", { defaultValue: "{{count}} sec ago", count: diff });
  if (diff < 3600) return tFn("overviewPanels.pipelinePanel.minAgo", { defaultValue: "{{count}} min ago", count: Math.floor(diff / 60) });
  return tFn("overviewPanels.pipelinePanel.hrAgo", { defaultValue: "{{count}} h ago", count: Math.floor(diff / 3600) });
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
  const { t, i18n } = useTranslation("projects");
  const { data, isLoading, isError } = useRunProgress(runId);

  if (!runId) {
    return (
      <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-4 py-6 text-center">
        <p className="text-sm text-[var(--text-muted)]">
          {t("overviewPanels.pipelinePanel.notLaunched")}
        </p>
        <p className="mt-1 text-[11px] text-[var(--text-muted)]">
          {t("overviewPanels.pipelinePanel.notLaunchedSub")}
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
          {t("overviewPanels.pipelinePanel.loadError")}
        </p>
      </div>
    );
  }

  const isTerminal =
    data.run_status === "completed" ||
    data.run_status === "completed_with_errors" ||
    data.run_status === "failed";

  const statusLabel = (() => {
    if (data.run_status === "completed") return t("overviewPanels.pipelinePanel.status.completed");
    if (data.run_status === "completed_with_errors")
      return t("overviewPanels.pipelinePanel.status.completedWithErrors");
    if (data.run_status === "failed") return t("overviewPanels.pipelinePanel.status.failed");
    if (data.run_status === "running") return t("overviewPanels.pipelinePanel.status.running");
    return t("overviewPanels.pipelinePanel.status.pending");
  })();

  const statusColor = (() => {
    if (data.run_status === "completed") return "text-[var(--color-success-text)]";
    if (data.run_status === "completed_with_errors") return "text-[var(--color-warning-text)]";
    if (data.run_status === "failed") return "text-[var(--color-error-text)]";
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
              {t("overviewPanels.pipelinePanel.startedAt", { time: formatTime(data.started_at, i18n.language) })}
            </span>
          )}
          {data.elapsed_seconds != null && (
            <span className="text-[11px] text-[var(--text-muted)]">
              {isTerminal
                ? t("overviewPanels.pipelinePanel.elapsedFinished", { time: formatElapsed(data.elapsed_seconds, t) })
                : t("overviewPanels.pipelinePanel.elapsedRunning", { time: formatElapsed(data.elapsed_seconds, t) })}
            </span>
          )}
        </div>
        {data.last_activity_at && !isTerminal && (
          <span className="text-[10px] text-[var(--text-muted)]">
            {t("overviewPanels.pipelinePanel.updatedRelative", {
              time: formatRelativeTime(data.last_activity_at, t)
            })}
          </span>
        )}
      </div>

      {/* Stale warning */}
      {data.is_stale && (
        <div className="rounded-xl border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-3 py-2">
          <p className="text-[11px] font-medium text-[var(--color-warning-text)]">
            {t("overviewPanels.pipelinePanel.staleWarning", { threshold: data.stale_threshold_minutes })}
          </p>
          <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
            {t("overviewPanels.pipelinePanel.staleSub")}
          </p>
        </div>
      )}

      {/* Steps */}
      <PipelineStepsList steps={data.steps} />

      {/* Summary footer for terminal */}
      {isTerminal && (data.documents_failed > 0 || data.documents_quarantine > 0) && (
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-3 py-2">
          <p className="text-[11px] text-[var(--text-muted)]">
            {data.documents_failed > 0 && (
              <span className="text-[var(--color-error-text)]">
                {t("overviewPanels.pipelinePanel.errors", { count: data.documents_failed })}
              </span>
            )}
            {data.documents_failed > 0 && data.documents_quarantine > 0 && (
              <span> · </span>
            )}
            {data.documents_quarantine > 0 && (
              <span className="text-[var(--color-warning-text)]">
                {t("overviewPanels.pipelinePanel.quarantine", { count: data.documents_quarantine })}
              </span>
            )}
          </p>
        </div>
      )}
    </div>
  );
};

/**
 * Список карточек этапов с явным position: relative на контейнере.
 *
 * Явный relative критичен: PipelineStepCard измеряет свою позицию
 * через offsetTop, который считается относительно ближайшего
 * offsetParent. Без relative-обёртки offsetParent мог бы стать
 * произвольным родителем выше по дереву, и координаты, сохранённые
 * в PipelineLayoutContext, стали бы бесполезны для collapsed rail.
 *
 * Также здесь регистрируется порядок этапов — collapsed rail
 * использует его как fallback (если store ещё пустой) и для
 * стабильной сортировки при рендере.
 */
const PipelineStepsList: React.FC<{
  steps: RunPipelineProgressStep[];
}> = ({ steps }) => {
  const { reportOrder } = usePipelineLayout();

  React.useEffect(() => {
    reportOrder(steps.map((s) => s.code));
  }, [reportOrder, steps]);

  return (
    <div className="relative space-y-2">
      {steps.map((step) => (
        <PipelineStepCard key={step.code} step={step} />
      ))}
    </div>
  );
};

// Локальный alias для типа, чтобы не тянуть внешний импорт в мелкий helper.
type RunPipelineProgressStep = React.ComponentProps<
  typeof PipelineStepCard
>["step"];

export default DocumentsPipelinePanel;



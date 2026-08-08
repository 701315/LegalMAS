// =============================================================
// src/pages/tabs/overview/PipelineStepCard.tsx
// Карточка одного этапа pipeline для DocumentsPipelinePanel.
// =============================================================

import React from "react";
import type { PipelineStep, PipelineStepStatus, PipelineSubProgress } from "../../../types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDuration(seconds: number | undefined | null): string {
  if (seconds == null) return "";
  if (seconds < 60) return `${seconds} сек`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return s > 0 ? `${m} мин ${s} сек` : `${m} мин`;
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
// Status icon
// ---------------------------------------------------------------------------

const StatusIcon: React.FC<{ status: PipelineStepStatus }> = ({ status }) => {
  if (status === "completed") {
    return (
      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--color-success)] text-[10px] text-white">
        ✓
      </span>
    );
  }

  if (status === "completed_with_errors") {
    return (
      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--color-warning)] text-[10px] text-white">
        ⚠
      </span>
    );
  }

  if (status === "failed") {
    return (
      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[var(--color-error)] text-[10px] text-white">
        ✕
      </span>
    );
  }

  if (status === "running") {
    return (
      <span className="flex h-5 w-5 shrink-0 items-center justify-center">
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-[var(--accent-primary)] border-t-transparent" />
      </span>
    );
  }

  // pending
  return (
    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 border-[var(--border)] bg-[var(--bg-elevated-soft)]" />
  );
};

// ---------------------------------------------------------------------------
// SubProgress block
// ---------------------------------------------------------------------------

const SubProgressBlock: React.FC<{
  sub: PipelineSubProgress;
}> = ({ sub }) => {
  const percent =
    sub.total > 0 ? Math.min(100, Math.round((sub.current / sub.total) * 100)) : 0;

  const kindLabel: Record<string, string> = {
    legal_units: "Semantic-блоки",
    segments: "Сегменты",
    checks: "Проверки",
    documents: "Документы",
  };

  return (
    <div className="mt-2 space-y-1.5 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-base)] px-3 py-2.5">
      {sub.current_document_name && (
        <p className="truncate text-[11px] text-[var(--text-secondary)]">
          <span className="font-medium text-[var(--text-primary)]">Документ:</span>{" "}
          {sub.current_document_name}
        </p>
      )}
      {sub.current_segment_title && (
        <p className="truncate text-[11px] text-[var(--text-secondary)]">
          <span className="font-medium text-[var(--text-primary)]">Сегмент:</span>{" "}
          {sub.current_segment_title}
        </p>
      )}
      {sub.current_unit_label && (
        <p className="truncate text-[11px] text-[var(--text-secondary)]">
          <span className="font-medium text-[var(--text-primary)]">Блок:</span>{" "}
          {sub.current_unit_label}
        </p>
      )}

      {sub.total > 0 && (
        <div>
          <div className="mb-1 flex items-center justify-between gap-2">
            <span className="text-[11px] text-[var(--text-muted)]">
              {kindLabel[sub.kind] ?? sub.kind}:{" "}
              <span className="font-medium tabular-nums text-[var(--text-primary)]">
                {sub.current} / {sub.total}
              </span>
            </span>
            <span className="text-[11px] tabular-nums text-[var(--text-muted)]">
              {percent}%
            </span>
          </div>
          <div className="h-1 w-full overflow-hidden rounded-full bg-[var(--bg-elevated-soft)]">
            <div
              className="h-1 rounded-full bg-[var(--accent-primary)] transition-all duration-500"
              style={{ width: `${percent}%` }}
            />
          </div>
        </div>
      )}

      {sub.updated_at && (
        <p className="text-[10px] text-[var(--text-muted)]">
          обновлено {formatRelativeTime(sub.updated_at)}
        </p>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// PipelineStepCard
// ---------------------------------------------------------------------------

export const PipelineStepCard: React.FC<{
  step: PipelineStep;
}> = ({ step }) => {
  const isRunning = step.status === "running";
  const isPending = step.status === "pending";
  const isTerminal =
    step.status === "completed" ||
    step.status === "completed_with_errors" ||
    step.status === "failed";

  const durationStr = formatDuration(step.duration_seconds);

  const borderClass = isRunning
    ? "border-[var(--accent-primary)] bg-[var(--accent-subtle)]"
    : isPending
      ? "border-[var(--border-subtle)] bg-[var(--bg-card)] opacity-60"
      : step.status === "failed"
        ? "border-[var(--color-error-border)] bg-[var(--color-error-bg)]"
        : step.status === "completed_with_errors"
          ? "border-[var(--color-warning-border)] bg-[var(--color-warning-bg)]"
          : "border-[var(--border)] bg-[var(--bg-card)]";

  return (
    <div
      className={`rounded-2xl border px-4 py-3 shadow-sm transition-colors ${borderClass}`}
    >
      {/* Header row */}
      <div className="flex items-start gap-3">
        <div className="mt-0.5">
          <StatusIcon status={step.status} />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0">
            <span
              className={`text-sm font-semibold ${
                isPending ? "text-[var(--text-muted)]" : "text-[var(--text-primary)]"
              }`}
            >
              {step.title}
            </span>
            {durationStr && isTerminal && (
              <span className="text-[11px] tabular-nums text-[var(--text-muted)]">
                {durationStr}
              </span>
            )}
            {isRunning && step.duration_seconds != null && (
              <span className="text-[11px] tabular-nums text-[var(--accent-primary)]">
                идёт {formatDuration(step.duration_seconds)}
              </span>
            )}
          </div>

          {/* Document progress */}
          {step.documents_total > 0 && !isPending && (
            <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
              {step.documents_completed} из {step.documents_total}{" "}
              {step.documents_failed > 0 && (
                <span className="text-[var(--color-error-text)]">
                  · ошибок: {step.documents_failed}
                </span>
              )}
            </p>
          )}

          {/* Message */}
          {step.message && (
            <p className="mt-0.5 text-[11px] italic text-[var(--text-muted)]">
              {step.message}
            </p>
          )}

          {/* Error message */}
          {step.error_message && step.status === "failed" && (
            <p className="mt-1 text-[11px] text-[var(--color-error-text)]">
              {step.error_message}
            </p>
          )}

          {/* Live sub_progress for running steps */}
          {isRunning && step.sub_progress && step.sub_progress.total > 0 && (
            <SubProgressBlock sub={step.sub_progress} />
          )}
        </div>
      </div>

      {/* Substeps — shown only for running or completed_with_errors */}
      {(isRunning || step.status === "completed_with_errors") &&
        step.substeps.length > 0 && (
          <div className="mt-2 ml-8 space-y-1">
            {step.substeps.map((substep) => (
              <div key={substep.code} className="flex items-center gap-2">
                <span className="text-[10px]">
                  {substep.status === "completed"
                    ? "✓"
                    : substep.status === "running"
                      ? "⋯"
                      : substep.status === "failed"
                        ? "✕"
                        : "○"}
                </span>
                <span
                  className={`text-[11px] ${
                    substep.status === "running"
                      ? "font-medium text-[var(--accent-primary)]"
                      : substep.status === "completed"
                        ? "text-[var(--text-muted)]"
                        : substep.status === "failed"
                          ? "text-[var(--color-error-text)]"
                          : "text-[var(--text-muted)]"
                  }`}
                >
                  {substep.title}
                  {substep.duration_seconds != null &&
                    substep.status === "completed" && (
                      <span className="ml-1 opacity-60">
                        {formatDuration(substep.duration_seconds)}
                      </span>
                    )}
                </span>
              </div>
            ))}
          </div>
        )}
    </div>
  );
};

export default PipelineStepCard;



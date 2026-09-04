// =============================================================
// src/pages/tabs/overview/PipelineStepCard.tsx
// Карточка одного этапа pipeline для DocumentsPipelinePanel.
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";
import type {
  PipelineStep,
  PipelineStepStatus,
  PipelineSubProgress,
} from "../../../types";
import { PipelineStepIcon } from "./pipelineStepIcons";
import { usePipelineStepCardRegistration } from "./pipelineLayoutContext";

type TranslateFn = (key: string, options?: Record<string, unknown>) => string;

function formatDuration(
  seconds: number | undefined | null,
  tFn: TranslateFn,
): string {
  if (seconds == null) return "";
  if (seconds < 60) {
    return tFn("overviewPanels.pipelineStep.durationSec", { count: seconds });
  }
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return s > 0
    ? tFn("overviewPanels.pipelineStep.durationMinSec", { m, s })
    : tFn("overviewPanels.pipelineStep.durationMin", { count: m });
}

function formatRelativeTime(
  iso: string | undefined | null,
  tFn: TranslateFn,
): string {
  if (!iso) return "";
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 5) return tFn("overviewPanels.pipelineStep.justNow");
  if (diff < 60) {
    return tFn("overviewPanels.pipelineStep.secAgo", { count: diff });
  }
  if (diff < 3600) {
    return tFn("overviewPanels.pipelineStep.minAgo", {
      count: Math.floor(diff / 60),
    });
  }
  return tFn("overviewPanels.pipelineStep.hrAgo", {
    count: Math.floor(diff / 3600),
  });
}

const StepBadge: React.FC<{
  code: string;
  status: PipelineStepStatus;
}> = ({ code, status }) => {
  const { t } = useTranslation("projects");
  const baseClass =
    "flex h-7 w-7 shrink-0 items-center justify-center rounded-full";

  if (status === "completed") {
    return (
      <span
        className={`${baseClass} bg-[var(--color-success)] text-white`}
        aria-label={t("overviewPanels.pipelineStep.aria.completed")}
      >
        <PipelineStepIcon
          code={code}
          className="h-3.5 w-3.5"
          strokeWidth={2.25}
        />
      </span>
    );
  }

  if (status === "completed_with_errors") {
    return (
      <span
        className={`${baseClass} bg-[var(--color-warning)] text-white`}
        aria-label={t("overviewPanels.pipelineStep.aria.completedWithErrors")}
      >
        <PipelineStepIcon
          code={code}
          className="h-3.5 w-3.5"
          strokeWidth={2.25}
        />
      </span>
    );
  }

  if (status === "failed") {
    return (
      <span
        className={`${baseClass} bg-[var(--color-error)] text-white`}
        aria-label={t("overviewPanels.pipelineStep.aria.failed")}
      >
        <PipelineStepIcon
          code={code}
          className="h-3.5 w-3.5"
          strokeWidth={2.25}
        />
      </span>
    );
  }

  if (status === "running") {
    return (
      <span
        className={`${baseClass} bg-[var(--accent-primary)] text-white`}
        aria-label={t("overviewPanels.pipelineStep.aria.running")}
      >
        <Loader2
          className="h-3.5 w-3.5 animate-spin"
          strokeWidth={2.5}
          aria-hidden
        />
      </span>
    );
  }

  return (
    <span
      className={`${baseClass} border border-[var(--border)] bg-[var(--bg-elevated-soft)] text-[var(--text-muted)]`}
      aria-label={t("overviewPanels.pipelineStep.aria.pending")}
    >
      <PipelineStepIcon code={code} className="h-3.5 w-3.5" strokeWidth={2} />
    </span>
  );
};

const SubProgressBlock: React.FC<{
  sub: PipelineSubProgress;
}> = ({ sub }) => {
  const { t } = useTranslation("projects");
  const percent =
    sub.total > 0
      ? Math.min(100, Math.round((sub.current / sub.total) * 100))
      : 0;

  const kindLabel =
    t(`overviewPanels.pipelineStep.kinds.${sub.kind}`, {
      defaultValue: sub.kind,
    }) as string;

  return (
    <div className="mt-2 space-y-1.5 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-base)] px-3 py-2.5">
      {sub.current_document_name && (
        <p className="truncate text-[11px] text-[var(--text-secondary)]">
          <span className="font-medium text-[var(--text-primary)]">
            {t("overviewPanels.pipelineStep.document")}
          </span>{" "}
          {sub.current_document_name}
        </p>
      )}
      {sub.current_segment_title && (
        <p className="truncate text-[11px] text-[var(--text-secondary)]">
          <span className="font-medium text-[var(--text-primary)]">
            {t("overviewPanels.pipelineStep.segment")}
          </span>{" "}
          {sub.current_segment_title}
        </p>
      )}
      {sub.current_unit_label && (
        <p className="truncate text-[11px] text-[var(--text-secondary)]">
          <span className="font-medium text-[var(--text-primary)]">
            {t("overviewPanels.pipelineStep.block")}
          </span>{" "}
          {sub.current_unit_label}
        </p>
      )}

      {sub.total > 0 && (
        <div>
          <div className="mb-1 flex items-center justify-between gap-2">
            <span className="text-[11px] text-[var(--text-muted)]">
              {kindLabel}:{" "}
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
          {t("overviewPanels.pipelineStep.updatedAt", {
            time: formatRelativeTime(sub.updated_at, t),
          })}
        </p>
      )}
    </div>
  );
};

export const PipelineStepCard: React.FC<{
  step: PipelineStep;
}> = ({ step }) => {
  const { t } = useTranslation("projects");
  const isRunning = step.status === "running";
  const isPending = step.status === "pending";
  const isTerminal =
    step.status === "completed" ||
    step.status === "completed_with_errors" ||
    step.status === "failed";

  const durationStr = formatDuration(step.duration_seconds, t);

  const stepTitle = t(`overviewPanels.pipelineStep.stepTitles.${step.code}`, {
    defaultValue: step.title,
  });

  const borderClass = isRunning
    ? "border-[var(--accent-primary)] bg-[var(--accent-subtle)]"
    : isPending
      ? "border-[var(--border-subtle)] bg-[var(--bg-card)] opacity-60"
      : step.status === "failed"
        ? "border-[var(--color-error-border)] bg-[var(--color-error-bg)]"
        : step.status === "completed_with_errors"
          ? "border-[var(--color-warning-border)] bg-[var(--color-warning-bg)]"
          : "border-[var(--border)] bg-[var(--bg-card)]";

  const cardRef = React.useRef<HTMLDivElement | null>(null);
  usePipelineStepCardRegistration(step.code, cardRef);

  return (
    <div
      ref={cardRef}
      className={`rounded-2xl border px-4 py-3 shadow-sm transition-colors ${borderClass}`}
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5">
          <StepBadge code={step.code} status={step.status} />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0">
            <span
              className={`text-sm font-semibold ${
                isPending
                  ? "text-[var(--text-muted)]"
                  : "text-[var(--text-primary)]"
              }`}
            >
              {stepTitle}
            </span>
            {durationStr && isTerminal && (
              <span className="text-[11px] tabular-nums text-[var(--text-muted)]">
                {durationStr}
              </span>
            )}
            {isRunning && step.duration_seconds != null && (
              <span className="text-[11px] tabular-nums text-[var(--accent-primary)]">
                {t("overviewPanels.pipelineStep.runningFor", {
                  duration: formatDuration(step.duration_seconds, t),
                })}
              </span>
            )}
          </div>

          {step.documents_total > 0 && !isPending && (
            <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
              {t("overviewPanels.pipelineStep.docsProgress", {
                completed: step.documents_completed,
                total: step.documents_total,
              })}{" "}
              {step.documents_failed > 0 && (
                <span className="text-[var(--color-error-text)]">
                  {t("overviewPanels.pipelineStep.docsErrors", {
                    count: step.documents_failed,
                  })}
                </span>
              )}
            </p>
          )}

          {step.message && (
            <p className="mt-0.5 text-[11px] italic text-[var(--text-muted)]">
              {step.message}
            </p>
          )}

          {step.error_message && step.status === "failed" && (
            <p className="mt-1 text-[11px] text-[var(--color-error-text)]">
              {step.error_message}
            </p>
          )}

          {isRunning && step.sub_progress && step.sub_progress.total > 0 && (
            <SubProgressBlock sub={step.sub_progress} />
          )}
        </div>
      </div>

      {(isRunning || step.status === "completed_with_errors") &&
        step.substeps.length > 0 && (
          <div className="mt-2 ml-8 space-y-1">
            {step.substeps.map((substep) => {
              const substepTitle = t(
                `overviewPanels.pipelineStep.substepTitles.${substep.code}`,
                { defaultValue: substep.title },
              );

              return (
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
                    {substepTitle}
                    {substep.duration_seconds != null &&
                      substep.status === "completed" && (
                        <span className="ml-1 opacity-60">
                          {formatDuration(substep.duration_seconds, t)}
                        </span>
                      )}
                  </span>
                </div>
              );
            })}
          </div>
        )}
    </div>
  );
};

export default PipelineStepCard;




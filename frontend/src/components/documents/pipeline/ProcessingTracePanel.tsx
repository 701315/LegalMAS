// frontend/src/components/documents/pipeline/ProcessingTracePanel.tsx

import React from "react";
import { useTranslation } from "react-i18next";
import { useProcessingTrace } from "../../../api/provenance";
import type { StageTraceDTO } from "../../../api/provenance";

interface Props {
  documentId: string;
}

function formatDuration(
  ms: number | null | undefined,
  tFn: (key: string, options?: Record<string, unknown>) => string,
): string {
  if (ms == null) return "—";
  if (ms < 1000) return tFn("trace.duration_ms", { ms });
  if (ms < 60_000) {
    return tFn("trace.duration_s", { seconds: (ms / 1000).toFixed(1) });
  }
  return tFn("trace.duration_m_s", {
    minutes: Math.floor(ms / 60_000),
    seconds: Math.round((ms % 60_000) / 1000),
  });
}

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    succeeded: "bg-[var(--color-success)]",
    failed: "bg-[var(--color-error)]",
    started: "bg-[var(--color-warning)]",
    cancelled: "bg-[var(--text-faint)]",
  };
  return (
    <span
      className={`mt-1.5 inline-block h-2 w-2 shrink-0 rounded-full ${
        colors[status] ?? "bg-[var(--border-strong)]"
      }`}
    />
  );
}

function StageRow({ stage }: { stage: StageTraceDTO }) {
  const { t, i18n } = useTranslation("pipeline");
  const [expanded, setExpanded] = React.useState(false);

  // Смена точек на подчёркивания для валидных JSON ключей
  const normTaskName = stage.task_name.replace(/\./g, "_");
  const fallbackLabel = stage.task_name.replace("workers.", "").replace("pii.", "");
  const label = t(`traceStages.${normTaskName}`, { defaultValue: fallbackLabel });

  const strategyLabel = stage.strategy
    ? t(`traceStrategies.${stage.strategy}`, { defaultValue: stage.strategy })
    : null;

  const warnings = (stage.warnings ?? []).filter(Boolean);
  const hasWarnings = warnings.length > 0;
  const hasTrace = stage.schema_version != null;

  const terminalOutcome = stage.output_summary?.terminal_outcome as
    | string
    | undefined;
  const enrichedCount = stage.output_summary?.segments_enriched as
    | number
    | undefined;

  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-start gap-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-3 text-left transition hover:bg-[var(--bg-elevated-soft)]"
      >
        <StatusDot status={stage.status} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-semibold text-[var(--text-primary)]">
              {label}
            </span>
            <span className="shrink-0 text-[10px] text-[var(--text-muted)]">
              {formatDuration(stage.duration_ms, t)}
            </span>
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
            {strategyLabel && (
              <span className="text-[10px] text-[var(--text-muted)]">
                {strategyLabel}
              </span>
            )}
            {terminalOutcome && (
              <span className="text-[10px] text-[var(--text-muted)]">
                {terminalOutcome}
                {enrichedCount != null
                  ? ` · ${t("trace.segmentsCount", { count: enrichedCount })}`
                  : ""}
              </span>
            )}
            {hasWarnings && (
              <span className="status-border-warning status-bg-warning rounded-full border px-1.5 py-0.5 text-[10px] status-text-warning">
                ⚠ {warnings.length}
              </span>
            )}
            {!hasTrace && (
              <span className="text-[10px] text-[var(--text-faint)]">
                {t("trace.legacy")}
              </span>
            )}
          </div>
        </div>
        <span className="shrink-0 text-[10px] text-[var(--accent-primary)]">
          {expanded ? "▲" : "▼"}
        </span>
      </button>

      {expanded && (
        <div className="ml-5 mt-1 space-y-2 rounded-b-xl border border-t-0 border-[var(--border-subtle)] px-3 py-3 text-[11px]">
          {hasWarnings && (
            <div className="status-border-warning status-bg-warning rounded-lg border px-2 py-2">
              <div className="font-medium status-text-warning">Warnings</div>
              <ul className="mt-1 list-inside list-disc text-[var(--color-warning-text)]">
                {warnings.map((w, i) => (
                  <li key={i}>{String(w)}</li>
                ))}
              </ul>
            </div>
          )}
          {stage.input_summary &&
            Object.keys(stage.input_summary).length > 0 && (
              <div>
                <div className="mb-1 font-medium text-[var(--text-muted)]">
                  Input
                </div>
                <pre className="overflow-auto rounded-lg bg-[var(--bg-elevated-soft)] p-2 text-[10px] text-[var(--text-secondary)]">
                  {JSON.stringify(stage.input_summary, null, 2)}
                </pre>
              </div>
            )}

          {stage.output_summary &&
            Object.keys(stage.output_summary).length > 0 && (
              <div>
                <div className="mb-1 font-medium text-[var(--text-muted)]">
                  Output
                </div>
                <pre className="overflow-auto rounded-lg bg-[var(--bg-elevated-soft)] p-2 text-[10px] text-[var(--text-secondary)]">
                  {JSON.stringify(stage.output_summary, null, 2)}
                </pre>
              </div>
            )}

          {stage.artifact_refs &&
            Object.keys(stage.artifact_refs).length > 0 && (
              <div>
                <div className="mb-1 font-medium text-[var(--text-muted)]">
                  Artifacts
                </div>
                {Object.entries(stage.artifact_refs).map(([k, v]) => (
                  <div key={k} className="flex gap-1">
                    <span className="text-[var(--text-muted)]">{k}:</span>
                    <span className="break-all text-[var(--accent-primary)]">
                      {String(v)}
                    </span>
                  </div>
                ))}
              </div>
            )}

          {stage.error_details && (
            <div>
              <div className="mb-1 font-medium status-text-error">Error</div>
              <pre className="status-bg-error status-text-error overflow-auto rounded-lg p-2 text-[10px]">
                {JSON.stringify(stage.error_details, null, 2)}
              </pre>
            </div>
          )}

          {(stage.started_at || stage.finished_at) && (
            <div className="text-[10px] text-[var(--text-faint)]">
              {stage.started_at && (
                <div>
                  {t("trace.start")}{" "}
                  {new Date(stage.started_at).toLocaleTimeString(i18n.language)}
                </div>
              )}
              {stage.finished_at && (
                <div>
                  {t("trace.completedAt")}{" "}
                  {new Date(stage.finished_at).toLocaleTimeString(i18n.language)}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function ProcessingTracePanel({ documentId }: Props) {
  const { t } = useTranslation("pipeline");
  const { data, isLoading, error } = useProcessingTrace(documentId);

  if (isLoading) {
    return (
      <div className="text-xs text-[var(--text-muted)]">
        {t("trace.loading")}
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-xs text-[var(--color-error-text)]">
        {t("trace.error")}
      </div>
    );
  }

  if (!data || data.stages.length === 0) {
    return (
      <div className="text-xs text-[var(--text-faint)]">
        {t("trace.unavailable")}
      </div>
    );
  }

  const succeeded = data.stages.filter((s) => s.status === "succeeded").length;
  const total = data.stages.length;
  const pct = Math.round((succeeded / total) * 100);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-[11px]">
        <span className="text-[var(--text-muted)]">
          {t("trace.stagesCompleted", { succeeded, total })}
        </span>
        <span className="text-[var(--text-faint)]">{data.document_status}</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--bg-elevated-soft)]">
        <div
          className="h-full rounded-full bg-[var(--color-success)] transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="space-y-2">
        {data.stages.map((stage, i) => (
          <StageRow key={`${stage.task_name}-${i}`} stage={stage} />
        ))}
      </div>
    </div>
  );
}

export default ProcessingTracePanel;


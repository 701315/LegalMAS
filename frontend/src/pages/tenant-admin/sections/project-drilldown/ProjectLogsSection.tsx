// =============================================================
// src/pages/tenant-admin/sections/project-drilldown/ProjectLogsSection.tsx
// (refactored: useLogSelection + useLogCopy)
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import { Filter, Loader2 } from "lucide-react";
import type { UseQueryResult } from "@tanstack/react-query";
import type {
  LogEntry,
  LogsMode,
  LogsResponse,
} from "../../../../api/tenantAdmin";
import Button from "../../../../components/ui/Button";
import {
  SECTION_CARD,
  LABEL_XS,
  FOCUS_RING,
  SINCE_OPTIONS,
} from "../../constants";
import ModeSwitch from "../../components/ModeSwitch";
import LogsTable from "../../components/LogsTable";
import LogDetailsPane from "../../components/LogDetailsPane";
import {
  useLogsSelectionWithReset,
  useLogCopy,
} from "../../hooks/useLogSelection";

export interface ProjectLogsSectionProps {
  logsQ: UseQueryResult<LogsResponse | undefined>;
  logsMode: LogsMode;
  onLogsModeChange: (mode: LogsMode) => void;
  projectLogsSince: number;
  onProjectLogsSinceChange: (minutes: number) => void;
  correlationRunId: string | null;
  correlationDocId: string | null;
  correlationTaskId: string | null;
  onCorrelationChange: (
    runId: string | null,
    docId: string | null,
    taskId: string | null,
  ) => void;
}

const ProjectLogsSection: React.FC<ProjectLogsSectionProps> = ({
  logsQ,
  logsMode,
  onLogsModeChange,
  projectLogsSince,
  onProjectLogsSinceChange,
  correlationRunId,
  correlationDocId,
  correlationTaskId,
  onCorrelationChange,
}) => {
  const { t } = useTranslation("tenantAdmin");

  // ───────────────── Derived data ─────────────────

  const logs = logsQ.data?.entries ?? [];
  const logsStats = logsQ.data?.stats;
  const lokiUp = logsQ.data?.loki_available ?? false;

  // ───────────────── Selection (extracted hook) ─────────────────

  const { selectedLogIdx, setSelectedLogIdx } =
    useLogsSelectionWithReset([
      logsMode,
      projectLogsSince,
      correlationRunId,
      correlationDocId,
      correlationTaskId,
    ]);

  const selectedLog: LogEntry | null =
    selectedLogIdx != null ? logs[selectedLogIdx] ?? null : null;

  // ───────────────── Copy (extracted hook) ─────────────────

  const { copied, handleCopy } = useLogCopy(
    () => selectedLog?.raw ?? null,
  );

  // ───────────────── Correlation ─────────────────

  const hasCorrelation =
    correlationRunId || correlationDocId || correlationTaskId;

  const clearCorrelation = () => {
    onCorrelationChange(null, null, null);
  };

  // ───────────────── Render ─────────────────

  return (
    <div className="flex h-full min-h-0 flex-col px-5 pb-5 pt-4">
      {/* Header controls */}
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <ModeSwitch value={logsMode} onChange={onLogsModeChange} />

          <label className="inline-flex items-center gap-1.5">
            <span className={LABEL_XS}>{t("drillDown.logs.period")}</span>
            <select
              value={String(projectLogsSince)}
              onChange={(e) =>
                onProjectLogsSinceChange(
                  Number.parseInt(e.target.value, 10) || 0,
                )
              }
              className="min-h-7 rounded-lg border border-[var(--border)] bg-[var(--bg-base)] px-2 text-xs text-[var(--text-primary)] outline-none focus:border-[var(--accent-primary)]"
            >
              {SINCE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {t(`logsTab.periodOptions.${opt.value}`, { defaultValue: opt.label })}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {hasCorrelation && (
            <button
              type="button"
              onClick={clearCorrelation}
              className={`inline-flex items-center gap-1 rounded-full border border-[var(--accent-primary)] bg-[var(--accent-muted)] px-2.5 py-1 text-[11px] font-medium text-[var(--accent-primary)] hover:brightness-95 ${FOCUS_RING}`}
            >
              <Filter size={11} />
              {correlationRunId && (
                <span>run: {correlationRunId.slice(0, 8)}…</span>
              )}
              {correlationDocId && (
                <span>doc: {correlationDocId.slice(0, 8)}…</span>
              )}
              {correlationTaskId && (
                <span>task: {correlationTaskId.slice(0, 8)}…</span>
              )}
              <span className="ml-1 text-[10px] opacity-70">
                {t("logsTab.reset")}
              </span>
            </button>
          )}

          {logsStats && (
            <p className="text-[10px] text-[var(--text-muted)]">
              {t("drillDown.logs.shownCount", { count: logsStats.returned })}
              {logsStats.filtered_out_by_mode > 0
                ? t("drillDown.logs.hiddenCount", { count: logsStats.filtered_out_by_mode })
                : ""}
            </p>
          )}
        </div>
      </div>

      {/* Loki warning */}
      {!lokiUp && logsQ.data && (
        <div className="mb-3 shrink-0 rounded-xl border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-4 py-3 text-xs text-[var(--color-warning-text)]">
          {t("drillDown.logs.lokiUnavailableDegraded")}
        </div>
      )}

      {/* Main content */}
      <div className={`${SECTION_CARD} flex min-h-0 flex-1 overflow-hidden`}>
        {logsQ.isLoading && !logsQ.data ? (
          <div className="flex h-full w-full items-center justify-center text-[var(--text-muted)]">
            <Loader2 size={20} className="animate-spin" />
            <span className="ml-3 text-sm">{t("logsTab.loading")}</span>
          </div>
        ) : logsQ.error && !logsQ.data ? (
          <div className="flex h-full w-full items-center justify-center p-5 text-center">
            <div>
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {t("logsTab.loadError")}
              </p>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => logsQ.refetch()}
                className="mt-3"
              >
                {t("actions.retry", { ns: "common" })}
              </Button>
            </div>
          </div>
        ) : !lokiUp ? (
          <div className="flex h-full w-full items-center justify-center text-sm text-[var(--text-muted)]">
            {t("logsTab.lokiUnavailable")}
          </div>
        ) : (
          <div className="grid h-full w-full grid-cols-1 xl:grid-cols-[minmax(0,1fr)_minmax(320px,420px)]">
            <div className="flex min-h-0 min-w-0 flex-col overflow-hidden xl:border-r xl:border-[var(--border-subtle)]">
              {logs.length === 0 ? (
                <div className="flex h-full items-center justify-center p-6 text-center text-sm text-[var(--text-muted)]">
                  {logsMode === "operational"
                    ? t("drillDown.logs.noOperationalLogsFound")
                    : t("drillDown.logs.noLogsFoundDebug")}
                </div>
              ) : (
                <div className="min-h-0 flex-1 overflow-auto">
                  <LogsTable
                    logs={logs}
                    selectedIdx={selectedLogIdx}
                    onSelect={setSelectedLogIdx}
                    compact
                  />
                </div>
              )}
            </div>

            <aside className="hidden min-h-0 overflow-hidden bg-[var(--bg-elevated-soft)] xl:flex xl:flex-col">
              <LogDetailsPane
                entry={selectedLog}
                copied={copied}
                onCopy={handleCopy}
                onClear={() => setSelectedLogIdx(null)}
                correlations={{
                  onFilterByRun: (id) => {
                    onCorrelationChange(id, null, null);
                    onLogsModeChange("debug");
                  },
                  onFilterByDocument: (id) => {
                    onCorrelationChange(null, id, null);
                    onLogsModeChange("debug");
                  },
                  onFilterByTask: (id) => {
                    onCorrelationChange(null, null, id);
                    onLogsModeChange("debug");
                  },
                }}
              />
            </aside>
          </div>
        )}
      </div>

      {/* Mobile fallback */}
      {selectedLog && (
        <div
          className={`${SECTION_CARD} mt-3 shrink-0 overflow-hidden xl:hidden`}
        >
          <LogDetailsPane
            entry={selectedLog}
            copied={copied}
            onCopy={handleCopy}
            onClear={() => setSelectedLogIdx(null)}
          />
        </div>
      )}
    </div>
  );
};

export default ProjectLogsSection;



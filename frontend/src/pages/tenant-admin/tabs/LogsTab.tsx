// =============================================================
// src/pages/tenant-admin/tabs/LogsTab.tsx
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
  ProjectHealthDTO,
} from "../../../api/tenantAdmin";
import Button from "../../../components/ui/Button";
import {
  SECTION_CARD,
  FILTER_CONTROL,
  LABEL_XS,
  FOCUS_RING,
  SINCE_OPTIONS,
} from "../constants";
import { fmt } from "../utils";
import KpiCard from "../components/KpiCard";
import ModeSwitch from "../components/ModeSwitch";
import LogsTable from "../components/LogsTable";
import LogDetailsPane from "../components/LogDetailsPane";
import {
  useLogsSelectionWithReset,
  useLogCopy,
} from "../hooks/useLogSelection";

export interface AppliedLogsFilters {
  deal_id: string;
  level: string;
  stage: string;
  queue: string;
  since_minutes: number;
  limit: number;
}

export interface LogsTabProps {
  logsQ: UseQueryResult<LogsResponse | undefined>;
  logsMode: LogsMode;
  onLogsModeChange: (mode: LogsMode) => void;
  appliedFilters: AppliedLogsFilters;
  onApplyFilters: (filters: AppliedLogsFilters) => void;
  projects: ProjectHealthDTO[];
  correlationRunId: string | null;
  correlationDocId: string | null;
  correlationTaskId: string | null;
  onCorrelationChange: (
    runId: string | null,
    docId: string | null,
    taskId: string | null,
  ) => void;
}

const LogsTab: React.FC<LogsTabProps> = ({
  logsQ,
  logsMode,
  onLogsModeChange,
  appliedFilters,
  onApplyFilters,
  projects,
  correlationRunId,
  correlationDocId,
  correlationTaskId,
  onCorrelationChange,
}) => {
  const { t, i18n } = useTranslation("tenantAdmin");

  // ───────────────── Draft filters ─────────────────

  const [draftDealId, setDraftDealId] = React.useState(appliedFilters.deal_id);
  const [draftLevel, setDraftLevel] = React.useState(appliedFilters.level);
  const [draftStage, setDraftStage] = React.useState(appliedFilters.stage);
  const [draftQueue, setDraftQueue] = React.useState(appliedFilters.queue);
  const [draftSince, setDraftSince] = React.useState(
    String(appliedFilters.since_minutes),
  );
  const [draftLimit, setDraftLimit] = React.useState(
    String(appliedFilters.limit),
  );

  // ───────────────── Derived data ─────────────────

  const ld = logsQ.data;
  const logs = ld?.entries ?? [];
  const logsStats = ld?.stats;
  const lokiUp = ld?.loki_available ?? false;

  // ───────────────── Selection (extracted hook) ─────────────────

  const { selectedLogIdx, setSelectedLogIdx } =
    useLogsSelectionWithReset([
      appliedFilters,
      logsMode,
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

  // ───────────────── Derived options ─────────────────

  const stageOpts = React.useMemo(() => {
    const stageSet = new Set<string>();
    if (draftStage) stageSet.add(draftStage);
    if (appliedFilters.stage) stageSet.add(appliedFilters.stage);
    logs.forEach((entry) => entry.stage && stageSet.add(entry.stage));
    return Array.from(stageSet).sort((a, b) =>
      a.localeCompare(b, i18n.language),
    );
  }, [draftStage, appliedFilters.stage, logs, i18n.language]);

  const queueOpts = React.useMemo(() => {
    const queueSet = new Set<string>();
    if (draftQueue) queueSet.add(draftQueue);
    if (appliedFilters.queue) queueSet.add(appliedFilters.queue);
    logs.forEach((entry) => entry.queue && queueSet.add(entry.queue));
    return Array.from(queueSet).sort((a, b) =>
      a.localeCompare(b, i18n.language),
    );
  }, [draftQueue, appliedFilters.queue, logs, i18n.language]);

  const hasCorrelation =
    correlationRunId || correlationDocId || correlationTaskId;

  // ───────────────── Handlers ─────────────────

  const handleSubmitFilters = (e: React.FormEvent) => {
    e.preventDefault();
    const s = Number.parseInt(draftSince, 10);
    const l = Number.parseInt(draftLimit, 10);

    onApplyFilters({
      deal_id: draftDealId,
      level: draftLevel,
      stage: draftStage,
      queue: draftQueue,
      since_minutes: Number.isFinite(s) && s >= 0 ? s : 60,
      limit: Number.isFinite(l) && l > 0 ? l : 50,
    });
  };

  const clearCorrelation = () => {
    onCorrelationChange(null, null, null);
  };

  // ───────────────── Render ─────────────────

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden px-5 pb-5 pt-4">
      {/* Header row */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <ModeSwitch value={logsMode} onChange={onLogsModeChange} />

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
      </div>

      {/* Filters */}
      <form
        onSubmit={handleSubmitFilters}
        className="grid shrink-0 grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-7"
      >
        <label className="xl:col-span-2">
          <span className={`mb-1 block ${LABEL_XS}`}>
            {t("logsTab.labels.project")}
          </span>
          <select
            value={draftDealId}
            onChange={(e) => setDraftDealId(e.target.value)}
            className={FILTER_CONTROL}
          >
            <option value="">{t("logsTab.allProjects")}</option>
            {projects.map((p) => (
              <option key={p.deal_id} value={p.deal_id}>
                {p.deal_name}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span className={`mb-1 block ${LABEL_XS}`}>
            {t("logsTab.labels.level")}
          </span>
          <select
            value={draftLevel}
            onChange={(e) => setDraftLevel(e.target.value)}
            className={FILTER_CONTROL}
          >
            <option value="">{t("logsTab.options.all")}</option>
            <option value="error">error</option>
            <option value="warning">warning</option>
            <option value="info">info</option>
          </select>
        </label>

        <label>
          <span className={`mb-1 block ${LABEL_XS}`}>
            {t("logsTab.labels.stage")}
          </span>
          <select
            value={draftStage}
            onChange={(e) => setDraftStage(e.target.value)}
            className={FILTER_CONTROL}
          >
            <option value="">{t("logsTab.options.all")}</option>
            {stageOpts.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span className={`mb-1 block ${LABEL_XS}`}>
            {t("logsTab.labels.queue")}
          </span>
          <select
            value={draftQueue}
            onChange={(e) => setDraftQueue(e.target.value)}
            className={FILTER_CONTROL}
          >
            <option value="">{t("logsTab.options.all")}</option>
            {queueOpts.map((q) => (
              <option key={q} value={q}>
                {q}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span className={`mb-1 block ${LABEL_XS}`}>
            {t("logsTab.labels.period")}
          </span>
          <select
            value={draftSince}
            onChange={(e) => setDraftSince(e.target.value)}
            className={FILTER_CONTROL}
          >
            {SINCE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {t(`logsTab.periodOptions.${opt.value}`, { defaultValue: opt.label })}
              </option>
            ))}
          </select>
        </label>

        <div className="flex items-end gap-2">
          <label className="flex-1">
            <span className={`mb-1 block ${LABEL_XS}`}>
              {t("logsTab.labels.limit")}
            </span>
            <select
              value={draftLimit}
              onChange={(e) => setDraftLimit(e.target.value)}
              className={FILTER_CONTROL}
            >
              <option value="25">25</option>
              <option value="50">50</option>
              <option value="100">100</option>
              <option value="200">200</option>
              <option value="500">500</option>
            </select>
          </label>
          <Button type="submit" size="sm" variant="secondary">
            {t("actions.confirm", { ns: "common" })}
          </Button>
        </div>
      </form>

      {/* Stats */}
      <div className="grid shrink-0 grid-cols-2 gap-2 sm:grid-cols-4">
        <KpiCard
          label={t("logsTab.loki.label")}
          value={
            lokiUp
              ? t("logsTab.loki.available")
              : t("logsTab.loki.unavailable")
          }
          tone={lokiUp ? "ok" : "warn"}
        />
        <KpiCard
          label={t("logsTab.loki.shown")}
          value={fmt(logs.length, i18n.language)}
        />
        <KpiCard
          label={t("logsTab.loki.hiddenInfo")}
          value={fmt(logsStats?.filtered_out_by_mode ?? 0, i18n.language)}
          tone={
            (logsStats?.filtered_out_by_mode ?? 0) > 0 ? "warn" : "default"
          }
        />
        <KpiCard
          label={t("logsTab.loki.mode")}
          value={
            logsMode === "operational"
              ? t("logsTab.loki.modeEvents")
              : t("logsTab.loki.modeDebug")
          }
          tone={logsMode === "operational" ? "ok" : "default"}
        />
      </div>

      {/* Main card */}
      <div className={`${SECTION_CARD} flex min-h-0 flex-1 overflow-hidden`}>
        {logsQ.isLoading && !ld ? (
          <div className="flex h-full w-full items-center justify-center text-[var(--text-muted)]">
            <Loader2 size={20} className="animate-spin" />
            <span className="ml-3 text-sm">{t("logsTab.loading")}</span>
          </div>
        ) : logsQ.error && !ld ? (
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
                  {t("logsTab.noLogsFound")}
                </div>
              ) : (
                <div className="min-h-0 flex-1 overflow-auto">
                  <LogsTable
                    logs={logs}
                    selectedIdx={selectedLogIdx}
                    onSelect={setSelectedLogIdx}
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
              />
            </aside>
          </div>
        )}
      </div>

      {/* Mobile details */}
      {selectedLog && (
        <div className={`${SECTION_CARD} shrink-0 overflow-hidden xl:hidden`}>
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

export default LogsTab;



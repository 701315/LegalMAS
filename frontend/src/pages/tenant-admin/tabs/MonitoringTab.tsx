// =============================================================
// src/pages/tenant-admin/tabs/MonitoringTab.tsx
//
// "Monitoring" tab in admin panel. Displays Prometheus metrics
// for: pipeline, API endpoints, LLM providers, Celery tasks.
//
// Design contract:
// - Loading state while data is being fetched
// - Error state with retry button
// - Warning banner if Prometheus is unavailable ("degraded mode")
// - Tenant-admin-only hint: metrics are global, per-project in drill down
// - Multiple sections wrapped in SECTION_CARD
//
// State ownership:
// - metricsQ (data + loading/error state) lifted to parent — because
//   parent controls enabled: activeTab === "monitoring" (query pattern)
// - All rendering derived from props
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import { Bot, Loader2 } from "lucide-react";
import type { UseQueryResult } from "@tanstack/react-query";
import Button from "../../../components/ui/Button";
import {
  SECTION_CARD,
  SECTION_HEADER_WRAP,
  SECTION_HEADER_INNER,
  SECTION_DIVIDER,
  LABEL_XS,
} from "../constants";
import { formatDateTime, fmt, fmtMs } from "../utils";
import KpiCard from "../components/KpiCard";

// Type for metrics data — matches PlatformMetricsResponse from API
interface PlatformMetricsData {
  prometheus_available: boolean;
  collected_at: string | null;
  pipeline: {
    dlq_size: number | null;
    active_runs: number | null;
    stuck_executions: number | null;
    docs_processed_last_hour: number | null;
    docs_failed_last_hour: number | null;
  };
  api: {
    top_endpoints: Array<{
      method: string;
      handler: string;
      requests: number;
      errors: number;
      p95_ms: number | null;
    }>;
  };
  llm: {
    providers: Array<{
      provider: string;
      requests_last_hour: number;
      timeouts_last_hour: number;
    }>;
  };
  celery: {
    task_failures_last_hour: Array<{
      task_name: string;
      failures_last_hour: number;
      failure_types: string[];
    }>;
  };
}

export interface MonitoringTabProps {
  /** Query result for platform metrics */
  metricsQ: UseQueryResult<PlatformMetricsData | undefined>;
  /** Current user role (for tenant-specific hints) */
  globalRole: string | null | undefined;
}

const MonitoringTab: React.FC<MonitoringTabProps> = ({
  metricsQ,
  globalRole,
}) => {
  const { t, i18n } = useTranslation("tenantAdmin");
  const md = metricsQ.data;
  const promUp = md?.prometheus_available ?? false;

  const metricVal = (v: number | null | undefined) =>
    promUp ? fmt(v ?? 0, i18n.language) : "—";

  // Loading state
  if (metricsQ.isLoading && !md) {
    return (
      <div className="min-h-0 flex-1 overflow-auto">
        <div className="flex h-full items-center justify-center text-[var(--text-muted)]">
          <Loader2 size={20} className="animate-spin" />
          <span className="ml-3 text-sm">{t("monitoringTab.loading")}</span>
        </div>
      </div>
    );
  }

  // Error state
  if (metricsQ.error && !md) {
    return (
      <div className="min-h-0 flex-1 overflow-auto">
        <div className="flex h-full items-center justify-center p-5">
          <div className="text-center">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {t("monitoringTab.loadError")}
            </p>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => metricsQ.refetch()}
              className="mt-3"
            >
              {t("actions.retry", { ns: "common" })}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-0 flex-1 overflow-auto">
      <div className="space-y-4 px-5 pb-5 pt-4">
        {/* Top-level KpiCards: Prometheus status + high-level metrics */}
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
          <KpiCard
            label={t("monitoringTab.prometheus")}
            value={
              promUp
                ? t("monitoringTab.available")
                : t("monitoringTab.unavailable")
            }
            tone={promUp ? "ok" : "warn"}
            sub={t("monitoringTab.updatedAt", {
              date: formatDateTime(md?.collected_at, i18n.language),
            })}
          />
          <KpiCard
            label={t("monitoringTab.dlqSize")}
            value={metricVal(md?.pipeline.dlq_size)}
            tone={
              promUp && (md?.pipeline.dlq_size ?? 0) > 0 ? "warn" : "default"
            }
          />
          <KpiCard
            label={t("monitoringTab.activeRuns")}
            value={metricVal(md?.pipeline.active_runs)}
          />
          <KpiCard
            label={t("monitoringTab.stuckExecutions")}
            value={metricVal(md?.pipeline.stuck_executions)}
            tone={
              promUp && (md?.pipeline.stuck_executions ?? 0) > 0
                ? "error"
                : "default"
            }
          />
        </div>

        {globalRole === "tenant_admin" && (
          <p className="text-[10px] text-[var(--text-muted)]">
            {t("monitoringTab.infrastructureHint")}
          </p>
        )}

        {!promUp && (
          <div className="rounded-xl border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-4 py-3 text-xs text-[var(--color-warning-text)]">
            {t("monitoringTab.degradedMode")}
          </div>
        )}

        {/* Pipeline section */}
        <div className={SECTION_CARD}>
          <div className={SECTION_HEADER_WRAP}>
            <div className={SECTION_HEADER_INNER}>
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {t("monitoringTab.pipeline")}
              </p>
              <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
                {t("monitoringTab.docsLastHour")}
              </p>
            </div>
            <div className={SECTION_DIVIDER} />
          </div>
          <div className="grid grid-cols-2 gap-2 px-5 py-4">
            <KpiCard
              label={t("monitoringTab.processedHour")}
              value={metricVal(md?.pipeline.docs_processed_last_hour)}
              tone={
                promUp && (md?.pipeline.docs_processed_last_hour ?? 0) > 0
                  ? "ok"
                  : "default"
              }
            />
            <KpiCard
              label={t("monitoringTab.failedHour")}
              value={metricVal(md?.pipeline.docs_failed_last_hour)}
              tone={
                promUp && (md?.pipeline.docs_failed_last_hour ?? 0) > 0
                  ? "error"
                  : "default"
              }
            />
          </div>
        </div>

        {/* API endpoints section */}
        <div className={SECTION_CARD}>
          <div className={SECTION_HEADER_WRAP}>
            <div className={SECTION_HEADER_INNER}>
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {t("monitoringTab.api.title")}
              </p>
              <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
                {t("monitoringTab.api.subtitle")}
              </p>
            </div>
            <div className={SECTION_DIVIDER} />
          </div>
          <div className="px-5 py-4">
            {!promUp || (md?.api.top_endpoints ?? []).length === 0 ? (
              <p className="text-[10px] text-[var(--text-muted)]">
                {promUp
                  ? t("monitoringTab.api.noData")
                  : t("monitoringTab.api.promUnavailable")}
              </p>
            ) : (
              <div className="overflow-auto">
                <table className="w-full min-w-[680px] border-collapse">
                  <thead className="bg-[var(--bg-elevated-soft)]">
                    <tr className="border-b border-[var(--border)]">
                      <th className={`px-3 py-2 text-left ${LABEL_XS}`}>
                        {t("monitoringTab.api.headers.endpoint")}
                      </th>
                      <th className={`px-3 py-2 text-left ${LABEL_XS}`}>
                        {t("monitoringTab.api.headers.requests")}
                      </th>
                      <th className={`px-3 py-2 text-left ${LABEL_XS}`}>
                        {t("monitoringTab.api.headers.errors")}
                      </th>
                      <th className={`px-3 py-2 text-left ${LABEL_XS}`}>
                        {t("monitoringTab.api.headers.p95")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {(md?.api.top_endpoints ?? []).map((ep) => (
                      <tr
                        key={`${ep.method}-${ep.handler}`}
                        className="border-b border-[var(--border-subtle)] last:border-b-0"
                      >
                        <td className="px-3 py-2">
                          <p className="font-mono text-[10px] text-[var(--text-muted)]">
                            {ep.method}
                          </p>
                          <p className="truncate text-sm text-[var(--text-primary)]">
                            {ep.handler}
                          </p>
                        </td>
                        <td className="px-3 py-2 text-sm font-semibold tabular-nums text-[var(--text-primary)]">
                          {fmt(ep.requests, i18n.language)}
                        </td>
                        <td className="px-3 py-2 text-sm tabular-nums">
                          <span
                            className={
                              ep.errors > 0
                                ? "font-semibold text-[var(--color-error-text)]"
                                : "text-[var(--text-secondary)]"
                            }
                          >
                            {fmt(ep.errors, i18n.language)}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-sm text-[var(--text-secondary)]">
                          {fmtMs(ep.p95_ms, i18n.language)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* LLM + Celery — 2-column grid on xl+ */}
        <div className="grid gap-4 xl:grid-cols-2">
          {/* LLM providers */}
          <div className={SECTION_CARD}>
            <div className={SECTION_HEADER_WRAP}>
              <div className={SECTION_HEADER_INNER}>
                <p className="text-sm font-semibold text-[var(--text-primary)]">
                  {t("monitoringTab.llm.title")}
                </p>
                <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
                  {t("monitoringTab.llm.subtitle")}
                </p>
              </div>
              <div className={SECTION_DIVIDER} />
            </div>
            <div className="px-5 py-4">
              {!promUp || (md?.llm.providers ?? []).length === 0 ? (
                <p className="text-[10px] text-[var(--text-muted)]">
                  {promUp
                    ? t("monitoringTab.llm.noData")
                    : t("monitoringTab.api.promUnavailable")}
                </p>
              ) : (
                <div className="grid gap-2">
                  {(md?.llm.providers ?? []).map((prov) => (
                    <div
                      key={prov.provider}
                      className="rounded-xl border border-[var(--border)] px-3 py-2"
                    >
                      <div className="flex items-center justify-between">
                        <p className="truncate text-sm font-semibold text-[var(--text-primary)]">
                          {prov.provider}
                        </p>
                        <Bot size={14} className="text-[var(--text-muted)]" />
                      </div>
                      <div className="mt-2 grid grid-cols-2 gap-2">
                        <div>
                          <p className={LABEL_XS}>
                            {t("monitoringTab.llm.headers.requests")}
                          </p>
                          <p className="mt-0.5 text-sm font-semibold tabular-nums text-[var(--text-primary)]">
                            {fmt(prov.requests_last_hour, i18n.language)}
                          </p>
                        </div>
                        <div>
                          <p className={LABEL_XS}>
                            {t("monitoringTab.llm.headers.timeouts")}
                          </p>
                          <p
                            className={`mt-0.5 text-sm font-semibold tabular-nums ${
                              prov.timeouts_last_hour > 0
                                ? "text-[var(--color-error-text)]"
                                : "text-[var(--text-primary)]"
                            }`}
                          >
                            {fmt(prov.timeouts_last_hour, i18n.language)}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Celery task failures */}
          <div className={SECTION_CARD}>
            <div className={SECTION_HEADER_WRAP}>
              <div className={SECTION_HEADER_INNER}>
                <p className="text-sm font-semibold text-[var(--text-primary)]">
                  {t("monitoringTab.celery.title")}
                </p>
                <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
                  {t("monitoringTab.celery.subtitle")}
                </p>
              </div>
              <div className={SECTION_DIVIDER} />
            </div>
            <div className="px-5 py-4">
              {!promUp ||
              (md?.celery.task_failures_last_hour ?? []).length === 0 ? (
                <p className="text-[10px] text-[var(--text-muted)]">
                  {promUp
                    ? t("monitoringTab.celery.noData")
                    : t("monitoringTab.api.promUnavailable")}
                </p>
              ) : (
                <div className="overflow-auto">
                  <table className="w-full min-w-[480px] border-collapse">
                    <thead className="bg-[var(--bg-elevated-soft)]">
                      <tr className="border-b border-[var(--border)]">
                        <th className={`px-3 py-2 text-left ${LABEL_XS}`}>
                          {t("monitoringTab.celery.headers.task")}
                        </th>
                        <th className={`px-3 py-2 text-left ${LABEL_XS}`}>
                          {t("monitoringTab.celery.headers.failures")}
                        </th>
                        <th className={`px-3 py-2 text-left ${LABEL_XS}`}>
                          {t("monitoringTab.celery.headers.types")}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {(md?.celery.task_failures_last_hour ?? []).map((tName) => (
                        <tr
                          key={tName.task_name}
                          className="border-b border-[var(--border-subtle)] last:border-b-0"
                        >
                          <td className="px-3 py-2 font-mono text-[10px] text-[var(--text-primary)]">
                            {tName.task_name}
                          </td>
                          <td className="px-3 py-2 text-sm font-semibold tabular-nums text-[var(--color-error-text)]">
                            {fmt(tName.failures_last_hour, i18n.language)}
                          </td>
                          <td className="px-3 py-2 text-sm text-[var(--text-secondary)]">
                            {tName.failure_types.length > 0
                              ? tName.failure_types.join(", ")
                              : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default MonitoringTab;



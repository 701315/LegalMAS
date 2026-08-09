// =============================================================
// src/pages/tenant-admin/tabs/MonitoringTab.tsx
//
// Вкладка "Мониторинг" в admin panel. Отображает метрики
// Prometheus по: pipeline, API endpoints, LLM providers, Celery tasks.
//
// Design contract:
// - Loading state если данные ещё не пришли
// - Error state с retry button
// - Warning banner если Prometheus недоступен (промышленный "degraded mode")
// - Tenant-admin-only hint: метрики глобальные, для per-project — в drill down
// - Multiple sections в SECTION_CARD wrappers
//
// State ownership:
// - metricsQ (данные + loading/error state) поднят в parent — потому что
//   parent решает enabled: activeTab === "monitoring" (query pattern)
// - Все rendering derived from props
// =============================================================

import React from "react";
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

// Type для metrics data — matches PlatformMetricsResponse из api
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
  /** Query result для platform metrics */
  metricsQ: UseQueryResult<PlatformMetricsData | undefined>;
  /** Роль текущего пользователя (для показа tenant-specific hints) */
  globalRole: string | null | undefined;
}

const MonitoringTab: React.FC<MonitoringTabProps> = ({
  metricsQ,
  globalRole,
}) => {
  const md = metricsQ.data;
  const promUp = md?.prometheus_available ?? false;

  const metricVal = (v: number | null | undefined) =>
    promUp ? fmt(v ?? 0) : "—";

  // Loading state
  if (metricsQ.isLoading && !md) {
    return (
      <div className="min-h-0 flex-1 overflow-auto">
        <div className="flex h-full items-center justify-center text-[var(--text-muted)]">
          <Loader2 size={20} className="animate-spin" />
          <span className="ml-3 text-sm">Загружаем метрики…</span>
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
              Не удалось загрузить метрики
            </p>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => metricsQ.refetch()}
              className="mt-3"
            >
              Повторить
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
            label="Prometheus"
            value={promUp ? "Доступен" : "Недоступен"}
            tone={promUp ? "ok" : "warn"}
            sub={`Обновлено: ${formatDateTime(md?.collected_at)}`}
          />
          <KpiCard
            label="DLQ size"
            value={metricVal(md?.pipeline.dlq_size)}
            tone={
              promUp && (md?.pipeline.dlq_size ?? 0) > 0 ? "warn" : "default"
            }
          />
          <KpiCard
            label="Active runs"
            value={metricVal(md?.pipeline.active_runs)}
          />
          <KpiCard
            label="Stuck executions"
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
            Метрики Prometheus — инфраструктурные и глобальные. Для метрик по
            проекту откройте проект во вкладке «Проекты».
          </p>
        )}

        {!promUp && (
          <div className="rounded-xl border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-4 py-3 text-xs text-[var(--color-warning-text)]">
            Метрики временно недоступны — деградированный режим.
          </div>
        )}

        {/* Pipeline section */}
        <div className={SECTION_CARD}>
          <div className={SECTION_HEADER_WRAP}>
            <div className={SECTION_HEADER_INNER}>
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                Pipeline
              </p>
              <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
                Документы за последний час
              </p>
            </div>
            <div className={SECTION_DIVIDER} />
          </div>
          <div className="grid grid-cols-2 gap-2 px-5 py-4">
            <KpiCard
              label="Processed / 1h"
              value={metricVal(md?.pipeline.docs_processed_last_hour)}
              tone={
                promUp && (md?.pipeline.docs_processed_last_hour ?? 0) > 0
                  ? "ok"
                  : "default"
              }
            />
            <KpiCard
              label="Failed / 1h"
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
                API
              </p>
              <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
                Топ-5 endpoint&apos;ов по запросам за час
              </p>
            </div>
            <div className={SECTION_DIVIDER} />
          </div>
          <div className="px-5 py-4">
            {!promUp || (md?.api.top_endpoints ?? []).length === 0 ? (
              <p className="text-[10px] text-[var(--text-muted)]">
                {promUp
                  ? "Нет данных — метрики появятся после накопления трафика."
                  : "Prometheus недоступен."}
              </p>
            ) : (
              <div className="overflow-auto">
                <table className="w-full min-w-[680px] border-collapse">
                  <thead className="bg-[var(--bg-elevated-soft)]">
                    <tr className="border-b border-[var(--border)]">
                      <th className={`px-3 py-2 text-left ${LABEL_XS}`}>
                        Endpoint
                      </th>
                      <th className={`px-3 py-2 text-left ${LABEL_XS}`}>
                        Requests
                      </th>
                      <th className={`px-3 py-2 text-left ${LABEL_XS}`}>
                        Errors
                      </th>
                      <th className={`px-3 py-2 text-left ${LABEL_XS}`}>
                        P95
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
                          {fmt(ep.requests)}
                        </td>
                        <td className="px-3 py-2 text-sm tabular-nums">
                          <span
                            className={
                              ep.errors > 0
                                ? "font-semibold text-[var(--color-error-text)]"
                                : "text-[var(--text-secondary)]"
                            }
                          >
                            {fmt(ep.errors)}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-sm text-[var(--text-secondary)]">
                          {fmtMs(ep.p95_ms)}
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
                  LLM
                </p>
                <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
                  Запросы и таймауты за час
                </p>
              </div>
              <div className={SECTION_DIVIDER} />
            </div>
            <div className="px-5 py-4">
              {!promUp || (md?.llm.providers ?? []).length === 0 ? (
                <p className="text-[10px] text-[var(--text-muted)]">
                  {promUp
                    ? "Нет LLM-метрик — появятся после прогона pipeline."
                    : "Prometheus недоступен."}
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
                          <p className={LABEL_XS}>Requests</p>
                          <p className="mt-0.5 text-sm font-semibold tabular-nums text-[var(--text-primary)]">
                            {fmt(prov.requests_last_hour)}
                          </p>
                        </div>
                        <div>
                          <p className={LABEL_XS}>Timeouts</p>
                          <p
                            className={`mt-0.5 text-sm font-semibold tabular-nums ${
                              prov.timeouts_last_hour > 0
                                ? "text-[var(--color-error-text)]"
                                : "text-[var(--text-primary)]"
                            }`}
                          >
                            {fmt(prov.timeouts_last_hour)}
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
                  Celery
                </p>
                <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
                  Ошибки задач за час
                </p>
              </div>
              <div className={SECTION_DIVIDER} />
            </div>
            <div className="px-5 py-4">
              {!promUp ||
              (md?.celery.task_failures_last_hour ?? []).length === 0 ? (
                <p className="text-[10px] text-[var(--text-muted)]">
                  {promUp
                    ? "Нет ошибок Celery за последний час."
                    : "Prometheus недоступен."}
                </p>
              ) : (
                <div className="overflow-auto">
                  <table className="w-full min-w-[480px] border-collapse">
                    <thead className="bg-[var(--bg-elevated-soft)]">
                      <tr className="border-b border-[var(--border)]">
                        <th className={`px-3 py-2 text-left ${LABEL_XS}`}>
                          Task
                        </th>
                        <th className={`px-3 py-2 text-left ${LABEL_XS}`}>
                          Failures
                        </th>
                        <th className={`px-3 py-2 text-left ${LABEL_XS}`}>
                          Types
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {(md?.celery.task_failures_last_hour ?? []).map((t) => (
                        <tr
                          key={t.task_name}
                          className="border-b border-[var(--border-subtle)] last:border-b-0"
                        >
                          <td className="px-3 py-2 font-mono text-[10px] text-[var(--text-primary)]">
                            {t.task_name}
                          </td>
                          <td className="px-3 py-2 text-sm font-semibold tabular-nums text-[var(--color-error-text)]">
                            {fmt(t.failures_last_hour)}
                          </td>
                          <td className="px-3 py-2 text-sm text-[var(--text-secondary)]">
                            {t.failure_types.length > 0
                              ? t.failure_types.join(", ")
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



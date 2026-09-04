// =============================================================
// src/pages/tenant-admin/sections/project-drilldown/ProjectOverviewSection.tsx
//
// Overview sub-tab внутри ProjectDrillDown. Отображает три
// секции с метриками и таблицами:
//
// 1. Документы — KpiCards + breakdown по статусам/типам
// 2. Анализы (runs) — KpiCards + таблица последних runs
// 3. Проблемы и ошибки — filter tabs + KpiCards + table с ErrorRow'ами
//
// Design contract:
// - space-y-4 между секциями
// - Каждая секция = SECTION_CARD wrapper
// - Filter tabs для errors (all/document/run)
// - Expand/collapse для error items
// - Клик "Логи" в run row или error row → switch на Logs sub-tab
//
// State ownership:
// - errorFilter, expandedErrorKey — локальный state (специфичный для этой секции)
// - Callbacks для switch на Logs sub-tab поднимаются в parent (ProjectDrillDown)
//   потому что они меняют subTab + logs correlation state
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import { Database } from "lucide-react";
import type {
  ProjectErrorItem,
  ProjectInsightsResponse,
} from "../../../../api/tenantAdmin";
import Button from "../../../../components/ui/Button";
import {
  SECTION_CARD,
  SECTION_HEADER_WRAP,
  SECTION_HEADER_INNER,
  SECTION_DIVIDER,
  LABEL_XS,
  FOCUS_RING,
  RUN_STATUS_CONFIG,
} from "../../constants";
import type { ErrorFilter } from "../../types";
import { formatDateTime, fmt, fmtDurationSeconds, toneClass } from "../../utils";
import KpiCard from "../../components/KpiCard";
import ErrorRow from "../../components/ErrorRow";

export interface ProjectOverviewSectionProps {
  /** Данные insights для проекта */
  insights: ProjectInsightsResponse | undefined;
  /** Callback при клике "Логи" в run row — parent переключает на Logs sub-tab */
  onOpenLogsForRun: (runId: string) => void;
  /** Callback при клике "Логи" в error row — parent переключает на Logs sub-tab */
  onOpenLogsForError: (item: ProjectErrorItem) => void;
}

const ProjectOverviewSection: React.FC<ProjectOverviewSectionProps> = ({
  insights,
  onOpenLogsForRun,
  onOpenLogsForError,
}) => {
  const { t, i18n } = useTranslation("tenantAdmin");
  const [errorFilter, setErrorFilter] = React.useState<ErrorFilter>("all");
  const [expandedErrorKey, setExpandedErrorKey] = React.useState<string | null>(
    null,
  );

  const runStats = insights?.runs;
  const docs = insights?.documents;
  const errors = insights?.errors;
  const allErrorItems = errors?.items ?? [];

  const filteredErrorItems = allErrorItems.filter((item) => {
    if (errorFilter === "all") return true;
    return item.kind === errorFilter;
  });

  const errorKey = (item: ProjectErrorItem, idx: number) =>
    `${item.kind}-${item.document_id ?? ""}-${item.run_id ?? ""}-${idx}`;

  return (
    <div className="space-y-4 px-5 pb-5 pt-4">
      {/* Documents section */}
      <div className={SECTION_CARD}>
        <div className={SECTION_HEADER_WRAP}>
          <div className={SECTION_HEADER_INNER}>
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {t("drillDown.overview.documents.title")}
            </p>
            <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
              {t("drillDown.overview.documents.subtitle")}
            </p>
          </div>
          <div className={SECTION_DIVIDER} />
        </div>
        <div className="grid grid-cols-2 gap-2 px-5 py-4 sm:grid-cols-4">
          <KpiCard
            label={t("drillDown.overview.all")}
            value={fmt(docs?.total, i18n.language)}
          />
          <KpiCard
            label={t("drillDown.overview.errors")}
            value={fmt(docs?.failed, i18n.language)}
            tone={(docs?.failed ?? 0) > 0 ? "error" : "default"}
          />
          <KpiCard
            label={t("drillDown.overview.quarantine")}
            value={fmt(docs?.quarantine, i18n.language)}
            tone={(docs?.quarantine ?? 0) > 0 ? "warn" : "default"}
          />
          <KpiCard
            label={t("drillDown.overview.reviewed")}
            value={fmt(docs?.reviewed_by_person, i18n.language)}
          />
        </div>

        {docs && Object.keys(docs.by_status).length > 0 && (
          <div className="border-t border-[var(--border-subtle)] px-5 py-4">
            <p className={LABEL_XS}>{t("drillDown.overview.byStatus")}</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {Object.entries(docs.by_status).map(([st, cnt]) => (
                <span
                  key={st}
                  className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[11px] text-[var(--text-secondary)]"
                >
                  {st}: <span className="tabular-nums">{fmt(cnt, i18n.language)}</span>
                </span>
              ))}
            </div>
          </div>
        )}

        {docs && Object.keys(docs.by_doc_type).length > 0 && (
          <div className="border-t border-[var(--border-subtle)] px-5 py-4">
            <p className={LABEL_XS}>{t("drillDown.overview.byDocType")}</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {Object.entries(docs.by_doc_type).map(([dt, cnt]) => (
                <span
                  key={dt}
                  className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[11px] text-[var(--text-secondary)]"
                >
                  {dt}: <span className="tabular-nums">{fmt(cnt, i18n.language)}</span>
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Runs section */}
      <div className={SECTION_CARD}>
        <div className={SECTION_HEADER_WRAP}>
          <div className={SECTION_HEADER_INNER}>
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {t("drillDown.overview.runs.title")}
            </p>
            <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
              {t("drillDown.overview.runs.subtitle")}
            </p>
          </div>
          <div className={SECTION_DIVIDER} />
        </div>
        <div className="grid grid-cols-2 gap-2 px-5 py-4 sm:grid-cols-4">
          <KpiCard
            label={t("drillDown.overview.all")}
            value={fmt(runStats?.total_runs, i18n.language)}
          />
          <KpiCard
            label={t("drillDown.overview.successful")}
            value={fmt(runStats?.completed_runs, i18n.language)}
            tone={(runStats?.completed_runs ?? 0) > 0 ? "ok" : "default"}
          />
          <KpiCard
            label={t("drillDown.overview.failed")}
            value={fmt(runStats?.failed_runs, i18n.language)}
            tone={(runStats?.failed_runs ?? 0) > 0 ? "error" : "default"}
          />
          <KpiCard
            label={t("drillDown.overview.avgDuration")}
            value={fmtDurationSeconds(runStats?.avg_duration_seconds, i18n.language)}
          />
        </div>

        {(runStats?.recent_runs.length ?? 0) > 0 && (
          <div className="border-t border-[var(--border-subtle)] px-5 py-4">
            <p className={LABEL_XS}>{t("drillDown.overview.recentRuns")}</p>
            <div className="mt-2 overflow-auto">
              <table className="w-full min-w-[560px] border-collapse">
                <thead className="bg-[var(--bg-elevated-soft)]">
                  <tr className="border-b border-[var(--border)]">
                    <th className={`px-3 py-2 text-left ${LABEL_XS}`}>
                      {t("drillDown.overview.headers.status")}
                    </th>
                    <th className={`px-3 py-2 text-left ${LABEL_XS}`}>
                      {t("drillDown.overview.headers.progress")}
                    </th>
                    <th className={`px-3 py-2 text-left ${LABEL_XS}`}>
                      {t("drillDown.overview.headers.started")}
                    </th>
                    <th className={`px-3 py-2 text-left ${LABEL_XS}`}>
                      {t("drillDown.overview.headers.completed")}
                    </th>
                    <th className={`px-3 py-2 text-left ${LABEL_XS}`} />
                  </tr>
                </thead>
                <tbody>
                  {runStats!.recent_runs.map((r) => {
                    const cfg = RUN_STATUS_CONFIG[r.status] ?? {
                      label: r.status,
                      tone: "neutral" as const,
                    };
                    return (
                      <tr
                        key={r.run_id}
                        className="border-b border-[var(--border-subtle)] last:border-b-0"
                      >
                        <td className="px-3 py-2">
                          <span
                            className={`text-xs font-medium ${toneClass(cfg.tone)}`}
                          >
                            {cfg.label}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-sm tabular-nums text-[var(--text-secondary)]">
                          {r.completed_checks}/{r.total_checks}
                        </td>
                        <td className="px-3 py-2 text-[11px] text-[var(--text-muted)]">
                          {formatDateTime(r.started_at, i18n.language)}
                        </td>
                        <td className="px-3 py-2 text-[11px] text-[var(--text-muted)]">
                          {formatDateTime(r.completed_at, i18n.language)}
                        </td>
                        <td className="px-3 py-2 text-right">
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => onOpenLogsForRun(r.run_id)}
                          >
                            {t("drillDown.overview.logs")}
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Problems & Errors section */}
      <div className={SECTION_CARD}>
        <div className={SECTION_HEADER_WRAP}>
          <div
            className={`flex flex-wrap items-center justify-between gap-2 ${SECTION_HEADER_INNER}`}
          >
            <div className="min-w-0">
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {t("drillDown.overview.problems.title")}
              </p>
              <p className="mt-0.5 flex items-center gap-1 text-[10px] text-[var(--text-muted)]">
                <Database size={11} />
                {t("drillDown.overview.problems.subtitle")}
              </p>
            </div>

            <div className="inline-flex overflow-hidden rounded-xl border border-[var(--border)] text-[11px]">
              {(
                [
                  { v: "all", label: t("drillDown.overview.filters.all") },
                  { v: "document", label: t("drillDown.overview.filters.documents") },
                  { v: "run", label: t("drillDown.overview.filters.runs") },
                ] as { v: ErrorFilter; label: string }[]
              ).map((opt) => (
                <button
                  key={opt.v}
                  type="button"
                  onClick={() => setErrorFilter(opt.v)}
                  className={`px-2.5 py-1 transition-colors ${FOCUS_RING} ${
                    errorFilter === opt.v
                      ? "bg-[var(--accent-muted)] text-[var(--accent-primary)]"
                      : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated-soft)]"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
          <div className={SECTION_DIVIDER} />
        </div>

        <div className="grid grid-cols-2 gap-2 px-5 py-4 sm:grid-cols-4">
          <KpiCard
            label={t("drillDown.overview.problems.docsFailed")}
            value={fmt(errors?.failed_documents, i18n.language)}
            tone={(errors?.failed_documents ?? 0) > 0 ? "error" : "default"}
          />
          <KpiCard
            label={t("drillDown.overview.problems.docsQuarantine")}
            value={fmt(errors?.quarantine_documents, i18n.language)}
            tone={
              (errors?.quarantine_documents ?? 0) > 0 ? "warn" : "default"
            }
          />
          <KpiCard
            label={t("drillDown.overview.problems.runsFailed")}
            value={fmt(errors?.failed_runs, i18n.language)}
            tone={(errors?.failed_runs ?? 0) > 0 ? "error" : "default"}
          />
          <KpiCard
            label={t("drillDown.overview.problems.runsWithErrors")}
            value={fmt(errors?.completed_with_errors_runs, i18n.language)}
            tone={
              (errors?.completed_with_errors_runs ?? 0) > 0
                ? "warn"
                : "default"
            }
          />
        </div>

        <div className="border-t border-[var(--border-subtle)]">
          {filteredErrorItems.length === 0 ? (
            <div className="flex min-h-[120px] items-center justify-center px-5 py-6 text-sm text-[var(--text-muted)]">
              {(errors?.total_items ?? 0) === 0
                ? t("drillDown.overview.problems.noErrors")
                : t("drillDown.overview.problems.noFilteredRecords")}
            </div>
          ) : (
            <div className="overflow-auto">
              <table className="w-full min-w-[860px] border-collapse">
                <thead className="bg-[var(--bg-elevated-soft)]">
                  <tr className="border-b border-[var(--border)]">
                    <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>
                      {t("drillDown.overview.headers.type")}
                    </th>
                    <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>
                      {t("drillDown.overview.headers.object")}
                    </th>
                    <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>
                      {t("drillDown.overview.headers.statusStage")}
                    </th>
                    <th className={`px-4 py-2.5 text-left ${LABEL_XS}`}>
                      {t("drillDown.overview.headers.error")}
                    </th>
                    <th className={`px-4 py-2.5 ${LABEL_XS}`} />
                  </tr>
                </thead>
                <tbody>
                  {filteredErrorItems.map((item, idx) => {
                    const key = errorKey(item, idx);
                    return (
                      <ErrorRow
                        key={key}
                        item={item}
                        expanded={expandedErrorKey === key}
                        onToggle={() =>
                          setExpandedErrorKey(
                            expandedErrorKey === key ? null : key,
                          )
                        }
                        onOpenLogs={() => onOpenLogsForError(item)}
                      />
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {errors?.truncated && (
            <p className="px-5 py-3 text-[10px] text-[var(--text-muted)]">
              {t("drillDown.overview.problems.truncated", { count: filteredErrorItems.length })}
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

export default ProjectOverviewSection;



// =============================================================
// src/pages/tabs/OverviewTab.tsx
// =============================================================

import React from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { AuditLogEntry, Deal, RunStatus } from "../../types";
import {
  runKeys,
  useDealRuns,
  useRun,
  useStartRun,
} from "../../api/runs";
import { useSetPrimaryLanguage, useUpdateDeal } from "../../api/deals";
import { useDocuments } from "../../api/documents";
import { useDealPermissions } from "../../hooks/usePermissions";
import { useSSEProgress } from "../../hooks/useSSE";
import { RUN_STATUS_CONFIG } from "../../utils/statusConfig";
import { useAuditLog } from "../../api/audit";
import Button from "../../components/ui/Button";
import AnalysisActionsPanel from "./overview/AnalysisActionsPanel";
import LaunchWideOverlay from "./overview/LaunchWideOverlay";
import {
  normalizeDiscoveryStatus,
  normalizeLang,
} from "../../utils/languageDiscovery";

export type ChecksMode =
  | "global_only"
  | "doc_type_only"
  | "global_and_doc_type";

interface OverviewTabProps {
  deal: Deal;
  currentRunId?: string | null;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

function formatDateShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function buildProjectTimelineFromAudit(entries: AuditLogEntry[]) {
  const imports = entries.filter((e) => e.action === "IMPORT");
  const quarantined = entries.filter(
    (e) => e.action === "IMPORT_FILE_QUARANTINED",
  );
  const unsupported = entries.filter(
    (e) => e.action === "IMPORT_FILE_UNSUPPORTED",
  );
  const reclassified = entries.filter(
    (e) => e.action === "DOCUMENT_RECLASSIFIED_API",
  );

  const sortedImports = imports
    .slice()
    .sort(
      (a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    );

  return {
    firstUpload: sortedImports[sortedImports.length - 1] ?? null,
    lastUpload: sortedImports[0] ?? null,
    totalUploads: imports.length,
    totalQuarantined: quarantined.length,
    totalUnsupported: unsupported.length,
    manualReclassifications: reclassified.length,
  };
}

function runStatusTextClass(
  tone: "ok" | "warn" | "error" | "neutral",
): string {
  if (tone === "ok") return "text-[var(--color-success)]";
  if (tone === "warn") return "text-[var(--color-warning)]";
  if (tone === "error") return "text-[var(--color-error)]";
  return "text-[var(--text-secondary)]";
}

function progressBarClass(status: RunStatus | undefined): string {
  if (status === "failed") return "bg-[var(--color-error)]";
  if (status === "completed") return "bg-[var(--color-success)]";
  if (status === "completed_with_errors") return "bg-[var(--color-warning)]";
  return "bg-[var(--accent-primary)]";
}

function isTerminalRunStatus(status: RunStatus | null | undefined): boolean {
  return (
    status === "completed" ||
    status === "completed_with_errors" ||
    status === "failed"
  );
}

// ---------------------------------------------------------------------------
// KpiCard
// ── value: text-sm (было text-xl — слишком крупно для плотного UI)
// ── px/py чуть компактнее
// ---------------------------------------------------------------------------

const KpiCard: React.FC<{
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: "default" | "ok" | "warn" | "error";
}> = ({ label, value, sub, tone = "default" }) => {
  const valueClass =
    tone === "ok"
      ? "text-[var(--color-success)]"
      : tone === "warn"
        ? "text-[var(--color-warning)]"
        : tone === "error"
          ? "text-[var(--color-error)]"
          : "text-[var(--text-primary)]";

  return (
    <div className="flex min-w-0 flex-col gap-0.5 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3 shadow-sm">
      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
        {label}
      </p>
      {/* ↓ было text-xl → text-sm: значение читается чётко, но не доминирует */}
      <p className={`truncate text-sm font-semibold tabular-nums leading-5 ${valueClass}`}>
        {value}
      </p>
      {sub && (
        <p className="truncate text-[10px] leading-4 text-[var(--text-muted)]">
          {sub}
        </p>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// ProjectKpiRow
// ---------------------------------------------------------------------------

const ProjectKpiRow: React.FC<{
  deal: Deal;
  currentRunId?: string | null;
  documentsCount: number;
}> = ({ deal, currentRunId, documentsCount }) => {
  const runId = currentRunId ?? null;
  const { data: run } = useRun(runId, false);
  const qc = useQueryClient();

  const { lastEvent } = useSSEProgress(runId, {
    enabled: !!runId && !isTerminalRunStatus(run?.status),
  });

  const lastEventStatus = lastEvent?.status;
  React.useEffect(() => {
    if (!runId || !isTerminalRunStatus(lastEventStatus as RunStatus)) return;
    void qc.invalidateQueries({ queryKey: runKeys.detail(runId, false) });
    void qc.invalidateQueries({ queryKey: runKeys.detail(runId, true) });
  }, [runId, lastEventStatus, qc]);

  const sseCompleted =
    lastEvent?.completed_checks ?? lastEvent?.completed ?? null;
  const sseTotal = lastEvent?.total_checks ?? lastEvent?.total ?? null;
  const effectiveCompleted = sseCompleted ?? run?.completed_checks ?? 0;
  const effectiveTotal = sseTotal ?? run?.total_checks ?? 0;
  const effectiveStatus = (lastEvent?.status ?? run?.status) as
    | RunStatus
    | undefined;

  const percent =
    effectiveTotal > 0
      ? Math.round((effectiveCompleted / effectiveTotal) * 100)
      : 0;

  const statusLabel = effectiveStatus
    ? (RUN_STATUS_CONFIG[effectiveStatus]?.label ?? effectiveStatus)
    : "Не запускался";

  const statusTone: "ok" | "warn" | "error" | "neutral" = (() => {
    if (effectiveStatus === "completed") return "ok";
    if (effectiveStatus === "completed_with_errors") return "warn";
    if (effectiveStatus === "failed") return "error";
    return "neutral";
  })();

  const failedDocs = run?.failed_docs_count ?? 0;
  const quarantineDocs = run?.quarantine_docs_count ?? 0;

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <KpiCard
          label="Документов"
          value={documentsCount > 0 ? documentsCount : "—"}
          sub={documentsCount > 0 ? "В проекте" : "Не загружены"}
        />
        <KpiCard
          label="Статус анализа"
          value={statusLabel}
          sub={
            effectiveTotal > 0
              ? `${effectiveCompleted} / ${effectiveTotal} проверок`
              : "Нет данных"
          }
          tone={
            statusTone === "neutral"
              ? "default"
              : (statusTone as "ok" | "warn" | "error")
          }
        />
        <KpiCard
          label="Последний анализ"
          value={
            run?.completed_at ?? run?.started_at
              ? formatDateShort(run.completed_at ?? run.started_at)
              : "—"
          }
          sub={deal.created_at ? `Создан ${formatDate(deal.created_at)}` : undefined}
        />
        <KpiCard
          label="Проблемных файлов"
          value={
            failedDocs + quarantineDocs > 0
              ? failedDocs + quarantineDocs
              : run
                ? "0"
                : "—"
          }
          sub={
            failedDocs + quarantineDocs > 0
              ? `Ошибок: ${failedDocs} · Карантин: ${quarantineDocs}`
              : run
                ? "Всё в порядке"
                : "После анализа"
          }
          tone={
            failedDocs + quarantineDocs > 0
              ? failedDocs > 0
                ? "error"
                : "warn"
              : "default"
          }
        />
      </div>

      {effectiveTotal > 0 && (
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-2.5 shadow-sm">
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              Прогресс анализа
            </span>
            <span className="text-[10px] font-semibold tabular-nums text-[var(--text-primary)]">
              {percent}%
            </span>
          </div>
          <div className="h-1 w-full overflow-hidden rounded-full bg-[var(--bg-elevated-soft)]">
            <div
              className={`h-1 rounded-full transition-all duration-500 ease-out ${progressBarClass(effectiveStatus)}`}
              style={{ width: `${Math.min(100, percent)}%` }}
            />
          </div>
          {(effectiveStatus === "failed" ||
            effectiveStatus === "completed_with_errors") && (
            <p
              className={`mt-1 text-[10px] font-medium ${runStatusTextClass(
                effectiveStatus === "failed" ? "error" : "warn",
              )}`}
            >
              {effectiveStatus === "failed"
                ? "Анализ завершился с ошибкой."
                : "Анализ завершён, но есть документы с ошибками."}
            </p>
          )}
        </div>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// TimelineEvent
// ---------------------------------------------------------------------------

const TimelineEvent: React.FC<{
  icon: string;
  label: string;
  date?: string;
  children?: React.ReactNode;
}> = ({ icon, label, date, children }) => (
  <li className="relative flex gap-3">
    <span className="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-xs">
      {icon}
    </span>
    <div className="min-w-0 pt-0.5">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <span className="text-xs font-medium text-[var(--text-primary)]">
          {label}
        </span>
        {date && (
          <span className="text-[10px] text-[var(--text-muted)]">{date}</span>
        )}
      </div>
      {children}
    </div>
  </li>
);

// ---------------------------------------------------------------------------
// DealInfoCard
// ── textarea: max-h-40 + overflow-y-auto — при большом тексте скролл внутри
// ── блок не растягивается бесконечно
// ---------------------------------------------------------------------------

const DealInfoCard: React.FC<{
  deal: Deal;
  projectSummary: string;
  isSaving: boolean;
  isDirty: boolean;
  onChangeSummary: (value: string) => void;
  onSaveSummary: () => void;
}> = ({ deal, projectSummary, isSaving, isDirty, onChangeSummary, onSaveSummary }) => (
  <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
    <div className="px-5">
      <div className="flex items-center justify-between gap-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">
            О проекте
          </h2>
          <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
            Краткое описание для рабочей команды
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={onSaveSummary}
          isLoading={isSaving}
          disabled={isSaving || !isDirty}
        >
          Сохранить
        </Button>
      </div>
      <div className="border-t border-[var(--border-subtle)]" />
    </div>
    <div className="px-5 py-4">
      <textarea
        id={`deal-summary-${deal.id}`}
        value={projectSummary}
        onChange={(e) => onChangeSummary(e.target.value)}
        rows={6}
        placeholder="Например: продажа группы компаний, buy-side DD, корпоративный блок, ключевые договоры и IP..."
        className="w-full resize-none overflow-y-auto rounded-xl border border-[var(--border)] bg-[var(--bg-base)] px-4 py-3 text-sm leading-6 text-[var(--text-primary)] outline-none transition placeholder:text-[var(--text-muted)] focus:border-[var(--accent-primary)]"
        style={{ minHeight: "9rem", maxHeight: "16rem" }}
      />
    </div>
  </section>
);

// ---------------------------------------------------------------------------
// ActivitySummarySection
//
// Ключевые изменения по сравнению с предыдущей версией:
//
// 1. Враппер-grid больше НЕ имеет md:max-h-* и md:overflow-hidden —
//    блок растёт до естественной высоты содержимого.
//
// 2. Каждая колонка имеет max-h-[22rem] и overflow-y-auto — скролл
//    изолирован внутри колонки, не «вылезает» из карточки.
//
// 3. Секция получает pb-5 снизу — стандартный отступ от нижней границы.
// ---------------------------------------------------------------------------

const ActivitySummarySection: React.FC<{
  deal: Deal;
  currentRunId?: string | null;
  documentsCount?: number;
}> = ({ deal, currentRunId, documentsCount }) => {
  const { data: allRuns } = useDealRuns(deal.id, false);
  const { data: currentRun } = useRun(currentRunId ?? null, false);
  const { data: auditPage } = useAuditLog(deal.id, { per_page: 50 });

  const auditEntries = auditPage?.items ?? [];
  const auditAgg = buildProjectTimelineFromAudit(auditEntries);

  const firstRun = React.useMemo(() => {
    if (!allRuns || allRuns.length === 0) return null;
    const runsWithStart = allRuns.filter((run) => !!run.started_at);
    if (runsWithStart.length === 0) return null;
    return runsWithStart
      .slice()
      .sort(
        (a, b) =>
          new Date(a.started_at!).getTime() - new Date(b.started_at!).getTime(),
      )[0];
  }, [allRuns]);

  const lastRunDate = currentRun?.completed_at ?? currentRun?.started_at ?? null;

  const lastRunStatusLabel = (() => {
    const s = currentRun?.status;
    if (!s) return null;
    if (s === "completed") return { text: "Завершён успешно", tone: "ok" as const };
    if (s === "completed_with_errors") return { text: "Завершён с ошибками", tone: "warn" as const };
    if (s === "failed") return { text: "Завершился с ошибкой", tone: "error" as const };
    if (s === "running") return { text: "Выполняется", tone: "neutral" as const };
    if (s === "pending") return { text: "В очереди", tone: "neutral" as const };
    return { text: s, tone: "neutral" as const };
  })();

  const totalChecks = currentRun?.total_checks ?? 0;
  const failedDocs = currentRun?.failed_docs_count ?? 0;
  const quarantineDocs = currentRun?.quarantine_docs_count ?? 0;
  const successDocs =
    totalChecks > 0 ? totalChecks - failedDocs - quarantineDocs : 0;

  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
      {/* Заголовок */}
      <div className="px-5">
        <div className="py-3">
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">
            Активность
          </h2>
          <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
            Документы · Контрагенты · Имущество
          </p>
        </div>
        <div className="border-t border-[var(--border-subtle)]" />
      </div>

      {/*
        grid-враппер: НЕТ max-h и overflow-hidden на уровне враппера.
        Высота определяется содержимым колонок.
        pb-5 — стандартный отступ снизу внутри карточки.
      */}
      <div className="grid grid-cols-1 divide-y divide-[var(--border-subtle)] px-5 pb-5 pt-4 md:grid-cols-3 md:divide-x md:divide-y-0">

        {/* ── Колонка 1: Документы ── */}
        <div className="flex flex-col pb-5 md:pb-0 md:pr-5">
          <p className="mb-3 shrink-0 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Документы
          </p>
          {/*
            max-h-[22rem] + overflow-y-auto: если событий много —
            колонка ограничена по высоте и скроллится внутри себя.
            Все три колонки имеют одинаковый max-h, поэтому блок
            выглядит выровненным по высоте.
          */}
          <ol className="max-h-[22rem] space-y-3 overflow-y-auto pr-1">
            <TimelineEvent
              icon="🗂"
              label="Проект создан"
              date={formatDate(deal.created_at)}
            />

            {auditAgg.firstUpload && (
              <TimelineEvent
                icon="📤"
                label="Первая загрузка"
                date={formatDateShort(auditAgg.firstUpload.created_at)}
              >
                <p className="mt-0.5 text-[10px] leading-4 text-[var(--text-secondary)]">
                  Через импорт-пайплайн.
                </p>
              </TimelineEvent>
            )}

            {auditAgg.lastUpload && (
              <TimelineEvent
                icon="📥"
                label={
                  auditAgg.totalUploads > 1
                    ? `Последняя загрузка (${auditAgg.totalUploads})`
                    : "Загрузка документов"
                }
                date={formatDateShort(auditAgg.lastUpload.created_at)}
              />
            )}

            {(auditAgg.totalQuarantined > 0 || auditAgg.totalUnsupported > 0) && (
              <TimelineEvent icon="⚠️" label="Проблемные файлы">
                <p className="mt-0.5 text-[10px] leading-4 text-[var(--text-secondary)]">
                  Карантин: {auditAgg.totalQuarantined}
                  {auditAgg.totalUnsupported > 0 && (
                    <> · неподдерживаемых: {auditAgg.totalUnsupported}</>
                  )}
                </p>
              </TimelineEvent>
            )}

            {typeof documentsCount === "number" && (
              <TimelineEvent
                icon="📚"
                label={
                  documentsCount > 0
                    ? `В проекте: ${documentsCount} докум.`
                    : "Документы не загружены"
                }
              />
            )}

            {firstRun?.started_at && (
              <TimelineEvent
                icon="🚀"
                label="Первый анализ"
                date={formatDateShort(firstRun.started_at)}
              />
            )}

            {currentRun && (
              <TimelineEvent
                icon={
                  currentRun.status === "completed"
                    ? "✅"
                    : currentRun.status === "completed_with_errors"
                      ? "⚠️"
                      : currentRun.status === "failed"
                        ? "❌"
                        : "🔄"
                }
                label="Последний анализ"
                date={lastRunDate ? formatDateShort(lastRunDate) : "—"}
              >
                {totalChecks > 0 && (
                  <div className="mt-0.5 flex flex-wrap gap-x-2 gap-y-0.5 text-[10px]">
                    <span className="text-[var(--color-success)]">
                      проверено: {totalChecks}
                    </span>
                    {successDocs > 0 && (
                      <span className="text-[var(--color-success)]">
                        успешно: {successDocs}
                      </span>
                    )}
                    {failedDocs > 0 && (
                      <span className="text-[var(--color-error)]">
                        ошибок: {failedDocs}
                      </span>
                    )}
                    {quarantineDocs > 0 && (
                      <span className="text-[var(--color-warning)]">
                        карантин: {quarantineDocs}
                      </span>
                    )}
                  </div>
                )}
                {lastRunStatusLabel && (
                  <p
                    className={`mt-0.5 text-[10px] font-medium ${runStatusTextClass(lastRunStatusLabel.tone)}`}
                  >
                    {lastRunStatusLabel.text}
                  </p>
                )}
              </TimelineEvent>
            )}
          </ol>
        </div>

        {/* ── Колонка 2: Контрагенты ── */}
        <div className="flex flex-col py-5 md:px-5 md:py-0">
          <p className="mb-3 shrink-0 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Контрагенты
          </p>
          <div className="max-h-[22rem] space-y-3 overflow-y-auto pr-1">
            <div className="flex items-center gap-2.5">
              <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-xs">
                🏢
              </span>
              <div className="h-2.5 w-36 animate-pulse rounded bg-[var(--bg-elevated-soft)]" />
            </div>
            <div className="flex items-center gap-2.5">
              <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-xs">
                👤
              </span>
              <div className="h-2.5 w-28 animate-pulse rounded bg-[var(--bg-elevated-soft)]" />
            </div>
            <div className="flex items-center gap-2.5">
              <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-xs">
                🔗
              </span>
              <div className="h-2.5 w-32 animate-pulse rounded bg-[var(--bg-elevated-soft)]" />
            </div>

            <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] px-3 py-2.5">
              <p className="text-[11px] font-medium text-[var(--text-primary)]">
                Раздел в разработке
              </p>
              <p className="mt-0.5 text-[10px] leading-[1.6] text-[var(--text-secondary)]">
                После запуска анализа здесь появятся выявленные контрагенты
                с типами и уровнями риска.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-xl border border-[var(--border)] px-3 py-2">
                <p className="text-[10px] text-[var(--text-muted)]">Юрлиц</p>
                <p className="mt-0.5 text-sm font-semibold tabular-nums text-[var(--text-primary)]">
                  —
                </p>
              </div>
              <div className="rounded-xl border border-[var(--border)] px-3 py-2">
                <p className="text-[10px] text-[var(--text-muted)]">Физлиц</p>
                <p className="mt-0.5 text-sm font-semibold tabular-nums text-[var(--text-primary)]">
                  —
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* ── Колонка 3: Имущество ── */}
        <div className="flex flex-col pt-5 md:pl-5 md:pt-0">
          <p className="mb-3 shrink-0 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Имущество
          </p>
          <div className="max-h-[22rem] space-y-3 overflow-y-auto pr-1">
            <div className="flex items-center gap-2.5">
              <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-xs">
                🏗
              </span>
              <div className="h-2.5 w-40 animate-pulse rounded bg-[var(--bg-elevated-soft)]" />
            </div>
            <div className="flex items-center gap-2.5">
              <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-xs">
                📍
              </span>
              <div className="h-2.5 w-32 animate-pulse rounded bg-[var(--bg-elevated-soft)]" />
            </div>
            <div className="flex items-center gap-2.5">
              <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-xs">
                ⚖️
              </span>
              <div className="h-2.5 w-36 animate-pulse rounded bg-[var(--bg-elevated-soft)]" />
            </div>

            <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] px-3 py-2.5">
              <p className="text-[11px] font-medium text-[var(--text-primary)]">
                Раздел в разработке
              </p>
              <p className="mt-0.5 text-[10px] leading-[1.6] text-[var(--text-secondary)]">
                После запуска анализа здесь появятся объекты недвижимости
                с адресами, кадастровыми номерами и статусом обременений.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-xl border border-[var(--border)] px-3 py-2">
                <p className="text-[10px] text-[var(--text-muted)]">Объектов</p>
                <p className="mt-0.5 text-sm font-semibold tabular-nums text-[var(--text-primary)]">
                  —
                </p>
              </div>
              <div className="rounded-xl border border-[var(--border)] px-3 py-2">
                <p className="text-[10px] text-[var(--text-muted)]">
                  С обременением
                </p>
                <p className="mt-0.5 text-sm font-semibold tabular-nums text-[var(--text-primary)]">
                  —
                </p>
              </div>
            </div>
          </div>
        </div>

      </div>
    </section>
  );
};

// ---------------------------------------------------------------------------
// OverviewTab — без изменений в логике
// ---------------------------------------------------------------------------

const OverviewTab: React.FC<OverviewTabProps> = ({ deal, currentRunId }) => {
  const qc = useQueryClient();

  const { data: currentRun } = useRun(currentRunId ?? null, false);
  const { data: documentsPage } = useDocuments(deal.id, 1);
  const documentsCount = documentsPage?.total ?? 0;
  const { canStartRun, canUploadDocuments } = useDealPermissions(deal.id);

  const startRun = useStartRun(deal.id);
  const updateDeal = useUpdateDeal(deal.id);
  const setPrimaryLanguage = useSetPrimaryLanguage(deal.id);

  const [isLaunchPanelOpen, setIsLaunchPanelOpen] = React.useState(false);
  const [checksMode, setChecksMode] =
    React.useState<ChecksMode>("global_and_doc_type");
  const [forceReclassify, setForceReclassify] = React.useState(false);
  const [hasRestartedAfterReclass, setHasRestartedAfterReclass] =
    React.useState(false);
  const [projectSummary, setProjectSummary] = React.useState(
    deal.summary ?? "",
  );
  const [dealPatch, setDealPatch] = React.useState<Partial<Deal>>({});

  const overviewRef = React.useRef<HTMLDivElement | null>(null);
  const railRef = React.useRef<HTMLDivElement | null>(null);
  const [overlayWidth, setOverlayWidth] = React.useState<number | null>(null);

  React.useLayoutEffect(() => {
    const overviewEl = overviewRef.current;
    const railEl = railRef.current;
    if (!overviewEl || !railEl) return;

    const update = () => {
      const overviewRect = overviewEl.getBoundingClientRect();
      const railRect = railEl.getBoundingClientRect();
      const styles = window.getComputedStyle(overviewEl);
      const gap = parseFloat(styles.columnGap || styles.gap || "0") || 0;
      const width = Math.max(0, overviewRect.width - railRect.width - gap);
      setOverlayWidth(width > 0 ? width : null);
    };

    update();

    const ro = new ResizeObserver(() => update());
    ro.observe(overviewEl);
    ro.observe(railEl);
    window.addEventListener("resize", update);

    return () => {
      ro.disconnect();
      window.removeEventListener("resize", update);
    };
  }, []);

  const dealLanguagesKey = JSON.stringify(deal.languages ?? []);

  React.useEffect(() => {
    setProjectSummary(deal.summary ?? "");
    setDealPatch({});
  }, [
    deal.id,
    deal.summary,
    deal.playbook_version_id,
    deal.primary_language,
    deal.language_discovery_status,
    dealLanguagesKey,
  ]);

  React.useEffect(() => {
    if (!isLaunchPanelOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsLaunchPanelOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isLaunchPanelOpen]);

  const effectiveDeal: Deal = { ...deal, ...dealPatch };

  const normalizedOriginalSummary = (deal.summary ?? "").trim();
  const normalizedDraftSummary = projectSummary.trim();
  const isSummaryDirty = normalizedDraftSummary !== normalizedOriginalSummary;

  const showReclassBanner =
    effectiveDeal.has_pending_manual_reclassifications &&
    (!!currentRun || !hasRestartedAfterReclass);

  const hasDocuments = documentsCount > 0;

  const discoveryStatus = normalizeDiscoveryStatus(
    effectiveDeal.language_discovery_status,
  );

  const isLanguageDiscoveryBlocking =
    discoveryStatus === "pending" || discoveryStatus === "processing";

  const canLaunchRun =
    canStartRun &&
    hasDocuments &&
    !!effectiveDeal.playbook_version_id &&
    !!effectiveDeal.primary_language &&
    !isLanguageDiscoveryBlocking &&
    !startRun.isPending &&
    !updateDeal.isPending &&
    !setPrimaryLanguage.isPending;

  const isSubmitting =
    startRun.isPending || updateDeal.isPending || setPrimaryLanguage.isPending;

  const handleOpenLaunchPanel = React.useCallback(() => {
    setIsLaunchPanelOpen(true);
  }, []);

  const handleCloseLaunchPanel = React.useCallback(() => {
    setIsLaunchPanelOpen(false);
  }, []);

  const handlePrimaryLanguageChange = React.useCallback(
    (value: string) => {
      const normalizedValue = normalizeLang(value) || null;
      setDealPatch((prev) => ({ ...prev, primary_language: normalizedValue }));
      setPrimaryLanguage.mutate(
        { primary_language: normalizedValue },
        {
          onError: () => {
            setDealPatch((prev) => ({
              ...prev,
              primary_language: deal.primary_language ?? null,
            }));
          },
        },
      );
    },
    [deal.primary_language, setPrimaryLanguage],
  );

  const handleSaveSummary = React.useCallback(() => {
    if (!isSummaryDirty) return;
    updateDeal.mutate({
      summary:
        normalizedDraftSummary.length > 0 ? normalizedDraftSummary : null,
    });
  }, [isSummaryDirty, normalizedDraftSummary, updateDeal]);

  const handleStartRun = React.useCallback(() => {
    if (!canLaunchRun) return;
    startRun.mutate(
      {
        profile: "core",
        checks_mode: checksMode,
        force_reclassify: forceReclassify,
      },
      {
        onSuccess: async (run) => {
          setHasRestartedAfterReclass(true);
          setForceReclassify(false);
          setIsLaunchPanelOpen(false);
          await Promise.all([
            qc.invalidateQueries({ queryKey: runKeys.detail(run.id, true) }),
            qc.invalidateQueries({ queryKey: runKeys.detail(run.id, false) }),
            qc.invalidateQueries({
              queryKey: runKeys.classificationReport(run.id),
            }),
            qc.invalidateQueries({ queryKey: ["deal", deal.id] }),
            qc.invalidateQueries({ queryKey: runKeys.history(deal.id, false) }),
            qc.invalidateQueries({ queryKey: runKeys.history(deal.id, true) }),
          ]);
        },
      },
    );
  }, [canLaunchRun, checksMode, deal.id, forceReclassify, qc, startRun]);

  const handleDealPatched = React.useCallback(
    async (patch?: Partial<Deal>) => {
      if (patch && Object.keys(patch).length > 0) {
        setDealPatch((prev) => ({ ...prev, ...patch }));
      }
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["deal", deal.id] }),
      ]);
    },
    [deal.id, qc],
  );

  return (
    <div
      ref={overviewRef}
      className="relative grid gap-4 xl:grid-cols-[minmax(0,2.2fr)_360px]"
    >
      <div className="min-w-0 space-y-4">
        <ProjectKpiRow
          deal={effectiveDeal}
          currentRunId={currentRunId}
          documentsCount={documentsCount}
        />

        <DealInfoCard
          deal={effectiveDeal}
          projectSummary={projectSummary}
          isSaving={updateDeal.isPending}
          isDirty={isSummaryDirty}
          onChangeSummary={setProjectSummary}
          onSaveSummary={handleSaveSummary}
        />

        <ActivitySummarySection
          deal={effectiveDeal}
          currentRunId={currentRunId}
          documentsCount={documentsCount}
        />
      </div>

      <div ref={railRef} className="relative hidden xl:block px-1 pb-2">
        <AnalysisActionsPanel
          deal={effectiveDeal}
          hasCurrentRun={!!currentRun}
          canStartRun={canLaunchRun}
          onOpenRunPanel={handleOpenLaunchPanel}
          showReclassBanner={showReclassBanner}
        />

        {overlayWidth !== null && (
          <LaunchWideOverlay
            open={isLaunchPanelOpen}
            overlayWidth={overlayWidth}
            deal={effectiveDeal}
            documentsCount={documentsCount}
            checksMode={checksMode}
            onChecksModeChange={setChecksMode}
            forceReclassify={forceReclassify}
            onForceReclassifyChange={setForceReclassify}
            canStartRun={canLaunchRun}
            canUploadDocuments={canUploadDocuments}
            isSubmitting={isSubmitting}
            onPrimaryLanguageChange={handlePrimaryLanguageChange}
            onSubmit={handleStartRun}
            onClose={handleCloseLaunchPanel}
            onDealPatched={handleDealPatched}
          />
        )}
      </div>

      <div className="xl:hidden">
        <AnalysisActionsPanel
          deal={effectiveDeal}
          hasCurrentRun={!!currentRun}
          canStartRun={canLaunchRun}
          onOpenRunPanel={handleOpenLaunchPanel}
          showReclassBanner={showReclassBanner}
        />
      </div>
    </div>
  );
};

export default OverviewTab;




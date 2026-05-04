// =============================================================
// src/pages/tabs/OverviewTab.tsx
// Вкладка "Обзор" сделки.
//
// Левая колонка:
//   1. Карточка "О проекте" — описание, контрагент, контакт,
//      юрисдикция, конфигурация анализа (без action-кнопок).
//   2. Карточка "Хроника проекта" — ключевые события от
//      создания до последнего анализа.
//   3. RunProgressCard — статус / прогресс текущего / последнего
//      запуска.
//
// Правая колонка:
//   AnalysisActionsPanel + LaunchOverlayPanel.
// =============================================================

import React from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { Deal, DealDetail, RunStatus } from "../../types";
import { useRun, useStartRun } from "../../api/runs";
import { useDeal, useSetPrimaryLanguage } from "../../api/deals";
import { useDocumentsCount } from "../../api/documents";
import { resultApi } from "../../api/results";
import { useDealPermissions } from "../../hooks/usePermissions";
import { useSSEProgress } from "../../hooks/useSSE";
import { RUN_STATUS_CONFIG } from "../../utils/statusConfig";
import Button from "../../components/ui/Button";
import { useAuditLog } from "../../api/audit";
import type { AuditLogEntry } from "../../types";

type ChecksMode = "global_only" | "doc_type_only" | "global_and_doc_type";

interface OverviewTabProps {
  deal: Deal;
  latestRunId?: string | null;
  onOpenModelConfig?: () => void;
}

const SECONDARY_ACTION_BUTTON_CLASS =
  "w-[220px] shrink-0 justify-center whitespace-nowrap text-sm font-semibold";

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

function formatDateShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const InfoRow: React.FC<{
  label: string;
  children: React.ReactNode;
  tone?: "ok" | "warn" | "error" | "neutral";
}> = ({ label, children, tone = "neutral" }) => {
  const valueClass =
    tone === "ok"
      ? "text-emerald-600"
      : tone === "warn"
      ? "text-amber-600"
      : tone === "error"
      ? "text-rose-600"
      : "text-[var(--text-primary)]";

  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
        {label}
      </span>
      <span className={`text-sm leading-5 ${valueClass}`}>{children}</span>
    </div>
  );
};

const StatusRow: React.FC<{
  label: string;
  value: string;
  tone?: "ok" | "warn" | "neutral";
}> = ({ label, value, tone = "neutral" }) => {
  const toneClass =
    tone === "ok"
      ? "text-emerald-600"
      : tone === "warn"
      ? "text-amber-600"
      : "text-[var(--text-primary)]";

  return (
    <div className="flex flex-col gap-1 rounded-xl border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-2">
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
        {label}
      </p>
      <p className={`text-sm ${toneClass}`}>{value}</p>
    </div>
  );
};

const CardShell: React.FC<{
  title: string;
  eyebrow?: string;
  children: React.ReactNode;
  rightSlot?: React.ReactNode;
}> = ({ title, eyebrow, children, rightSlot }) => (
  <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
    <div className="flex items-start justify-between gap-4 border-b border-[var(--border-soft)] px-5 py-4">
      <div className="min-w-0">
        {eyebrow && (
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            {eyebrow}
          </p>
        )}
        <h2 className="text-base font-semibold text-[var(--text-primary)]">
          {title}
        </h2>
      </div>
      {rightSlot}
    </div>
    <div className="px-5 py-4">{children}</div>
  </section>
);

const DealInfoCard: React.FC<{
  deal: Deal;
  detail: DealDetail | null | undefined;
}> = ({ deal, detail }) => {
  const description = detail?.description ?? null;
  const counterparty = detail?.counterparty ?? null;
  const contactPerson = deal.metadata_?.contact_person ?? null;

  return (
    <CardShell
      eyebrow="Проект"
      title={deal.name}
      rightSlot={
        <div className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-1 text-[11px] font-medium text-[var(--text-secondary)]">
          {deal.status}
        </div>
      }
    >
      <div className="space-y-4">
        <div className="flex flex-wrap gap-2 text-[12px] text-[var(--text-secondary)]">
          {deal.deal_type && (
            <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-2.5 py-1">
              Тип: {deal.deal_type}
            </span>
          )}
          {deal.jurisdiction && (
            <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-2.5 py-1">
              Юрисдикция: {deal.jurisdiction}
            </span>
          )}
        </div>

        {description && (
          <div className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-4 py-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
              Описание
            </p>
            <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
              {description}
            </p>
          </div>
        )}

        {(counterparty || contactPerson || deal.jurisdiction) && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {counterparty && (
              <InfoRow label="Контрагент">{counterparty}</InfoRow>
            )}
            {contactPerson && (
              <InfoRow label="Контактное лицо">{contactPerson}</InfoRow>
            )}
            {deal.jurisdiction && (
              <InfoRow label="Юрисдикция">{deal.jurisdiction}</InfoRow>
            )}
          </div>
        )}
      </div>
    </CardShell>
  );
};

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
        new Date(b.created_at).getTime() -
        new Date(a.created_at).getTime(),
    );

  const lastUpload = sortedImports[0] ?? null;
  const firstUpload = sortedImports[sortedImports.length - 1] ?? null;

  const totalImported = imports.reduce((sum, e) => {
    const d = (e.details ?? {}) as Record<string, unknown>;
    const importedCount =
      typeof d.imported_count === "number" ? d.imported_count : 0;
    return sum + importedCount;
  }, 0);

  return {
    firstUpload,
    lastUpload,
    totalUploads: imports.length,
    totalImported,
    totalQuarantined: quarantined.length,
    totalUnsupported: unsupported.length,
    manualReclassifications: reclassified.length,
  };
}

const TimelineEvent: React.FC<{
  icon: string;
  label: string;
  date?: string;
  children?: React.ReactNode;
}> = ({ icon, label, date, children }) => (
  <li className="relative flex gap-3">
    <span className="mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] text-sm">
      {icon}
    </span>
    <div className="min-w-0 pt-0.5">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="text-sm font-medium text-[var(--text-primary)]">
          {label}
        </span>
        {date && (
          <span className="text-[11px] text-[var(--text-muted)]">{date}</span>
        )}
      </div>
      {children}
    </div>
  </li>
);

const ProjectTimelineCard: React.FC<{
  deal: Deal;
  latestRunId?: string | null;
  documentsCount?: number;
}> = ({ deal, latestRunId, documentsCount }) => {
  const { data: allRuns } = useQuery({
    queryKey: ["all-runs", deal.id],
    queryFn: () => resultApi.listRuns(deal.id, false),
    enabled: !!deal.id,
    staleTime: 2 * 60_000,
  });

  const { data: latestRun } = useRun(latestRunId ?? null, false);

  const { data: auditPage } = useAuditLog(deal.id, { per_page: 50 });
  const auditEntries = auditPage?.items ?? [];
  const auditAgg = buildProjectTimelineFromAudit(auditEntries);

  const totalRuns = allRuns?.length ?? 0;
  const firstRun =
    allRuns && allRuns.length > 0 ? allRuns[allRuns.length - 1] : null;

  const lastRunDate = latestRun?.completed_at ?? latestRun?.started_at ?? null;

  const lastRunStatusLabel = (() => {
    const s = latestRun?.status;
    if (!s) return null;
    if (s === "completed") return { text: "Завершён успешно", tone: "ok" };
    if (s === "completed_with_errors") {
      return { text: "Завершён с ошибками", tone: "warn" };
    }
    if (s === "failed") return { text: "Завершился с ошибкой", tone: "error" };
    if (s === "running") return { text: "Выполняется", tone: "neutral" };
    if (s === "pending") return { text: "В очереди", tone: "neutral" };
    return { text: s, tone: "neutral" };
  })();

  const totalChecks = latestRun?.total_checks ?? 0;
  const failedDocs = latestRun?.failed_docs_count ?? 0;
  const quarantineDocs = latestRun?.quarantine_docs_count ?? 0;
  const successDocs =
    totalChecks > 0 ? totalChecks - failedDocs - quarantineDocs : 0;

  if (!deal.created_at && !latestRunId) {
    return null;
  }

  return (
    <CardShell eyebrow="Активность" title="Хроника проекта">
      <ol className="space-y-4">
        <TimelineEvent
          icon="🗂"
          label="Проект создан"
          date={formatDate(deal.created_at)}
        />

        {auditAgg.firstUpload && (
          <TimelineEvent
            icon="📤"
            label="Первая загрузка документов"
            date={formatDateShort(auditAgg.firstUpload.created_at)}
          >
            <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
              Через импорт‑пайплайн началась работа с документами.
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
          >
            {(() => {
              const d = (auditAgg.lastUpload.details ?? {}) as Record<
                string,
                unknown
              >;
              const totalFiles =
                typeof d.total_files === "number" ? d.total_files : undefined;
              const importedCount =
                typeof d.imported_count === "number"
                  ? d.imported_count
                  : undefined;
              const quarantineCount =
                typeof d.quarantine_count === "number"
                  ? d.quarantine_count
                  : undefined;
              const duplicateCount =
                typeof d.duplicate_count === "number"
                  ? d.duplicate_count
                  : undefined;

              return (
                <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
                  {typeof totalFiles === "number" && (
                    <>
                      Загрузка: {totalFiles} файл(ов)
                      {" · "}
                    </>
                  )}
                  {typeof importedCount === "number" && (
                    <>принято {importedCount}</>
                  )}
                  {typeof quarantineCount === "number" &&
                    quarantineCount > 0 && (
                      <> · карантин {quarantineCount}</>
                    )}
                  {typeof duplicateCount === "number" && duplicateCount > 0 && (
                    <> · дубликатов {duplicateCount}</>
                  )}
                </p>
              );
            })()}
          </TimelineEvent>
        )}

        {(auditAgg.totalQuarantined > 0 || auditAgg.totalUnsupported > 0) && (
          <TimelineEvent icon="⚠️" label="Проблемные файлы при загрузках">
            <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
              В карантине: {auditAgg.totalQuarantined}
              {auditAgg.totalUnsupported > 0 && (
                <> · неподдерживаемых форматов: {auditAgg.totalUnsupported}</>
              )}
            </p>
          </TimelineEvent>
        )}

        {typeof documentsCount === "number" && (
          <TimelineEvent
            icon="📚"
            label={
              documentsCount > 0
                ? "Документы в проекте"
                : "Документы ещё не загружены"
            }
          >
            <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
              Сейчас в проекте {documentsCount} документ(ов).
            </p>
          </TimelineEvent>
        )}

        {firstRun && firstRun.started_at && (
          <TimelineEvent
            icon="🚀"
            label="Первый анализ проведён"
            date={formatDateShort(firstRun.started_at)}
          />
        )}

        {latestRun && (
          <TimelineEvent
            icon={
              latestRun.status === "completed"
                ? "✅"
                : latestRun.status === "completed_with_errors"
                ? "⚠️"
                : latestRun.status === "failed"
                ? "❌"
                : "🔄"
            }
            label="Последний анализ"
            date={lastRunDate ? formatDateShort(lastRunDate) : "—"}
          >
            {totalChecks > 0 && (
              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[12px]">
                <span className="text-emerald-600">проверено: {totalChecks}</span>
                {successDocs > 0 && (
                  <span className="text-emerald-500">успешно: {successDocs}</span>
                )}
                {failedDocs > 0 && (
                  <span className="text-rose-600">с ошибкой: {failedDocs}</span>
                )}
                {quarantineDocs > 0 && (
                  <span className="text-amber-600">
                    карантин: {quarantineDocs}
                  </span>
                )}
              </div>
            )}

            {lastRunStatusLabel && (
              <p
                className={`mt-1 text-[12px] font-medium ${
                  lastRunStatusLabel.tone === "ok"
                    ? "text-emerald-600"
                    : lastRunStatusLabel.tone === "warn"
                    ? "text-amber-600"
                    : lastRunStatusLabel.tone === "error"
                    ? "text-rose-600"
                    : "text-[var(--text-secondary)]"
                }`}
              >
                {lastRunStatusLabel.text}
              </p>
            )}
          </TimelineEvent>
        )}
      </ol>

      {(totalRuns > 1 || auditAgg.manualReclassifications > 0) && (
        <div className="mt-4 flex flex-wrap gap-2">
          {totalRuns > 1 && (
            <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)]">
              Запусков анализа: {totalRuns}
            </span>
          )}
          {auditAgg.manualReclassifications > 0 && (
            <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)]">
              Ручных переклассификаций: {auditAgg.manualReclassifications}
            </span>
          )}
        </div>
      )}
    </CardShell>
  );
};

const RunProgressCard: React.FC<{
  latestRunId?: string | null;
}> = ({ latestRunId }) => {
  const runId = latestRunId ?? null;
  const { data: run, isLoading } = useRun(runId, false);
  const { lastEvent } = useSSEProgress(runId, { enabled: !!runId });

  if (!runId) {
    return (
      <CardShell eyebrow="Pipeline" title="Статус анализа">
        <p className="text-sm leading-6 text-[var(--text-secondary)]">
          Анализ ещё не запускался для этой сделки.
        </p>
      </CardShell>
    );
  }

  const effectiveCompleted =
    lastEvent?.completed_checks ?? run?.completed_checks ?? 0;
  const effectiveTotal = lastEvent?.total_checks ?? run?.total_checks ?? 0;
  const effectiveStatus = (lastEvent?.status ??
    run?.status) as RunStatus | undefined;

  const percent =
    effectiveTotal > 0
      ? Math.round((effectiveCompleted / effectiveTotal) * 100)
      : 0;

  const progressColor =
    effectiveStatus === "failed"
      ? "bg-rose-500"
      : effectiveStatus === "completed"
      ? "bg-emerald-500"
      : effectiveStatus === "completed_with_errors"
      ? "bg-amber-500"
      : "bg-[var(--accent-primary)]";

  return (
    <CardShell
      eyebrow="Pipeline"
      title="Статус анализа"
      rightSlot={
        isLoading && !run ? (
          <span className="text-[11px] text-[var(--text-muted)]">Загружаем…</span>
        ) : (
          <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-1 text-[11px] font-medium text-[var(--text-secondary)]">
            {effectiveStatus
              ? RUN_STATUS_CONFIG[effectiveStatus]?.label ?? effectiveStatus
              : "—"}
          </span>
        )
      }
    >
      {effectiveTotal > 0 ? (
        <div className="space-y-3">
          <div className="flex items-center justify-between text-[12px]">
            <span className="text-[var(--text-secondary)]">
              {effectiveCompleted} / {effectiveTotal} проверок
            </span>
            <span className="font-semibold text-[var(--text-primary)]">
              {percent}%
            </span>
          </div>

          <div className="h-2.5 w-full rounded-full bg-[var(--bg-elevated-soft)]">
            <div
              className={`h-2.5 rounded-full transition-all duration-300 ${progressColor}`}
              style={{ width: `${Math.min(100, percent)}%` }}
            />
          </div>

          {(effectiveStatus === "failed" ||
            effectiveStatus === "completed_with_errors") &&
            run && (
              <div
                className={`rounded-xl border px-3 py-2 text-[12px] leading-5 ${
                  effectiveStatus === "failed"
                    ? "border-rose-200 bg-rose-50 text-rose-700"
                    : "border-amber-200 bg-amber-50 text-amber-800"
                }`}
              >
                <p>
                  {effectiveStatus === "failed"
                    ? "Анализ завершился с ошибкой."
                    : "Анализ завершён, но есть документы с ошибками."}
                  {effectiveStatus === "completed_with_errors" && (
                    <>
                      {typeof run.failed_docs_count === "number" &&
                        run.failed_docs_count > 0 && (
                          <> Проблемных: {run.failed_docs_count}.</>
                        )}
                      {typeof run.quarantine_docs_count === "number" &&
                        run.quarantine_docs_count > 0 && (
                          <> Карантин: {run.quarantine_docs_count}.</>
                        )}
                    </>
                  )}
                  {(() => {
                    const details = run.error_details;
                    if (
                      details &&
                      typeof details === "object" &&
                      "message" in details &&
                      typeof (details as { message: unknown }).message === "string"
                    ) {
                      return (
                        <> Детали: {(details as { message: string }).message}</>
                      );
                    }
                    return null;
                  })()}
                </p>
              </div>
            )}
        </div>
      ) : (
        <p className="text-sm leading-6 text-[var(--text-secondary)]">
          Документы для анализа ещё не готовы или пайплайн не запущен.
        </p>
      )}
    </CardShell>
  );
};

const LaunchOverlayPanel: React.FC<{
  open: boolean;
  onClose: () => void;
  deal: Deal;
  latestRunId?: string | null;
  documentsCount?: number;
  checksMode: ChecksMode;
  onChecksModeChange: (value: ChecksMode) => void;
  forceReclassify: boolean;
  onForceReclassifyChange: (value: boolean) => void;
  canStartRun: boolean;
  canUploadDocuments: boolean;
  isSubmitting: boolean;
  onOpenPlaybook: () => void;
  onOpenModelConfig?: () => void;
  onOpenUpload: () => void;
  onPrimaryLanguageChange: (value: string) => void;
  onSubmit: () => void;
}> = ({
  open,
  onClose,
  deal,
  latestRunId,
  documentsCount,
  checksMode,
  onChecksModeChange,
  forceReclassify,
  onForceReclassifyChange,
  canStartRun,
  canUploadDocuments,
  isSubmitting,
  onOpenPlaybook,
  onOpenModelConfig,
  onOpenUpload,
  onPrimaryLanguageChange,
  onSubmit,
}) => {
  const documentLanguages = deal.languages ?? [];
  const hasMultipleDocumentLanguages = documentLanguages.length > 1;
  const selectedPrimaryLanguage = deal.primary_language ?? "";

  const requiresExplicitPrimaryLanguage = hasMultipleDocumentLanguages;
  const hasValidPrimaryLanguageSelection =
    !requiresExplicitPrimaryLanguage || !!selectedPrimaryLanguage;
  const hasPlaybook = !!deal.playbook_version_id;

  const canLaunchRun =
    canStartRun &&
    hasPlaybook &&
    hasValidPrimaryLanguageSelection &&
    !isSubmitting;

  const readinessLabel = !hasPlaybook
    ? "Нужно выбрать playbook, чтобы запустить анализ."
    : !hasValidPrimaryLanguageSelection
    ? "Нужно выбрать основной язык анализа."
    : "Параметры готовы к запуску анализа.";

  if (!open) return null;

  const panelContent = (
    <div className="flex max-h-[calc(100vh-7rem)] flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-xl">
      <div className="flex items-start justify-between border-b border-[var(--border-soft)] px-5 py-4">
        <div>
          <h3 className="text-base font-semibold text-[var(--text-primary)]">
            Запуск анализа
          </h3>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Проверьте параметры анализа для этой сделки.
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg p-2 text-[var(--text-muted)] transition hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)]"
          aria-label="Закрыть панель запуска"
        >
          ✕
        </button>
      </div>

      <div className="space-y-3 overflow-y-auto px-5 py-4">
        <div className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-4 py-3">
          <p className="text-xs font-semibold text-[var(--text-primary)]">
            {readinessLabel}
          </p>
          {latestRunId && (
            <p className="mt-1 text-[11px] leading-5 text-[var(--text-secondary)]">
              Последний анализ уже запускался. Новый запуск обновит результаты
              по текущим документам.
            </p>
          )}
        </div>

        <section className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-base)] p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                Документы
              </h4>
              <p className="mt-1 text-xs text-[var(--text-secondary)]">
                {typeof documentsCount === "number"
                  ? `В проект загружено ${documentsCount} документ(ов).`
                  : "Загружаем информацию о документах…"}
              </p>
              <p className="mt-1 text-[11px] text-[var(--text-muted)]">
                Для добавления новых документов используйте отдельный сценарий
                загрузки.
              </p>
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={onOpenUpload}
              disabled={!canUploadDocuments}
              className={SECONDARY_ACTION_BUTTON_CLASS}
            >
              Загрузить документы
            </Button>
          </div>
        </section>

        <section className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-base)] p-4">
          <h4 className="text-sm font-semibold text-[var(--text-primary)]">
            Режим проверки
          </h4>
          <div className="mt-3 space-y-2">
            {(
              [
                {
                  value: "global_and_doc_type",
                  title: "Playbook и типы документов",
                  hint: "Рекомендуемый режим: комбинирует глобальный playbook и типовые проверки.",
                },
                {
                  value: "global_only",
                  title: "Только Playbook",
                  hint: "Анализ только по правилам playbook без привязки к типу документа.",
                },
                {
                  value: "doc_type_only",
                  title: "Только типы документов",
                  hint: "Используются проверки, привязанные к типам документов.",
                },
              ] as { value: ChecksMode; title: string; hint: string }[]
            ).map(({ value, title, hint }) => (
              <label
                key={value}
                className={`flex cursor-pointer items-start gap-3 rounded-xl border px-3 py-3 transition ${
                  checksMode === value
                    ? "border-[var(--accent-primary)] bg-[var(--bg-elevated-soft)]"
                    : "border-[var(--border-soft)] bg-[var(--bg-card)] hover:bg-[var(--bg-elevated-soft)]"
                }`}
              >
                <input
                  type="radio"
                  className="mt-[2px]"
                  value={value}
                  checked={checksMode === value}
                  onChange={() => onChecksModeChange(value)}
                  disabled={isSubmitting || !canStartRun}
                />
                <span>
                  <span className="block text-[13px] font-medium text-[var(--text-primary)]">
                    {title}
                  </span>
                  <span className="block text-[11px] leading-5 text-[var(--text-secondary)]">
                    {hint}
                  </span>
                </span>
              </label>
            ))}
          </div>
        </section>

        <section className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-base)] p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                Playbook проекта
              </h4>
              <p className="mt-1 text-xs text-[var(--text-muted)]">
                Используется для формирования проверок и DD Grid.
              </p>
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={onOpenPlaybook}
              className={SECONDARY_ACTION_BUTTON_CLASS}
            >
              Открыть Playbook
            </Button>
          </div>
          <p className="mt-3 text-xs leading-5">
            {hasPlaybook ? (
              <span className="text-[var(--text-secondary)]">
                Playbook выбран. При необходимости вы можете изменить его перед
                запуском.
              </span>
            ) : (
              <span className="text-rose-600">
                Playbook не выбран. Нельзя запустить анализ без выбранного
                playbook.
              </span>
            )}
          </p>
        </section>

        <section className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-base)] p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                Профиль модели
              </h4>
              <p className="mt-1 text-xs text-[var(--text-muted)]">
                Настройка профиля модели для специальных сценариев анализа.
              </p>
            </div>
            {onOpenModelConfig && (
              <Button
                variant="secondary"
                size="sm"
                onClick={onOpenModelConfig}
                className={SECONDARY_ACTION_BUTTON_CLASS}
              >
                Настроить профиль модели
              </Button>
            )}
          </div>
          <p className="mt-3 text-xs leading-5 text-[var(--text-secondary)]">
            {deal.model_config_name
              ? `Текущий профиль: ${deal.model_config_name}.`
              : "Будет использован профиль, привязанный к проекту или playbook."}
          </p>
        </section>

        <section className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-base)] p-4">
          <h4 className="text-sm font-semibold text-[var(--text-primary)]">
            Основной язык анализа
          </h4>
          <div className="mt-3 flex items-center gap-2">
            <select
              className="min-w-[220px] rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-2 text-xs text-[var(--text-primary)] disabled:opacity-50"
              value={selectedPrimaryLanguage}
              onChange={(e) => onPrimaryLanguageChange(e.target.value)}
              disabled={documentLanguages.length === 0 || isSubmitting}
            >
              <option value="">
                {hasMultipleDocumentLanguages
                  ? "Выберите основной язык"
                  : "Авто (единственный язык сделки)"}
              </option>
              {documentLanguages.map((lang) => (
                <option key={lang} value={lang}>
                  {lang}
                </option>
              ))}
            </select>
            {isSubmitting && (
              <span className="text-[11px] text-[var(--text-muted)]">
                Сохраняем…
              </span>
            )}
          </div>
          {documentLanguages.length > 0 && (
            <p className="mt-2 text-xs text-[var(--text-secondary)]">
              Языки документов: {documentLanguages.join(", ")}
            </p>
          )}
          {hasMultipleDocumentLanguages && !selectedPrimaryLanguage && (
            <p className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] leading-5 text-amber-800">
              В сделке есть документы на нескольких языках. Перед запуском
              анализа выберите основной язык.
            </p>
          )}
        </section>

        {deal.has_pending_manual_reclassifications && (
          <section className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-base)] p-4">
            <h4 className="text-sm font-semibold text-[var(--text-primary)]">
              Дополнительные параметры
            </h4>
            <label className="mt-3 flex cursor-pointer items-start gap-3 rounded-xl border border-[var(--border-soft)] bg-[var(--bg-card)] px-3 py-3 text-xs text-[var(--text-secondary)]">
              <input
                type="checkbox"
                className="mt-[2px]"
                checked={forceReclassify}
                onChange={(e) => onForceReclassifyChange(e.target.checked)}
                disabled={isSubmitting}
              />
              <span>
                <span className="block text-[13px] font-medium text-[var(--text-primary)]">
                  Принудительно переклассифицировать документы
                </span>
                <span className="block text-[11px] leading-5 text-[var(--text-secondary)]">
                  Используйте после ручной переклассификации, чтобы обновить
                  типы документов.
                </span>
              </span>
            </label>
          </section>
        )}
      </div>

      <div className="flex items-center justify-between border-t border-[var(--border-soft)] px-5 py-4">
        <Button variant="secondary" size="sm" onClick={onClose}>
          Отмена
        </Button>
        <div className="flex items-center gap-3">
          {!canLaunchRun && (
            <span className="text-[11px] text-[var(--text-muted)]">
              {readinessLabel}
            </span>
          )}
          <Button
            variant="primary"
            size="sm"
            onClick={onSubmit}
            disabled={!canLaunchRun}
            isLoading={isSubmitting}
          >
            Запустить анализ
          </Button>
        </div>
      </div>
    </div>
  );

  return (
    <>
      <div
        className="absolute inset-0 z-20 rounded-2xl bg-white/55 backdrop-blur-[1px]"
        onClick={onClose}
        aria-hidden="true"
      />

      <div className="absolute inset-y-0 right-[calc(100%+1rem)] z-30 hidden w-[760px] max-w-[calc(100vw-24rem)] xl:block">
        {panelContent}
      </div>

      <div
        className="fixed inset-0 z-40 bg-black/20 xl:hidden"
        onClick={onClose}
        aria-hidden="true"
      />

      <div className="fixed inset-x-4 bottom-4 top-20 z-50 flex flex-col rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-xl xl:hidden">
        <div className="flex items-start justify-between border-b border-[var(--border-soft)] px-4 py-4">
          <div>
            <h3 className="text-base font-semibold text-[var(--text-primary)]">
              Запуск анализа
            </h3>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              Проверьте параметры анализа для этой сделки.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-[var(--text-muted)] transition hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)]"
            aria-label="Закрыть панель запуска"
          >
            ✕
          </button>
        </div>
        <div className="space-y-4 overflow-y-auto p-4">
          <section className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-base)] p-4">
            <div className="flex flex-col gap-3">
              <div>
                <h4 className="text-sm font-semibold text-[var(--text-primary)]">
                  Документы
                </h4>
                <p className="mt-1 text-xs text-[var(--text-secondary)]">
                  {typeof documentsCount === "number"
                    ? `В проект загружено ${documentsCount} документ(ов).`
                    : "Загружаем информацию о документах…"}
                </p>
              </div>
              <Button
                variant="secondary"
                size="sm"
                onClick={onOpenUpload}
                disabled={!canUploadDocuments}
                className={SECONDARY_ACTION_BUTTON_CLASS}
              >
                Загрузить дополнительные документы
              </Button>
            </div>
          </section>
        </div>
      </div>
    </>
  );
};

const AnalysisActionsPanel: React.FC<{
  deal: Deal;
  latestRunExists: boolean;
  canStartRun: boolean;
  onOpenRunPanel: () => void;
  showReclassBanner: boolean;
}> = ({ deal, latestRunExists, canStartRun, onOpenRunPanel, showReclassBanner }) => {
  const hasPlaybook = !!deal.playbook_version_id;
  const documentLanguages = deal.languages ?? [];
  const hasMultipleDocumentLanguages = documentLanguages.length > 1;
  const primaryLanguageSelected = !!deal.primary_language;

  return (
    <aside className="self-start rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm xl:sticky xl:top-6">
      <div className="flex h-full flex-col px-5 py-5">
        <div>
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Действия
          </p>
          <h3 className="text-base font-semibold text-[var(--text-primary)]">
            Анализ документов
          </h3>
          <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
            {!latestRunExists
              ? "Настройте параметры и запустите первый анализ документов по этому проекту."
              : "Вы можете запустить повторный анализ, чтобы обновить результаты по текущему набору документов."}
          </p>
        </div>

        {showReclassBanner && (
          <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3">
            <p className="text-xs font-semibold text-amber-900">
              Требуется обновление результатов
            </p>
            <p className="mt-1 text-xs leading-5 text-amber-800">
              После ручной переклассификации рекомендуется повторно запустить
              анализ, чтобы привести выводы, DD Grid и связанные результаты в
              актуальное состояние.
            </p>
          </div>
        )}

        <div className="mt-5 rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-base)] px-4 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Текущая готовность
          </p>
          <div className="mt-3 space-y-2">
            <StatusRow
              label="Playbook проекта"
              value={hasPlaybook ? "Выбран" : "Не выбран"}
              tone={hasPlaybook ? "ok" : "warn"}
            />
            <StatusRow
              label="Языки документов"
              value={
                documentLanguages.length > 0
                  ? documentLanguages.join(", ")
                  : "Ещё не определены"
              }
              tone={documentLanguages.length > 0 ? "ok" : "neutral"}
            />
            <StatusRow
              label="Основной язык анализа"
              value={
                deal.primary_language
                  ? deal.primary_language
                  : hasMultipleDocumentLanguages
                  ? "Нужно выбрать перед запуском"
                  : "Будет определён автоматически"
              }
              tone={
                primaryLanguageSelected
                  ? "ok"
                  : hasMultipleDocumentLanguages
                  ? "warn"
                  : "neutral"
              }
            />
            <StatusRow
              label="Профиль модели"
              value={deal.model_config_name || "Профиль проекта / playbook"}
              tone={deal.model_config_name ? "ok" : "neutral"}
            />
          </div>
        </div>

        <div className="mt-5">
          <Button
            variant="primary"
            size="sm"
            onClick={onOpenRunPanel}
            disabled={!canStartRun}
          >
            Запустить анализ документов
          </Button>
        </div>
      </div>
    </aside>
  );
};

const OverviewTab: React.FC<OverviewTabProps> = ({
  deal,
  latestRunId,
  onOpenModelConfig,
}) => {
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data: dealDetail } = useDeal(deal.id);
  const { data: latestRun } = useRun(latestRunId ?? null, false);
  const { data: documentsCount } = useDocumentsCount(deal.id);

  const { canStartRun, canUploadDocuments } = useDealPermissions(deal.id);

  const startRun = useStartRun(deal.id);
  const setPrimaryLanguage = useSetPrimaryLanguage(deal.id);

  const [isLaunchPanelOpen, setIsLaunchPanelOpen] = React.useState(false);
  const [checksMode, setChecksMode] =
    React.useState<ChecksMode>("global_and_doc_type");
  const [forceReclassify, setForceReclassify] = React.useState(false);
  const [hasRestartedAfterReclass, setHasRestartedAfterReclass] =
    React.useState(false);

  const documentLanguages = deal.languages ?? [];
  const hasMultipleDocumentLanguages = documentLanguages.length > 1;

  const showReclassBanner =
    deal.has_pending_manual_reclassifications &&
    (!!latestRun || !hasRestartedAfterReclass);

  const canLaunchRun =
    canStartRun &&
    !!deal.playbook_version_id &&
    (!hasMultipleDocumentLanguages || !!deal.primary_language) &&
    !startRun.isPending &&
    !setPrimaryLanguage.isPending;

  const handleOpenPlaybook = () => {
    navigate(`/projects/${deal.id}/playbook`);
  };

  const handleOpenUpload = () => {
    if (!canUploadDocuments) return;
    navigate(`/projects/${deal.id}/upload`);
  };

  const handlePrimaryLanguageChange = (value: string) => {
    setPrimaryLanguage.mutate(
      { primary_language: value || null },
      {
        onSuccess: async () => {
          await Promise.all([
            qc.invalidateQueries({ queryKey: ["deal", deal.id] }),
            qc.invalidateQueries({ queryKey: ["latest-run", deal.id, true] }),
            qc.invalidateQueries({ queryKey: ["latest-run", deal.id, false] }),
          ]);
        },
      },
    );
  };

  const handleStartRun = () => {
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
            qc.invalidateQueries({ queryKey: ["run", run.id, true] }),
            qc.invalidateQueries({ queryKey: ["run", run.id, false] }),
            qc.invalidateQueries({
              queryKey: ["classification-report", run.id],
            }),
            qc.invalidateQueries({ queryKey: ["deal", deal.id] }),
            qc.invalidateQueries({ queryKey: ["latest-run", deal.id, true] }),
            qc.invalidateQueries({ queryKey: ["latest-run", deal.id, false] }),
            qc.invalidateQueries({ queryKey: ["all-runs", deal.id] }),
          ]);
        },
      },
    );
  };

  React.useEffect(() => {
    if (!isLaunchPanelOpen) return;

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsLaunchPanelOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isLaunchPanelOpen]);

  return (
    <div className="relative grid gap-4 xl:grid-cols-[minmax(0,2.2fr)_minmax(320px,1fr)]">
      <div className="relative space-y-4">
        <DealInfoCard deal={deal} detail={dealDetail} />

        <ProjectTimelineCard
          deal={deal}
          latestRunId={latestRunId}
          documentsCount={documentsCount}
        />

        <RunProgressCard latestRunId={latestRunId} />
      </div>

      <div className="relative">
        <AnalysisActionsPanel
          deal={deal}
          latestRunExists={!!latestRun}
          canStartRun={canStartRun}
          onOpenRunPanel={() => setIsLaunchPanelOpen(true)}
          showReclassBanner={showReclassBanner}
        />

        <LaunchOverlayPanel
          open={isLaunchPanelOpen}
          onClose={() => setIsLaunchPanelOpen(false)}
          deal={deal}
          latestRunId={latestRunId}
          documentsCount={documentsCount}
          checksMode={checksMode}
          onChecksModeChange={setChecksMode}
          forceReclassify={forceReclassify}
          onForceReclassifyChange={setForceReclassify}
          canStartRun={canStartRun}
          canUploadDocuments={canUploadDocuments}
          isSubmitting={startRun.isPending || setPrimaryLanguage.isPending}
          onOpenPlaybook={handleOpenPlaybook}
          onOpenModelConfig={onOpenModelConfig}
          onOpenUpload={handleOpenUpload}
          onPrimaryLanguageChange={handlePrimaryLanguageChange}
          onSubmit={handleStartRun}
        />
      </div>
    </div>
  );
};

export default OverviewTab;






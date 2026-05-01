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
// Правая колонка (не изменяется):
//   AnalysisActionsPanel + LaunchOverlayPanel.
// =============================================================

import React from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import type { Deal, DealDetail, RunStatus } from "../../types";
import {
  useRun,
  useStartRun,
} from "../../api/runs";
import { useDeal, useSetPrimaryLanguage } from "../../api/deals";
import { useDocumentsCount } from "../../api/documents";
import { resultApi } from "../../api/results";
import { useQuery } from "@tanstack/react-query";
import { useDealPermissions } from "../../hooks/usePermissions";
import { useSSEProgress } from "../../hooks/useSSE";
import { RUN_STATUS_CONFIG } from "../../utils/statusConfig";
import Button from "../../components/ui/Button";
import { useAuditLog } from "../../api/audit";
import type { AuditLogEntry } from "../../types";

// -------------------------------------------------------------
// Types
// -------------------------------------------------------------

type ChecksMode = "global_only" | "doc_type_only" | "global_and_doc_type";

interface OverviewTabProps {
  deal: Deal;
  latestRunId?: string | null;
  onOpenModelConfig?: () => void;
}

// -------------------------------------------------------------
// Constants
// -------------------------------------------------------------

const SECONDARY_ACTION_BUTTON_CLASS =
  "w-[220px] shrink-0 justify-center whitespace-nowrap text-sm font-semibold";

// -------------------------------------------------------------
// Helpers
// -------------------------------------------------------------

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

// -------------------------------------------------------------
// Sub-component: InfoRow — одна строка метаданных
// -------------------------------------------------------------

const InfoRow: React.FC<{
  label: string;
  children: React.ReactNode;
  tone?: "ok" | "warn" | "error" | "neutral";
}> = ({ label, children, tone = "neutral" }) => {
  const valueClass =
    tone === "ok"
      ? "text-green-700"
      : tone === "warn"
      ? "text-amber-700"
      : tone === "error"
      ? "text-red-600"
      : "text-gray-700";

  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-gray-500">{label}</span>
      <span className={`text-sm ${valueClass}`}>{children}</span>
    </div>
  );
};

// -------------------------------------------------------------
// Sub-component: StatusRow — строка готовности (правая панель)
// -------------------------------------------------------------

const StatusRow: React.FC<{
  label: string;
  value: string;
  tone?: "ok" | "warn" | "neutral";
}> = ({ label, value, tone = "neutral" }) => {
  const toneClass =
    tone === "ok"
      ? "text-green-700"
      : tone === "warn"
      ? "text-amber-700"
      : "text-gray-700";

  return (
    <div className="flex flex-col gap-0.5">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`text-sm ${toneClass}`}>{value}</p>
    </div>
  );
};

// -------------------------------------------------------------
// Sub-component: DealInfoCard — "О проекте"
// -------------------------------------------------------------

const DealInfoCard: React.FC<{
  deal: Deal;
  detail: DealDetail | null | undefined;
}> = ({
  deal,
  detail,
}) => {

  // description / counterparty берём из DealDetail, если загружен
  const description = detail?.description ?? null;
  const counterparty = detail?.counterparty ?? null;
  const contactPerson = deal.metadata_?.contact_person ?? null;

  return (
    <div className="rounded-lg border bg-white p-5">
      {/* Заголовок */}
      <div className="mb-4">
        <h2 className="text-xl font-bold text-gray-900">{deal.name}</h2>
        <p className="mt-0.5 text-sm text-gray-500">
          статус:{" "}
          <span className="font-medium text-gray-700">{deal.status}</span>
          {deal.deal_type && (
            <>
              {" "}· тип:{" "}
              <span className="font-medium text-gray-700">
                {deal.deal_type}
              </span>
            </>
          )}
        </p>
      </div>

      {/* Описание проекта */}
      {(description || counterparty || contactPerson || deal.jurisdiction) && (
        <div className="mb-4 space-y-2 border-b border-gray-100 pb-4">
          {description && (
            <div>
              <p className="text-xs text-gray-500">Описание</p>
              <p className="mt-0.5 text-sm leading-5 text-gray-700">
                {description}
              </p>
            </div>
          )}
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
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
        </div>
      )}


    </div>
  );
};

// -------------------------------------------------------------
// Sub-component: ProjectTimelineCard — "Хроника проекта"
// -------------------------------------------------------------

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

  // IMPORT приходят с корректным deal_id, сортируем по created_at: новые сверху
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
    const importedCount = typeof d.imported_count === "number" ? d.imported_count : 0;
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

const ProjectTimelineCard: React.FC<{
  deal: Deal;
  latestRunId?: string | null;
  documentsCount?: number;
}> = ({ deal, latestRunId, documentsCount }) => {
  // История всех запусков — используем тот же resultApi, что и useLatestRun
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
  const firstRun = allRuns && allRuns.length > 0
    ? allRuns[allRuns.length - 1]
    : null;

  const lastRunDate = latestRun?.completed_at ?? latestRun?.started_at ?? null;

  const lastRunStatusLabel = (() => {
    const s = latestRun?.status;
    if (!s) return null;
    if (s === "completed") return { text: "Завершён успешно", tone: "ok" };
    if (s === "completed_with_errors")
      return { text: "Завершён с ошибками", tone: "warn" };
    if (s === "failed") return { text: "Завершился с ошибкой", tone: "error" };
    if (s === "running") return { text: "Выполняется", tone: "neutral" };
    if (s === "pending") return { text: "В очереди", tone: "neutral" };
    return { text: s, tone: "neutral" };
  })();

  // Итоги последнего анализа
  const totalChecks = latestRun?.total_checks ?? 0;
  const failedDocs = latestRun?.failed_docs_count ?? 0;
  const quarantineDocs = latestRun?.quarantine_docs_count ?? 0;
  const successDocs =
    totalChecks > 0 ? totalChecks - failedDocs - quarantineDocs : 0;

  if (!deal.created_at && !latestRunId) {
    return null;
  }

  return (
    <div className="rounded-lg border bg-white p-5">
      <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-400">
        Хроника проекта
      </p>

      <ol className="space-y-3">
        {/* Создан */}
        <TimelineEvent
          icon="🗂"
          label="Проект создан"
          date={formatDate(deal.created_at)}
        />

        {/* Первая загрузка */}
        {auditAgg.firstUpload && (
          <TimelineEvent
            icon="📤"
            label="Первая загрузка документов"
            date={formatDateShort(auditAgg.firstUpload.created_at)}
          >
            <p className="mt-0.5 text-xs text-gray-500">
              Через импорт‑пайплайн началась работа с документами.
            </p>
          </TimelineEvent>
        )}

        {/* Последняя загрузка + агрегаты по последнему IMPORT */}
        {auditAgg.lastUpload && (
          <TimelineEvent
            icon="📥"
            label={
              auditAgg.totalUploads > 1
                ? `Последняя загрузка (из ${auditAgg.totalUploads})`
                : "Загрузка документов"
            }
            date={formatDateShort(auditAgg.lastUpload.created_at)}
          >
            {(() => {
              const d = (auditAgg.lastUpload.details ?? {}) as Record<string, unknown>;
              const totalFiles =
                typeof d.total_files === "number" ? d.total_files : undefined;
              const importedCount =
                typeof d.imported_count === "number" ? d.imported_count : undefined;
              const quarantineCount =
                typeof d.quarantine_count === "number" ? d.quarantine_count : undefined;
              const duplicateCount =
                typeof d.duplicate_count === "number" ? d.duplicate_count : undefined;

              return (
                <p className="mt-0.5 text-xs text-gray-500">
                  {typeof totalFiles === "number" && (
                    <>
                      Загрузка: {totalFiles} файл(ов)
                      {" · "}
                    </>
                  )}
                  {typeof importedCount === "number" && (
                    <>принято {importedCount}</>
                  )}
                  {typeof quarantineCount === "number" && quarantineCount > 0 && (
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

        {/* Сводка по карантину / неподдерживаемым форматам по всем загрузкам */}
        {(auditAgg.totalQuarantined > 0 || auditAgg.totalUnsupported > 0) && (
          <TimelineEvent
            icon="⚠️"
            label="Проблемные файлы при загрузках"
          >
            <p className="mt-0.5 text-xs text-gray-500">
              В карантине: {auditAgg.totalQuarantined}
              {auditAgg.totalUnsupported > 0 && (
                <> · неподдерживаемых форматов: {auditAgg.totalUnsupported}</>
              )}
            </p>
          </TimelineEvent>
        )}

        {/* Уже существующие блоки — документы, первый run, последний анализ */}
        {typeof documentsCount === "number" && (
          <TimelineEvent
            icon="📚"
            label={
              documentsCount > 0
                ? "Документы в проекте"
                : "Документы ещё не загружены"
            }
          >
            <p className="mt-0.5 text-xs text-gray-500">
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

        {/* Последний анализ */}
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
            label={
              totalRuns > 1
                ? `Последний анализ (${totalRuns} из ${totalRuns})`
                : "Последний анализ"
            }
            date={lastRunDate ? formatDateShort(lastRunDate) : "—"}
          >
            {/* Итоги */}
            {totalChecks > 0 && (
              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs">
                <span className="text-green-700">
                  ✓ проверено: {totalChecks}
                </span>
                {successDocs > 0 && (
                  <span className="text-green-600">успешно: {successDocs}</span>
                )}
                {failedDocs > 0 && (
                  <span className="text-red-600">
                    с ошибкой: {failedDocs}
                  </span>
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
                className={`mt-0.5 text-xs font-medium ${
                  lastRunStatusLabel.tone === "ok"
                    ? "text-green-700"
                    : lastRunStatusLabel.tone === "warn"
                    ? "text-amber-700"
                    : lastRunStatusLabel.tone === "error"
                    ? "text-red-600"
                    : "text-gray-500"
                }`}
              >
                {lastRunStatusLabel.text}
              </p>
            )}
          </TimelineEvent>
        )}
      </ol>

      {totalRuns > 1 && (
        <p className="mt-3 text-xs text-gray-400">
          Всего запусков анализа: {totalRuns}
        </p>
      )}
    </div>
  );
};

const TimelineEvent: React.FC<{
  icon: string;
  label: string;
  date?: string;
  children?: React.ReactNode;
}> = ({ icon, label, date, children }) => (
  <li className="flex gap-3">
    <span className="mt-0.5 shrink-0 text-base leading-none">{icon}</span>
    <div className="min-w-0">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <span className="text-sm font-medium text-gray-800">{label}</span>
        {date && <span className="text-xs text-gray-400">{date}</span>}
      </div>
      {children}
    </div>
  </li>
);

// -------------------------------------------------------------
// Sub-component: RunProgressCard — статус / прогресс анализа
// -------------------------------------------------------------

const RunProgressCard: React.FC<{
  latestRunId?: string | null;
}> = ({ latestRunId }) => {
  const runId = latestRunId ?? null;
  const { data: run, isLoading } = useRun(runId, false);
  const { lastEvent } = useSSEProgress(runId, { enabled: !!runId });

  if (!runId) {
    return (
      <div className="rounded-lg border bg-white p-5">
        <h3 className="mb-1 text-sm font-semibold text-gray-900">
          Статус анализа
        </h3>
        <p className="text-xs text-gray-500">
          Анализ ещё не запускался для этой сделки.
        </p>
      </div>
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
      ? "bg-red-500"
      : effectiveStatus === "completed"
      ? "bg-green-500"
      : effectiveStatus === "completed_with_errors"
      ? "bg-yellow-500"
      : "bg-blue-500";

  return (
    <div className="rounded-lg border bg-white p-5">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-900">Статус анализа</h3>

        {isLoading && !run ? (
          <span className="text-xs text-gray-400">Загружаем…</span>
        ) : (
          <span className="text-xs text-gray-500">
            {effectiveStatus
              ? (RUN_STATUS_CONFIG[effectiveStatus]?.label ?? effectiveStatus)
              : "—"}
          </span>
        )}
      </div>

      {effectiveTotal > 0 ? (
        <>
          <div className="mb-1 flex items-center justify-between text-xs">
            <span className="text-gray-500">
              {effectiveCompleted} / {effectiveTotal} проверок
            </span>
            <span className="font-semibold text-gray-700">{percent}%</span>
          </div>

          <div className="h-2 w-full rounded bg-gray-100">
            <div
              className={`h-2 rounded transition-all duration-300 ${progressColor}`}
              style={{ width: `${Math.min(100, percent)}%` }}
            />
          </div>

          {(effectiveStatus === "failed" ||
            effectiveStatus === "completed_with_errors") &&
            run && (
              <p
                className={`mt-2 text-xs ${
                  effectiveStatus === "failed"
                    ? "text-red-600"
                    : "text-amber-700"
                }`}
              >
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
            )}
        </>
      ) : (
        <p className="text-xs text-gray-500">
          Документы для анализа ещё не готовы или пайплайн не запущен.
        </p>
      )}
    </div>
  );
};

// -------------------------------------------------------------
// Sub-component: LaunchOverlayPanel (правая панель, не меняется)
// -------------------------------------------------------------

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
    canStartRun && hasPlaybook && hasValidPrimaryLanguageSelection && !isSubmitting;

  const readinessLabel = !hasPlaybook
    ? "Нужно выбрать playbook, чтобы запустить анализ."
    : !hasValidPrimaryLanguageSelection
    ? "Нужно выбрать основной язык анализа."
    : "Параметры готовы к запуску анализа.";

  if (!open) return null;

  const panelContent = (
    <div className="flex max-h-[calc(100vh-7rem)] flex-col rounded-lg border border-gray-200 bg-white shadow-xl">
      {/* Header */}
      <div className="flex items-start justify-between border-b border-gray-200 px-5 py-4">
        <div>
          <h3 className="text-base font-semibold text-gray-900">
            Запуск анализа
          </h3>
          <p className="mt-1 text-sm text-gray-600">
            Проверьте параметры анализа для этой сделки.
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-1 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600"
          aria-label="Закрыть панель запуска"
        >
          ✕
        </button>
      </div>

      {/* Body */}
      <div className="space-y-3 overflow-y-auto px-5 py-4">
        {/* Readiness banner */}
        <div className="rounded border border-gray-200 bg-gray-50 px-3 py-2">
          <p className="text-xs font-semibold text-gray-800">
            {readinessLabel}
          </p>
          {latestRunId && (
            <p className="mt-1 text-[11px] text-gray-500">
              Последний анализ уже запускался. Новый запуск обновит результаты
              по текущим документам.
            </p>
          )}
        </div>

        {/* Documents */}
        <section className="rounded-lg border border-gray-200 p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <h4 className="text-sm font-semibold text-gray-900">
                Документы
              </h4>
              <p className="mt-1 text-xs text-gray-600">
                {typeof documentsCount === "number"
                  ? `В проект загружено ${documentsCount} документ(ов).`
                  : "Загружаем информацию о документах…"}
              </p>
              <p className="mt-1 text-[11px] text-gray-500">
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

        {/* Checks mode */}
        <section className="rounded-lg border border-gray-200 p-4">
          <h4 className="text-sm font-semibold text-gray-900">
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
                className="flex cursor-pointer items-start gap-2 rounded border border-gray-200 px-3 py-2 transition hover:bg-gray-50"
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
                  <span className="block text-[13px] font-medium text-gray-900">
                    {title}
                  </span>
                  <span className="block text-[11px] text-gray-500">
                    {hint}
                  </span>
                </span>
              </label>
            ))}
          </div>
        </section>

        {/* Playbook */}
        <section className="rounded-lg border border-gray-200 p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <h4 className="text-sm font-semibold text-gray-900">
                Playbook проекта
              </h4>
              <p className="mt-1 text-xs text-gray-500">
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
          <p className="mt-3 text-xs">
            {hasPlaybook ? (
              <span className="text-gray-700">
                Playbook выбран. При необходимости вы можете изменить его перед
                запуском.
              </span>
            ) : (
              <span className="text-red-600">
                Playbook не выбран. Нельзя запустить анализ без выбранного
                playbook.
              </span>
            )}
          </p>
        </section>

        {/* Model profile */}
        <section className="rounded-lg border border-gray-200 p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <h4 className="text-sm font-semibold text-gray-900">
                Профиль модели
              </h4>
              <p className="mt-1 text-xs text-gray-500">
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
          <p className="mt-3 text-xs text-gray-700">
            {deal.model_config_name
              ? `Текущий профиль: ${deal.model_config_name}.`
              : "Будет использован профиль, привязанный к проекту или playbook."}
          </p>
        </section>

        {/* Primary language */}
        <section className="rounded-lg border border-gray-200 p-4">
          <h4 className="text-sm font-semibold text-gray-900">
            Основной язык анализа
          </h4>
          <div className="mt-3 flex items-center gap-2">
            <select
              className="rounded border bg-white px-2 py-1 text-xs text-gray-700 disabled:opacity-50"
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
              <span className="text-[11px] text-gray-400">Сохраняем…</span>
            )}
          </div>
          {documentLanguages.length > 0 && (
            <p className="mt-2 text-xs text-gray-500">
              Языки документов: {documentLanguages.join(", ")}
            </p>
          )}
          {hasMultipleDocumentLanguages && !selectedPrimaryLanguage && (
            <p className="mt-3 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-800">
              В сделке есть документы на нескольких языках. Перед запуском
              анализа выберите основной язык.
            </p>
          )}
        </section>

        {/* Force reclassify */}
        {deal.has_pending_manual_reclassifications && (
          <section className="rounded-lg border border-gray-200 p-4">
            <h4 className="text-sm font-semibold text-gray-900">
              Дополнительные параметры
            </h4>
            <label className="mt-3 flex cursor-pointer items-start gap-2 text-xs text-gray-700">
              <input
                type="checkbox"
                className="mt-[2px]"
                checked={forceReclassify}
                onChange={(e) => onForceReclassifyChange(e.target.checked)}
                disabled={isSubmitting}
              />
              <span>
                <span className="block text-[13px] font-medium text-gray-900">
                  Принудительно переклассифицировать документы
                </span>
                <span className="block text-[11px] text-gray-500">
                  Используйте после ручной переклассификации, чтобы обновить
                  типы документов.
                </span>
              </span>
            </label>
          </section>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between border-t border-gray-200 px-5 py-4">
        <Button variant="secondary" size="sm" onClick={onClose}>
          Отмена
        </Button>
        <div className="flex items-center gap-3">
          {!canLaunchRun && (
            <span className="text-[11px] text-gray-500">{readinessLabel}</span>
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
      {/* Backdrop — desktop */}
      <div
        className="absolute inset-0 z-20 rounded-lg bg-white/55 backdrop-blur-[1px]"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Panel — desktop (слева от правой колонки) */}
      <div className="absolute inset-y-0 right-[calc(100%+1rem)] z-30 hidden w-[760px] max-w-[calc(100vw-24rem)] xl:block">
        {panelContent}
      </div>

      {/* Backdrop — mobile */}
      <div
        className="fixed inset-0 z-40 bg-black/20 xl:hidden"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Panel — mobile (full-screen sheet) */}
      <div className="fixed inset-x-4 bottom-4 top-20 z-50 flex flex-col rounded-lg border border-gray-200 bg-white shadow-xl xl:hidden">
        <div className="flex items-start justify-between border-b border-gray-200 px-4 py-4">
          <div>
            <h3 className="text-base font-semibold text-gray-900">
              Запуск анализа
            </h3>
            <p className="mt-1 text-sm text-gray-600">
              Проверьте параметры анализа для этой сделки.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600"
            aria-label="Закрыть панель запуска"
          >
            ✕
          </button>
        </div>
        <div className="space-y-4 overflow-y-auto p-4">
          <section className="rounded-lg border border-gray-200 p-4">
            <div className="flex flex-col gap-3">
              <div>
                <h4 className="text-sm font-semibold text-gray-900">
                  Документы
                </h4>
                <p className="mt-1 text-xs text-gray-600">
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

// -------------------------------------------------------------
// Sub-component: AnalysisActionsPanel (правая панель, не меняется)
// -------------------------------------------------------------

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
    <div className="self-start rounded-lg border bg-white p-5 xl:sticky xl:top-6">
      <div className="flex h-full flex-col">
        <div>
          <h3 className="text-base font-semibold text-gray-900">
            Анализ документов
          </h3>
          <p className="mt-2 text-sm leading-6 text-gray-600">
            {!latestRunExists
              ? "Настройте параметры и запустите первый анализ документов по этому проекту."
              : "Вы можете запустить повторный анализ, чтобы обновить результаты по текущему набору документов."}
          </p>
        </div>

        {showReclassBanner && (
          <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-3">
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

        {/* Текущая готовность */}
        <div className="mt-5 rounded-md border border-gray-200 px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-700">
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
    </div>
  );
};

// -------------------------------------------------------------
// Main: OverviewTab
// -------------------------------------------------------------

const OverviewTab: React.FC<OverviewTabProps> = ({
  deal,
  latestRunId,
  onOpenModelConfig,
}) => {
  const navigate = useNavigate();
  const qc = useQueryClient();

  // Загружаем DealDetail для description / counterparty.
  // Данные скорее всего уже в React Query кэше от родительского
  // компонента (ProjectPage), поэтому дополнительного сетевого
  // запроса в большинстве случаев не будет.
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

  // Escape закрывает панель запуска
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
      {/* ── Левая колонка ── */}
      <div className="relative space-y-4">
        {/* 1. О проекте */}
        <DealInfoCard
          deal={deal}
          detail={dealDetail}
        />

        {/* 2. Хроника проекта */}
        <ProjectTimelineCard
          deal={deal}
          latestRunId={latestRunId}
          documentsCount={documentsCount}
        />

        {/* 3. Статус / прогресс анализа */}
        <RunProgressCard latestRunId={latestRunId} />
      </div>

      {/* ── Правая колонка (не меняется) ── */}
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






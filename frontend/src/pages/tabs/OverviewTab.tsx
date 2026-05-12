// =============================================================
// src/pages/tabs/OverviewTab.tsx
// Launch panel раскрывается до границы основной контентной колонки,
// без backdrop и без перекрытия AnalysisActionsPanel.
// Ширина overlay вычисляется от реального layout, а не от 100vw.
// =============================================================

import React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { AuditLogEntry, Deal, RunStatus } from "../../types";
import { useRun, useStartRun } from "../../api/runs";
import { useSetPrimaryLanguage, useUpdateDeal } from "../../api/deals";
import { useDocumentsCount } from "../../api/documents";
import { resultApi } from "../../api/results";
import { useDealPermissions } from "../../hooks/usePermissions";
import { useSSEProgress } from "../../hooks/useSSE";
import { RUN_STATUS_CONFIG } from "../../utils/statusConfig";
import { useAuditLog } from "../../api/audit";
import Button from "../../components/ui/Button";
import AnalysisActionsPanel from "./overview/AnalysisActionsPanel";
import LaunchWideOverlay from "./overview/LaunchWideOverlay";

export type ChecksMode =
  | "global_only"
  | "doc_type_only"
  | "global_and_doc_type";

interface OverviewTabProps {
  deal: Deal;
  latestRunId?: string | null;
}

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

function normalizeDiscoveryStatus(
  value: string | null | undefined,
): string | null {
  const normalized = String(value ?? "").trim().toLowerCase();
  return normalized || null;
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

  const lastUpload = sortedImports[0] ?? null;
  const firstUpload = sortedImports[sortedImports.length - 1] ?? null;

  return {
    firstUpload,
    lastUpload,
    totalUploads: imports.length,
    totalQuarantined: quarantined.length,
    totalUnsupported: unsupported.length,
    manualReclassifications: reclassified.length,
  };
}

const CardShell: React.FC<{
  title: string;
  eyebrow?: string;
  children: React.ReactNode;
  rightSlot?: React.ReactNode;
}> = ({ title, eyebrow, children, rightSlot }) => (
  <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
    <div className="px-5">
      <div className="flex items-start justify-between gap-4 py-4">
        <div className="min-w-0">
          {eyebrow ? (
            <>
              <h2 className="text-base font-semibold text-[var(--text-primary)]">
                {eyebrow}
              </h2>
              <p className="mt-1 text-sm text-[var(--text-muted)]">
                {title}
              </p>
            </>
          ) : (
            <h2 className="text-base font-semibold text-[var(--text-primary)]">
              {title}
            </h2>
          )}
        </div>
        {rightSlot}
      </div>

      <div className="border-t border-[var(--border-subtle)]" />
    </div>

    <div className="px-5 py-4">{children}</div>
  </section>
);

const DealInfoCard: React.FC<{
  deal: Deal;
  projectSummary: string;
  isSaving: boolean;
  isDirty: boolean;
  onChangeSummary: (value: string) => void;
  onSaveSummary: () => void;
}> = ({
  deal,
  projectSummary,
  isSaving,
  isDirty,
  onChangeSummary,
  onSaveSummary,
}) => (
  <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
    <div className="px-5">
      <div className="py-4">
        <h2 className="text-base font-semibold text-[var(--text-primary)]">
          О проекте
        </h2>
        <p className="mt-1 text-sm text-[var(--text-muted)]">
          Краткое описание проекта для рабочей команды.
        </p>
      </div>

      <div className="border-t border-[var(--border-subtle)]" />
    </div>

    <div className="px-5 py-4">
      <textarea
        id={`deal-summary-${deal.id}`}
        value={projectSummary}
        onChange={(e) => onChangeSummary(e.target.value)}
        rows={6}
        placeholder="Например: продажа группы компаний, buy-side DD, проверяем корпоративный блок, ключевые договоры и IP..."
        className="mt-2 w-full rounded-2xl border border-[var(--border)] bg-[var(--bg-base)] px-4 py-3 text-sm leading-6 text-[var(--text-primary)] outline-none transition placeholder:text-[var(--text-muted)] focus:border-[var(--accent-primary)]"
      />

      <div className="mt-3 flex items-center justify-between gap-3">
        <p className="text-[11px] leading-5 text-[var(--text-muted)]">
          Это поле хранится отдельно для данного проекта и помогает юристам
          быстрее понимать контекст сделки.
        </p>

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
    </div>
  </section>
);

const TimelineEvent: React.FC<{
  icon: string;
  label: string;
  date?: string;
  children?: React.ReactNode;
}> = ({ icon, label, date, children }) => (
  <li className="relative flex gap-3">
    <span className="mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-sm">
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

function runStatusTextClass(tone: "ok" | "warn" | "error" | "neutral"): string {
  if (tone === "ok") return "text-[var(--color-success)]";
  if (tone === "warn") return "text-[var(--color-warning)]";
  if (tone === "error") return "text-[var(--color-error)]";
  return "text-[var(--text-secondary)]";
}

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
  const firstRun =
    allRuns && allRuns.length > 0 ? allRuns[allRuns.length - 1] : null;
  const lastRunDate = latestRun?.completed_at ?? latestRun?.started_at ?? null;

  const lastRunStatusLabel = (() => {
    const s = latestRun?.status;
    if (!s) return null;
    if (s === "completed") {
      return { text: "Завершён успешно", tone: "ok" as const };
    }
    if (s === "completed_with_errors") {
      return { text: "Завершён с ошибками", tone: "warn" as const };
    }
    if (s === "failed") {
      return { text: "Завершился с ошибкой", tone: "error" as const };
    }
    if (s === "running") {
      return { text: "Выполняется", tone: "neutral" as const };
    }
    if (s === "pending") {
      return { text: "В очереди", tone: "neutral" as const };
    }
    return { text: s, tone: "neutral" as const };
  })();

  const totalChecks = latestRun?.total_checks ?? 0;
  const failedDocs = latestRun?.failed_docs_count ?? 0;
  const quarantineDocs = latestRun?.quarantine_docs_count ?? 0;
  const successDocs =
    totalChecks > 0 ? totalChecks - failedDocs - quarantineDocs : 0;

  if (!deal.created_at && !latestRunId) return null;

  return (
    <CardShell eyebrow="Активность" title="Хроника действий по проекту">
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
            <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
              Последний пакет документов загружен в проект.
            </p>
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

        {firstRun?.started_at && (
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
                    с ошибкой: {failedDocs}
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
                className={`mt-1 text-[12px] font-medium ${runStatusTextClass(lastRunStatusLabel.tone)}`}
              >
                {lastRunStatusLabel.text}
              </p>
            )}
          </TimelineEvent>
        )}
      </ol>
    </CardShell>
  );
};

function progressBarClass(status: RunStatus | undefined): string {
  if (status === "failed") return "bg-[var(--color-error)]";
  if (status === "completed") return "bg-[var(--color-success)]";
  if (status === "completed_with_errors") return "bg-[var(--color-warning)]";
  return "bg-[var(--accent-primary)]";
}

const RunProgressCard: React.FC<{
  latestRunId?: string | null;
}> = ({ latestRunId }) => {
  const runId = latestRunId ?? null;
  const { data: run, isLoading } = useRun(runId, false);
  const { lastEvent } = useSSEProgress(runId, { enabled: !!runId });

  if (!runId) {
    return (
      <CardShell
        eyebrow="Статус проверок"
        title="Количество и статус проведённых проверок в проекте"
      >
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

  return (
    <CardShell
      eyebrow="Статус проверок"
      title="Количество и статус проведённых проверок в проекте"
      rightSlot={
        isLoading && !run ? (
          <span className="text-[11px] text-[var(--text-muted)]">
            Загружаем…
          </span>
        ) : (
          <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-3 py-1 text-[11px] font-medium text-[var(--text-secondary)]">
            {effectiveStatus
              ? RUN_STATUS_CONFIG[effectiveStatus]?.label ?? effectiveStatus
              : "—"}
          </span>
        )
      }
    >
      {effectiveTotal > 0 ? (
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-2 text-[12px]">
            <span className="text-[var(--text-secondary)]">
              {effectiveCompleted} / {effectiveTotal} проверок
            </span>
            <span className="font-semibold text-[var(--text-primary)]">
              {percent}%
            </span>
          </div>

          <div className="h-2.5 w-full rounded-full bg-[var(--bg-elevated-soft)]">
            <div
              className={`h-2.5 rounded-full transition-all duration-300 ${progressBarClass(effectiveStatus)}`}
              style={{ width: `${Math.min(100, percent)}%` }}
            />
          </div>

          {(effectiveStatus === "failed" ||
            effectiveStatus === "completed_with_errors") &&
            run && (
              <div
                className={`rounded-xl border px-3 py-2 text-[12px] leading-5 ${
                  effectiveStatus === "failed"
                    ? "border-[var(--color-error-border)] bg-[var(--color-error-subtle)] text-[var(--color-error)]"
                    : "border-[var(--color-warning-border)] bg-[var(--color-warning-subtle)] text-[var(--color-warning)]"
                }`}
              >
                <p>
                  {effectiveStatus === "failed"
                    ? "Анализ завершился с ошибкой."
                    : "Анализ завершён, но есть документы с ошибками."}
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

const OverviewTab: React.FC<OverviewTabProps> = ({
  deal,
  latestRunId,
}) => {
  const qc = useQueryClient();

  const { data: latestRun } = useRun(latestRunId ?? null, false);
  const { data: documentsCount } = useDocumentsCount(deal.id);
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
      const gap =
        parseFloat(styles.columnGap || styles.gap || "0") || 0;

      const width = Math.max(
        0,
        overviewRect.width - railRect.width - gap,
      );

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

  React.useEffect(() => {
    setProjectSummary(deal.summary ?? "");
    setDealPatch({});
  }, [deal.id, deal.summary, deal.playbook_version_id, deal.primary_language, deal.language_discovery_status, JSON.stringify(deal.languages ?? [])]);

  React.useEffect(() => {
    if (!isLaunchPanelOpen) return;

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsLaunchPanelOpen(false);
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isLaunchPanelOpen]);

  const effectiveDeal: Deal = {
    ...deal,
    ...dealPatch,
  };

  const normalizedOriginalSummary = (deal.summary ?? "").trim();
  const normalizedDraftSummary = projectSummary.trim();
  const isSummaryDirty = normalizedDraftSummary !== normalizedOriginalSummary;

  const showReclassBanner =
    effectiveDeal.has_pending_manual_reclassifications &&
    (!!latestRun || !hasRestartedAfterReclass);

  const hasDocuments =
    typeof documentsCount === "number" ? documentsCount > 0 : false;

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

  const handlePrimaryLanguageChange = (value: string) => {
    const normalizedValue = value || null;

    setDealPatch((prev) => ({
      ...prev,
      primary_language: normalizedValue,
    }));

    setPrimaryLanguage.mutate(
      {
        primary_language: normalizedValue,
      },
      {
        onError: () => {
          setDealPatch((prev) => ({
            ...prev,
            primary_language: deal.primary_language ?? null,
          }));
        },
      },
    );
  };

  const handleSaveSummary = () => {
    if (!isSummaryDirty) return;

    updateDeal.mutate({
      summary:
        normalizedDraftSummary.length > 0 ? normalizedDraftSummary : null,
    });
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

  const handleDealPatched = async (patch?: Partial<Deal>) => {
    if (patch && Object.keys(patch).length > 0) {
      setDealPatch((prev) => ({
        ...prev,
        ...patch,
      }));
    }

    await Promise.all([
      qc.invalidateQueries({ queryKey: ["deal", deal.id] }),
      qc.invalidateQueries({ queryKey: ["latest-run", deal.id, true] }),
      qc.invalidateQueries({ queryKey: ["latest-run", deal.id, false] }),
    ]);
  };

  return (
    <div
      ref={overviewRef}
      className="relative grid gap-4 xl:grid-cols-[minmax(0,2.2fr)_360px]"
    >
      <div className="min-w-0 space-y-4">
        <DealInfoCard
          deal={effectiveDeal}
          projectSummary={projectSummary}
          isSaving={updateDeal.isPending}
          isDirty={isSummaryDirty}
          onChangeSummary={setProjectSummary}
          onSaveSummary={handleSaveSummary}
        />

        <ProjectTimelineCard
          deal={effectiveDeal}
          latestRunId={latestRunId}
          documentsCount={documentsCount}
        />

        <RunProgressCard latestRunId={latestRunId} />
      </div>

      <div ref={railRef} className="relative hidden xl:block px-1 pb-2">
        <AnalysisActionsPanel
          deal={effectiveDeal}
          latestRunExists={!!latestRun}
          canStartRun={canLaunchRun}
          onOpenRunPanel={() => setIsLaunchPanelOpen(true)}
          showReclassBanner={showReclassBanner}
        />

        {overlayWidth !== null && (
          <LaunchWideOverlay
            open={isLaunchPanelOpen}
            overlayWidth={overlayWidth}
            deal={effectiveDeal}
            latestRunId={latestRunId}
            documentsCount={documentsCount}
            checksMode={checksMode}
            onChecksModeChange={setChecksMode}
            forceReclassify={forceReclassify}
            onForceReclassifyChange={setForceReclassify}
            canStartRun={canLaunchRun}
            canUploadDocuments={canUploadDocuments}
            isSubmitting={
              startRun.isPending ||
              updateDeal.isPending ||
              setPrimaryLanguage.isPending
            }
            onPrimaryLanguageChange={handlePrimaryLanguageChange}
            onSubmit={handleStartRun}
            onClose={() => setIsLaunchPanelOpen(false)}
            onDealPatched={handleDealPatched}
          />
        )}
      </div>

      <div className="xl:hidden">
        <AnalysisActionsPanel
          deal={effectiveDeal}
          latestRunExists={!!latestRun}
          canStartRun={canLaunchRun}
          onOpenRunPanel={() => setIsLaunchPanelOpen(true)}
          showReclassBanner={showReclassBanner}
        />
      </div>
    </div>
  );
};

export default OverviewTab;






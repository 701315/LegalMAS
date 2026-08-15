// =============================================================
// src/pages/tabs/overview/ProjectDomainDetailsPanel.tsx
// =============================================================

import React from "react";
import { ChevronRight, ChevronDown, Loader2, FileText } from "lucide-react";
import { PipelineStepIcon } from "./pipelineStepIcons";
import {
  PipelineLayoutProvider,
  usePipelineLayout,
} from "./pipelineLayoutContext";
import type { Deal } from "../../../types";
import DocumentsPipelinePanel from "./DocumentsPipelinePanel";
import { LLMUsageWidget } from "./LLMUsageWidget";
import { DocumentsOverviewWidget } from "./DocumentsOverviewWidget";
import { AnalysisResultsWidget } from "./AnalysisResultsWidget";
import { RunSummaryPanel } from "./RunSummaryPanel";
import { useDealLLMUsage } from "../../../api/deals";
import { useDocuments } from "../../../api/documents";
import { useRunProgress, useRunSummary } from "../../../api/runs";
import { DEMO_AGGREGATES } from "../counterparties/constants";
import { DEMO_OBJECTS } from "../real-estate/constants";

type DomainKey = "documents" | "counterparties" | "real_estate";

interface ProjectDomainDetailsPanelProps {
  activeDomain: DomainKey;
  onDomainChange: (d: DomainKey) => void;
  runId: string | null;
  deal: Deal;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getDomainLabel(domain: DomainKey): string {
  switch (domain) {
    case "documents":
      return "Документы";
    case "counterparties":
      return "Контрагенты";
    case "real_estate":
      return "Имущество";
  }
}

// ---------------------------------------------------------------------------
// Column shell
// ---------------------------------------------------------------------------

interface ColumnShellProps {
  title: string;
  children: React.ReactNode;
}

const ColumnShell: React.FC<ColumnShellProps> = ({ title, children }) => (
  <div className="flex h-full min-h-0 min-w-0 flex-col">
    <p className="mb-2 shrink-0 text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">
      {title}
    </p>
    <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1">
      {children}
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// Counterparties summary
// ---------------------------------------------------------------------------

const CounterpartiesSummary: React.FC = () => {
  const critical = DEMO_AGGREGATES.filter(
    (item) => item.reviewStatus === "critical",
  );
  const sanctions = DEMO_AGGREGATES.filter((item) => item.sanctionsFlag);
  const bankruptcy = DEMO_AGGREGATES.filter((item) => item.bankruptcyFlag);

  const countryMap = new Map<string, number>();
  for (const item of DEMO_AGGREGATES) {
    countryMap.set(item.country, (countryMap.get(item.country) ?? 0) + 1);
  }
  const topCountries = [...countryMap.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4);

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-xl border border-[var(--border)] px-3 py-2.5">
          <p className="text-[10px] text-[var(--text-muted)]">Всего</p>
          <p className="mt-0.5 text-lg font-semibold tabular-nums text-[var(--text-primary)]">
            {DEMO_AGGREGATES.length}
          </p>
        </div>
        <div className="rounded-xl border border-[var(--border)] px-3 py-2.5">
          <p className="text-[10px] text-[var(--text-muted)]">Critical</p>
          <p className="mt-0.5 text-lg font-semibold tabular-nums text-[var(--color-error-text)]">
            {critical.length}
          </p>
        </div>
        <div className="rounded-xl border border-[var(--border)] px-3 py-2.5">
          <p className="text-[10px] text-[var(--text-muted)]">Санкции</p>
          <p className="mt-0.5 text-lg font-semibold tabular-nums text-[var(--color-error-text)]">
            {sanctions.length}
          </p>
        </div>
        <div className="rounded-xl border border-[var(--border)] px-3 py-2.5">
          <p className="text-[10px] text-[var(--text-muted)]">Банкротство</p>
          <p className="mt-0.5 text-lg font-semibold tabular-nums text-[var(--color-warning-text)]">
            {bankruptcy.length}
          </p>
        </div>
      </div>

      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-2.5">
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--text-muted)]">
          География
        </p>
        <div className="space-y-1.5">
          {topCountries.map(([country, count]) => (
            <div key={country} className="flex items-center justify-between gap-2">
              <span className="text-xs text-[var(--text-primary)]">{country}</span>
              <span className="text-[11px] tabular-nums text-[var(--text-muted)]">{count}</span>
            </div>
          ))}
        </div>
      </div>

      <p className="text-[11px] text-[var(--text-muted)]">
        Демо-данные. Перейдите на вкладку «Контрагенты» для полного анализа.
      </p>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Real estate summary
// ---------------------------------------------------------------------------

const RealEstateSummary: React.FC = () => {
  const encumbered = DEMO_OBJECTS.filter((item) => item.encumbrance === true);
  const ownershipReview = DEMO_OBJECTS.filter(
    (item) => item.ownership_status === "review" || item.ownership_status === "not_confirmed",
  );
  const highRisk = DEMO_OBJECTS.filter((item) => item.risk === "high");

  const regionMap = new Map<string, number>();
  for (const item of DEMO_OBJECTS) {
    regionMap.set(item.region, (regionMap.get(item.region) ?? 0) + 1);
  }
  const topRegions = [...regionMap.entries()].sort((a, b) => b[1] - a[1]).slice(0, 4);

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-xl border border-[var(--border)] px-3 py-2.5">
          <p className="text-[10px] text-[var(--text-muted)]">Объектов</p>
          <p className="mt-0.5 text-lg font-semibold tabular-nums text-[var(--text-primary)]">{DEMO_OBJECTS.length}</p>
        </div>
        <div className="rounded-xl border border-[var(--border)] px-3 py-2.5">
          <p className="text-[10px] text-[var(--text-muted)]">С обременением</p>
          <p className="mt-0.5 text-lg font-semibold tabular-nums text-[var(--color-error-text)]">{encumbered.length}</p>
        </div>
        <div className="rounded-xl border border-[var(--border)] px-3 py-2.5">
          <p className="text-[10px] text-[var(--text-muted)]">Ownership review</p>
          <p className="mt-0.5 text-lg font-semibold tabular-nums text-[var(--color-warning-text)]">{ownershipReview.length}</p>
        </div>
        <div className="rounded-xl border border-[var(--border)] px-3 py-2.5">
          <p className="text-[10px] text-[var(--text-muted)]">Высокий риск</p>
          <p className="mt-0.5 text-lg font-semibold tabular-nums text-[var(--color-error-text)]">{highRisk.length}</p>
        </div>
      </div>

      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-2.5">
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--text-muted)]">Топ регионов</p>
        <div className="space-y-1.5">
          {topRegions.map(([region, count]) => (
            <div key={region} className="flex items-center justify-between gap-2">
              <span className="text-xs text-[var(--text-primary)]">{region}</span>
              <span className="text-[11px] tabular-nums text-[var(--text-muted)]">{count}</span>
            </div>
          ))}
        </div>
      </div>

      <p className="text-[11px] text-[var(--text-muted)]">
        Демо-данные. Перейдите на вкладку «Имущество» для полного анализа.
      </p>
    </div>
  );
};

// ---------------------------------------------------------------------------
// DocumentsContent
// ---------------------------------------------------------------------------

function isTerminalRunStatus(status: string | undefined): boolean {
  return status === "completed" || status === "completed_with_errors" || status === "failed";
}

type StepBadgeStatus = "pending" | "running" | "completed" | "completed_with_errors" | "failed";

interface CollapsedStep {
  code: string;
  title: string;
  status: StepBadgeStatus;
  duration_seconds?: number | null;
}

function formatCollapsedStepTooltip(step: CollapsedStep): string {
  const statusLabel: Record<StepBadgeStatus, string> = {
    completed: "завершён",
    completed_with_errors: "завершён с ошибками",
    failed: "ошибка",
    running: "идёт",
    pending: "ожидание",
  };

  const parts = [step.title, statusLabel[step.status]];

  if (typeof step.duration_seconds === "number" && step.duration_seconds > 0 && step.status !== "pending") {
    if (step.duration_seconds < 60) {
      parts.push(`${step.duration_seconds} сек`);
    } else {
      const m = Math.floor(step.duration_seconds / 60);
      const s = step.duration_seconds % 60;
      parts.push(s > 0 ? `${m} мин ${s} сек` : `${m} мин`);
    }
  }

  return parts.join(" · ");
}

const CollapsedStepBadge: React.FC<{ step: CollapsedStep }> = ({ step }) => {
  const baseClass = "flex h-8 w-8 items-center justify-center rounded-full";
  const tooltip = formatCollapsedStepTooltip(step);

  if (step.status === "completed") {
    return (
      <span className={`${baseClass} bg-[var(--color-success)] text-white`} title={tooltip} aria-label={tooltip}>
        <PipelineStepIcon code={step.code} className="h-4 w-4" strokeWidth={2.25} />
      </span>
    );
  }
  if (step.status === "completed_with_errors") {
    return (
      <span className={`${baseClass} bg-[var(--color-warning)] text-white`} title={tooltip} aria-label={tooltip}>
        <PipelineStepIcon code={step.code} className="h-4 w-4" strokeWidth={2.25} />
      </span>
    );
  }
  if (step.status === "failed") {
    return (
      <span className={`${baseClass} bg-[var(--color-error)] text-white`} title={tooltip} aria-label={tooltip}>
        <PipelineStepIcon code={step.code} className="h-4 w-4" strokeWidth={2.25} />
      </span>
    );
  }
  if (step.status === "running") {
    return (
      <span className={`${baseClass} bg-[var(--accent-primary)] text-white`} title={tooltip} aria-label={tooltip}>
        <Loader2 className="h-4 w-4 animate-spin" strokeWidth={2.5} aria-hidden />
      </span>
    );
  }

  return (
    <span className={`${baseClass} border border-[var(--border)] bg-[var(--bg-elevated-soft)] text-[var(--text-muted)]`} title={tooltip} aria-label={tooltip}>
      <PipelineStepIcon code={step.code} className="h-4 w-4" strokeWidth={2} />
    </span>
  );
};

const COLLAPSED_BADGE_HEIGHT_PX = 32;
const COLLAPSED_FALLBACK_STEP_GAP_PX = 60;
const COLLAPSED_FALLBACK_TOP_OFFSET_PX = 8;
const COLLAPSED_RAIL_TOP_PADDING_PX = 36;

const CollapsedPipelineSummary: React.FC<{
  runId: string | null;
  onExpand: () => void;
  summaryStatus?: string | null;
}> = ({ runId, onExpand, summaryStatus }) => {
  const { data: progress } = useRunProgress(runId);
  const { layout } = usePipelineLayout();

  const rawSteps = (progress?.steps ?? []) as CollapsedStep[];
  const isTerminal = isTerminalRunStatus(progress?.run_status);

  const summaryStep: CollapsedStep | null =
    isTerminal && summaryStatus
      ? {
          code: "summary_generation",
          title: "Построение резюме",
          status: summaryStatus === "ready" ? "completed" : summaryStatus === "generating" || summaryStatus === "pending" ? "running" : "pending",
        }
      : null;

  const steps = summaryStep ? [...rawSteps, summaryStep] : rawSteps;

  const stepByCode = React.useMemo(() => {
    const map = new Map<string, CollapsedStep>();
    for (const s of steps) map.set(s.code, s);
    return map;
  }, [steps]);

  const orderedCodes = React.useMemo(() => {
    if (layout.order.length > 0) return layout.order;
    return steps.map((s) => s.code);
  }, [layout.order, steps]);

  const iconsAreaHeightPx = React.useMemo(() => {
    let maxBottom = 0;
    for (const code of orderedCodes) {
      const entry = layout.entries[code];
      if (entry) {
        const bottom = entry.top + entry.height;
        if (bottom > maxBottom) maxBottom = bottom;
      }
    }
    if (maxBottom > 0) return maxBottom;

    const n = orderedCodes.length;
    if (n === 0) return 0;
    return COLLAPSED_FALLBACK_TOP_OFFSET_PX + (n - 1) * COLLAPSED_FALLBACK_STEP_GAP_PX + COLLAPSED_BADGE_HEIGHT_PX;
  }, [layout.entries, orderedCodes]);

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col">
      <p className="mb-2 shrink-0 text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">Пайплайн</p>

      <button
        type="button"
        onClick={onExpand}
        title="Нажмите, чтобы развернуть детали пайплайна"
        aria-label="Развернуть детали пайплайна"
        className="group min-h-0 flex-1 overflow-y-auto overscroll-contain rounded-xl border border-[var(--border)] bg-[var(--bg-card)] p-0 text-left transition-colors hover:border-[var(--accent-primary)] hover:bg-[var(--bg-elevated-soft)]"
      >
        {orderedCodes.length === 0 ? (
          <p className="px-3 py-3 text-[10px] text-[var(--text-muted)]">—</p>
        ) : (
          <div className="relative w-full">
            <span className="absolute left-1/2 top-2 -translate-x-1/2 rounded-md p-1 text-[var(--text-muted)] transition-colors group-hover:text-[var(--accent-primary)]" aria-hidden>
              <ChevronRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
            </span>

            <div
              className="flex w-full flex-col items-center justify-between"
              style={{
                paddingTop: `${COLLAPSED_RAIL_TOP_PADDING_PX}px`,
                paddingBottom: `${COLLAPSED_RAIL_TOP_PADDING_PX}px`,
                minHeight: `${Math.max(iconsAreaHeightPx + COLLAPSED_RAIL_TOP_PADDING_PX * 2, orderedCodes.length * COLLAPSED_BADGE_HEIGHT_PX + (orderedCodes.length - 1) * 16)}px`,
              }}
            >
              {orderedCodes.map((code) => {
                const step = stepByCode.get(code);
                if (!step) return null;
                return <CollapsedStepBadge key={code} step={step} />;
              })}
            </div>
          </div>
        )}
      </button>
    </div>
  );
};

// ---------------------------------------------------------------------------
// НОВЫЙ КОМПОНЕНТ: Collapsed Summary Rail (аналог пайплайна)
// ---------------------------------------------------------------------------

const CollapsedSummaryRail: React.FC<{
  onExpand: () => void;
  hasErrors?: boolean;
}> = ({ onExpand, hasErrors = false }) => {
  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col">
      <p className="mb-2 shrink-0 text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">Резюме</p>

      <button
        type="button"
        onClick={onExpand}
        title="Нажмите, чтобы развернуть резюме"
        aria-label="Развернуть резюме"
        className={`group min-h-0 flex-1 overflow-hidden rounded-xl border p-0 text-left transition-colors ${
          hasErrors
            ? "border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] hover:border-[var(--color-warning)]"
            : "border-[var(--border)] bg-[var(--bg-card)] hover:border-[var(--accent-primary)] hover:bg-[var(--bg-elevated-soft)]"
        }`}
      >
        <div className="flex h-full w-full flex-col items-center justify-center gap-2 py-4">
          <div
            className={`flex h-10 w-10 items-center justify-center rounded-full transition-colors ${
              hasErrors
                ? "bg-[var(--color-warning)] text-white"
                : "bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] group-hover:bg-[var(--accent-primary)] group-hover:text-white"
            }`}
          >
            <FileText className="h-5 w-5" />
          </div>
          <ChevronRight className="h-3.5 w-3.5 text-[var(--text-muted)] transition-transform group-hover:translate-x-0.5" />
        </div>
      </button>
    </div>
  );
};

// ---------------------------------------------------------------------------
// DocumentsContent Main Logic
// ---------------------------------------------------------------------------

const DocumentsContent: React.FC<{ runId: string | null; dealId: string }> = ({ runId, dealId }) => {
  const [isPipelineExpanded, setIsPipelineExpanded] = React.useState(false);
  const [isSummaryExpanded, setIsSummaryExpanded] = React.useState(false);
  const [isMobilePipelineOpen, setIsMobilePipelineOpen] = React.useState(false);

  const { data: progress } = useRunProgress(runId);
  const isTerminal = isTerminalRunStatus(progress?.run_status);
  const isRunActive = !!runId && !isTerminal;

  const { data: summary, refetch: refetchSummary } = useRunSummary(runId);

  // Авто-разворачивание резюме при готовности
  React.useEffect(() => {
    if (isTerminal && summary?.status === "ready") {
      setIsPipelineExpanded(false);
      setIsSummaryExpanded(true);
    }
  }, [isTerminal, summary?.status]);

  React.useEffect(() => {
    if (!isTerminal) {
      setIsPipelineExpanded(false);
      setIsSummaryExpanded(false);
    }
  }, [isTerminal]);

  const { data: llmUsage, isLoading: llmLoading, isError: llmError } = useDealLLMUsage(dealId, {
    refetchInterval: isRunActive ? 30_000 : false,
  });

  const { data: documentsPage, isLoading: documentsLoading, isError: documentsError } = useDocuments(dealId, 1);
  const documents = documentsPage?.items;

  const documentNames = React.useMemo<Record<string, string>>(() => {
    const map: Record<string, string> = {};
    for (const doc of documents ?? []) {
      if (doc.id && doc.filename) map[doc.id] = doc.filename;
    }
    return map;
  }, [documents]);

  return (
    <>
      {/* ── xl+ : активный run → pipeline на всю ширину ── */}
      {!isTerminal && (
        <div className="hidden h-full min-h-0 xl:block">
          <div className="flex h-full min-h-0 flex-col">
            <p className="mb-2 shrink-0 text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">Пайплайн анализа</p>
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1">
              <DocumentsPipelinePanel runId={runId} />
            </div>
          </div>
        </div>
      )}

      {/* ── xl+ : terminal + expanded pipeline ── */}
      {isTerminal && isPipelineExpanded && (
        <div className="hidden h-full min-h-0 xl:flex xl:flex-col">
          <div className="mb-2 flex shrink-0 items-center justify-between gap-3">
            <p className="text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">Пайплайн анализа · подробности</p>
            <button
              type="button"
              onClick={() => setIsPipelineExpanded(false)}
              className="rounded-lg border border-[var(--border)] bg-[var(--bg-card)] px-3 py-1.5 text-[11px] text-[var(--text-muted)] transition hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)]"
            >
              Свернуть пайплайн
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1">
            <DocumentsPipelinePanel runId={runId} />
          </div>
        </div>
      )}

      {/* ── xl+ : terminal + collapsed pipeline + summary logic ── */}
      {isTerminal && !isPipelineExpanded && (
        <div
          className="hidden h-full min-h-0 grid-rows-[minmax(0,1fr)] gap-4 xl:grid"
          style={{
            gridTemplateColumns: isSummaryExpanded
              ? "minmax(72px,72px) minmax(0,3fr)"
              : "minmax(72px,72px) minmax(72px,72px) minmax(0,1fr) minmax(0,1fr) minmax(0,1fr)",
          }}
        >
          {/* Колонка 1: Пайплайн */}
          <div className="flex h-full min-h-0 flex-col">
            <div className="h-full flex flex-col">
              <CollapsedPipelineSummary
                runId={runId}
                onExpand={() => setIsPipelineExpanded(true)}
                summaryStatus={summary?.status ?? null}
              />
            </div>
          </div>

          {/* Колонки 2+: Логика Резюме */}
          {isSummaryExpanded ? (
            <div className="flex h-full min-h-0 flex-col">
              <div className="h-full flex flex-col">
                {summary && (
                  <RunSummaryPanel
                    summary={summary}
                    onRegenerate={() => refetchSummary()}
                    onClose={() => setIsSummaryExpanded(false)}
                    documents={documents}
                    dealId={dealId}
                  />
                )}
              </div>
            </div>
          ) : (
            <>
              {/* Колонка 2: Summary Rail */}
              <div className="flex h-full min-h-0 flex-col">
                <div className="h-full flex flex-col">
                  <CollapsedSummaryRail
                    onExpand={() => setIsSummaryExpanded(true)}
                    hasErrors={summary?.status === "failed"}
                  />
                </div>
              </div>
              
              {/* Колонка 3: Обзор документов */}
              <ColumnShell title="Обзор документов">
                <DocumentsOverviewWidget documents={documents} isLoading={documentsLoading} isError={documentsError} />
              </ColumnShell>
              
              {/* Колонка 4: Итог анализа */}
              <ColumnShell title="Итог анализа">
                <AnalysisResultsWidget dealId={dealId} runId={runId} />
              </ColumnShell>
              
              {/* Колонка 5: Использование LLM */}
              <ColumnShell title="Использование LLM">
                <LLMUsageWidget data={llmUsage} isLoading={llmLoading} isError={llmError} documentNames={documentNames} />
              </ColumnShell>
            </>
          )}
        </div>
      )}

      {/* ── < xl : stacked fallback ── */}
      <div className="grid min-h-0 grid-cols-1 gap-4 xl:hidden lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className="min-w-0">
          <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
            <button
              type="button"
              onClick={() => setIsMobilePipelineOpen((prev) => !prev)}
              aria-expanded={isMobilePipelineOpen}
              aria-controls="mobile-pipeline-content"
              className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition hover:bg-[var(--bg-elevated-soft)]"
            >
              <span className="text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">Пайплайн анализа</span>
              <ChevronDown
                className={["h-4 w-4 shrink-0 text-[var(--text-muted)] transition-transform duration-200", isMobilePipelineOpen ? "rotate-180" : ""].join(" ")}
                aria-hidden
              />
            </button>


            {isMobilePipelineOpen && (
              <>
                <div className="mx-4 border-t border-[var(--border-subtle)]" />
                <div id="mobile-pipeline-content" className="px-4 py-3">
                  <DocumentsPipelinePanel runId={runId} />
                </div>
              </>
            )}
          </section>
        </div>


        {isTerminal && (
          <div className="min-w-0 space-y-4">
            {summary && (
              <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
                <button
                  type="button"
                  onClick={() => setIsSummaryExpanded((prev) => !prev)}
                  aria-expanded={isSummaryExpanded}
                  aria-controls="mobile-summary-content"
                  className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition hover:bg-[var(--bg-elevated-soft)]"
                >
                  <span className="text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">Резюме</span>
                  <ChevronDown
                    className={["h-4 w-4 shrink-0 text-[var(--text-muted)] transition-transform duration-200", isSummaryExpanded ? "rotate-180" : ""].join(" ")}
                    aria-hidden
                  />
                </button>

                {isSummaryExpanded && (
                  <>
                    <div className="mx-4 border-t border-[var(--border-subtle)]" />
                    <div id="mobile-summary-content" className="px-4 py-3">
                      <RunSummaryPanel
                        summary={summary}
                        onRegenerate={() => refetchSummary()}
                        onClose={() => setIsSummaryExpanded(false)}
                        documents={documents}
                        dealId={dealId}
                      />
                    </div>
                  </>
                )}
              </section>
            )}
            <div>
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">Обзор документов</p>
              <DocumentsOverviewWidget documents={documents} isLoading={documentsLoading} isError={documentsError} />
            </div>
            <div>
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">Итог анализа</p>
              <AnalysisResultsWidget dealId={dealId} runId={runId} />
            </div>
            <div>
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">Использование LLM</p>
              <LLMUsageWidget data={llmUsage} isLoading={llmLoading} isError={llmError} documentNames={documentNames} />
            </div>
          </div>
        )}
      </div>
    </>
  );
};

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

export const ProjectDomainDetailsPanel: React.FC<ProjectDomainDetailsPanelProps> = ({ activeDomain, onDomainChange: _onDomainChange, runId, deal }) => {
  const domainLabel = getDomainLabel(activeDomain);

  return (
    <section className="flex flex-col lg:h-full lg:min-h-0 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm xl:rounded-t-none xl:border-t-0">
      <div className="relative flex flex-col text-[var(--text-primary)] lg:min-h-0 lg:flex-1">
        
        {/* Header: shrink-0 */}
        <div className="shrink-0 px-5">
          <div className="py-3">
            <div className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--accent-primary)]" aria-hidden />
              <span className="text-xs font-semibold text-[var(--accent-primary)]">{domainLabel}</span>
              <ChevronRight className="h-3 w-3 shrink-0 text-[var(--text-muted)]" aria-hidden />
              <h2 className="text-sm font-semibold text-[var(--text-primary)]">Детали результатов анализа</h2>
            </div>
          </div>
          <div className="border-t border-[var(--border-subtle)]" />
        </div>

        {/* Content: строгий десктопный контракт, на мобильном течёт естественно */}
        <div className="px-5 py-4 lg:min-h-0 lg:flex-1 lg:overflow-hidden">
          {activeDomain === "documents" && (
            <PipelineLayoutProvider>
              <DocumentsContent runId={runId} dealId={deal.id} />
            </PipelineLayoutProvider>
          )}
          {activeDomain === "counterparties" && (
            <div className="lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:overscroll-contain">
              <CounterpartiesSummary />
            </div>
          )}
          {activeDomain === "real_estate" && (
            <div className="lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:overscroll-contain">
              <RealEstateSummary />
            </div>
          )}
        </div>
      </div>
    </section>
  );
};

export default ProjectDomainDetailsPanel;



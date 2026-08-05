// =============================================================
// src/pages/tabs/overview/ProjectDomainDetailsPanel.tsx
// Переключаемая панель деталей по направлению.
//
// Documents (xl+): 4-колоночный layout, каждая колонка = 1/4 ширины,
//                  одинаковая высота, внутренний скролл.
//   1. Пайплайн анализа
//   2. Обзор документов (с встроенным блоком "Требует внимания")
//   3. Итог анализа (с встроенным блоком "Результаты, требующие уточнения")
//   4. Использование LLM
//
// Documents (< xl):  fallback 2-колоночный layout (legacy).
// Counterparties / RealEstate: одна колонка, как раньше.
// =============================================================

import React from "react";
import type { Deal } from "../../../types";
import DocumentsPipelinePanel from "./DocumentsPipelinePanel";
import { LLMUsageWidget } from "./LLMUsageWidget";
import { DocumentsOverviewWidget } from "./DocumentsOverviewWidget";
import { AnalysisResultsWidget } from "./AnalysisResultsWidget";
import { useDealLLMUsage } from "../../../api/deals";
import { useDocuments } from "../../../api/documents";
import { DEMO_AGGREGATES } from "../CounterpartiesTab";
import { DEMO_OBJECTS } from "../RealEstateTab";

type DomainKey = "documents" | "counterparties" | "real_estate";

interface ProjectDomainDetailsPanelProps {
  activeDomain: DomainKey;
  onDomainChange: (d: DomainKey) => void;
  runId: string | null;
  deal: Deal;
}

// ---------------------------------------------------------------------------
// Column shell (общий стиль для 4-колоночного layout)
// ---------------------------------------------------------------------------

interface ColumnShellProps {
  title: string;
  children: React.ReactNode;
}

const ColumnShell: React.FC<ColumnShellProps> = ({ title, children }) => (
  <div className="flex min-h-0 min-w-0 flex-col">
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
            <div
              key={country}
              className="flex items-center justify-between gap-2"
            >
              <span className="text-xs text-[var(--text-primary)]">
                {country}
              </span>
              <span className="text-[11px] tabular-nums text-[var(--text-muted)]">
                {count}
              </span>
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
    (item) =>
      item.ownership_status === "review" ||
      item.ownership_status === "not_confirmed",
  );
  const highRisk = DEMO_OBJECTS.filter((item) => item.risk === "high");

  const regionMap = new Map<string, number>();
  for (const item of DEMO_OBJECTS) {
    regionMap.set(item.region, (regionMap.get(item.region) ?? 0) + 1);
  }
  const topRegions = [...regionMap.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4);

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-xl border border-[var(--border)] px-3 py-2.5">
          <p className="text-[10px] text-[var(--text-muted)]">Объектов</p>
          <p className="mt-0.5 text-lg font-semibold tabular-nums text-[var(--text-primary)]">
            {DEMO_OBJECTS.length}
          </p>
        </div>
        <div className="rounded-xl border border-[var(--border)] px-3 py-2.5">
          <p className="text-[10px] text-[var(--text-muted)]">
            С обременением
          </p>
          <p className="mt-0.5 text-lg font-semibold tabular-nums text-[var(--color-error-text)]">
            {encumbered.length}
          </p>
        </div>
        <div className="rounded-xl border border-[var(--border)] px-3 py-2.5">
          <p className="text-[10px] text-[var(--text-muted)]">
            Ownership review
          </p>
          <p className="mt-0.5 text-lg font-semibold tabular-nums text-[var(--color-warning-text)]">
            {ownershipReview.length}
          </p>
        </div>
        <div className="rounded-xl border border-[var(--border)] px-3 py-2.5">
          <p className="text-[10px] text-[var(--text-muted)]">Высокий риск</p>
          <p className="mt-0.5 text-lg font-semibold tabular-nums text-[var(--color-error-text)]">
            {highRisk.length}
          </p>
        </div>
      </div>

      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-2.5">
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--text-muted)]">
          Топ регионов
        </p>
        <div className="space-y-1.5">
          {topRegions.map(([region, count]) => (
            <div
              key={region}
              className="flex items-center justify-between gap-2"
            >
              <span className="text-xs text-[var(--text-primary)]">
                {region}
              </span>
              <span className="text-[11px] tabular-nums text-[var(--text-muted)]">
                {count}
              </span>
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
// DocumentsContent — 4-колоночный layout на xl+, fallback на меньших
// ---------------------------------------------------------------------------

const DocumentsContent: React.FC<{
  runId: string | null;
  dealId: string;
  isRunActive: boolean;
}> = ({ runId, dealId, isRunActive }) => {
  const {
    data: llmUsage,
    isLoading: llmLoading,
    isError: llmError,
  } = useDealLLMUsage(dealId, {
    refetchInterval: isRunActive ? 30_000 : false,
  });

  const {
    data: documentsPage,
    isLoading: documentsLoading,
    isError: documentsError,
  } = useDocuments(dealId, 1);

  const documents = documentsPage?.items;

  return (
    <>
      {/* ── xl+ : 4 колонки, одинаковая высота, скролл внутри каждой ── */}
      <div className="hidden h-full min-h-0 grid-cols-4 gap-4 xl:grid">
        <ColumnShell title="Пайплайн анализа">
          <DocumentsPipelinePanel runId={runId} />
        </ColumnShell>

        <ColumnShell title="Обзор документов">
          <DocumentsOverviewWidget
            documents={documents}
            isLoading={documentsLoading}
            isError={documentsError}
          />
        </ColumnShell>

        <ColumnShell title="Итог анализа">
          <AnalysisResultsWidget dealId={dealId} runId={runId} />
        </ColumnShell>

        <ColumnShell title="Использование LLM">
          <LLMUsageWidget
            data={llmUsage}
            isLoading={llmLoading}
            isError={llmError}
          />
        </ColumnShell>
      </div>

      {/* ── < xl : fallback — двухколоночный layout с новыми виджетами ── */}
      <div className="grid min-h-0 grid-cols-1 gap-4 xl:hidden lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className="min-w-0">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">
            Пайплайн анализа
          </p>
          <DocumentsPipelinePanel runId={runId} />
        </div>

        <div className="min-w-0 space-y-4">
          <div>
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">
              Обзор документов
            </p>
            <DocumentsOverviewWidget
              documents={documents}
              isLoading={documentsLoading}
              isError={documentsError}
            />
          </div>

          <div>
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">
              Итог анализа
            </p>
            <AnalysisResultsWidget dealId={dealId} runId={runId} />
          </div>

          <div>
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">
              Использование LLM
            </p>
            <LLMUsageWidget
              data={llmUsage}
              isLoading={llmLoading}
              isError={llmError}
            />
          </div>
        </div>
      </div>
    </>
  );
};

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

export const ProjectDomainDetailsPanel: React.FC<
  ProjectDomainDetailsPanelProps
> = ({ activeDomain, onDomainChange: _onDomainChange, runId, deal }) => {
  const domainTitle =
    activeDomain === "documents"
      ? "Документы"
      : activeDomain === "counterparties"
        ? "Контрагенты"
        : "Имущество";

  const isRunActive = !!runId;

  return (
    <section className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
      {/* Header */}
      <div className="shrink-0 px-5">
        <div className="py-3">
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">
            Детали результатов анализа
          </h2>
          <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
            {domainTitle}
          </p>
        </div>
        <div className="border-t border-[var(--border-subtle)]" />
      </div>

      {/* Content */}
      <div className="min-h-0 flex-1 overflow-hidden px-5 py-4">
        {activeDomain === "documents" && (
          <DocumentsContent
            runId={runId}
            dealId={deal.id}
            isRunActive={isRunActive}
          />
        )}
        {activeDomain === "counterparties" && (
          <div className="h-full overflow-y-auto overscroll-contain">
            <CounterpartiesSummary />
          </div>
        )}
        {activeDomain === "real_estate" && (
          <div className="h-full overflow-y-auto overscroll-contain">
            <RealEstateSummary />
          </div>
        )}
      </div>
    </section>
  );
};

export default ProjectDomainDetailsPanel;


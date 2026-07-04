// =============================================================
// src/pages/tabs/overview/ProjectDomainDetailsPanel.tsx
// Переключаемая панель деталей по направлению.
// =============================================================

import React from "react";
import type { Deal } from "../../../types";
import { DocumentsPipelinePanel } from "./DocumentsPipelinePanel";
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
// Counterparties summary (берём данные из DEMO_AGGREGATES)
// ---------------------------------------------------------------------------

const CounterpartiesSummary: React.FC = () => {
  const critical = DEMO_AGGREGATES.filter(
    (item) => item.reviewStatus === "critical"
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
          <p className="mt-0.5 text-lg font-semibold tabular-nums text-[var(--color-error)]">
            {critical.length}
          </p>
        </div>
        <div className="rounded-xl border border-[var(--border)] px-3 py-2.5">
          <p className="text-[10px] text-[var(--text-muted)]">Санкции</p>
          <p className="mt-0.5 text-lg font-semibold tabular-nums text-[var(--color-error)]">
            {sanctions.length}
          </p>
        </div>
        <div className="rounded-xl border border-[var(--border)] px-3 py-2.5">
          <p className="text-[10px] text-[var(--text-muted)]">Банкротство</p>
          <p className="mt-0.5 text-lg font-semibold tabular-nums text-[var(--color-warning)]">
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
// Real estate summary (берём данные из DEMO_OBJECTS)
// ---------------------------------------------------------------------------

const RealEstateSummary: React.FC = () => {
  const encumbered = DEMO_OBJECTS.filter((item) => item.encumbrance === true);
  const ownershipReview = DEMO_OBJECTS.filter(
    (item) =>
      item.ownership_status === "review" ||
      item.ownership_status === "not_confirmed"
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
          <p className="text-[10px] text-[var(--text-muted)]">С обременением</p>
          <p className="mt-0.5 text-lg font-semibold tabular-nums text-[var(--color-error)]">
            {encumbered.length}
          </p>
        </div>
        <div className="rounded-xl border border-[var(--border)] px-3 py-2.5">
          <p className="text-[10px] text-[var(--text-muted)]">Ownership review</p>
          <p className="mt-0.5 text-lg font-semibold tabular-nums text-[var(--color-warning)]">
            {ownershipReview.length}
          </p>
        </div>
        <div className="rounded-xl border border-[var(--border)] px-3 py-2.5">
          <p className="text-[10px] text-[var(--text-muted)]">Высокий риск</p>
          <p className="mt-0.5 text-lg font-semibold tabular-nums text-[var(--color-error)]">
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
            <div key={region} className="flex items-center justify-between gap-2">
              <span className="text-xs text-[var(--text-primary)]">{region}</span>
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
// Main
// ---------------------------------------------------------------------------

export const ProjectDomainDetailsPanel: React.FC<
  ProjectDomainDetailsPanelProps
> = ({ activeDomain, onDomainChange: _onDomainChange, runId }) => {
  const domainTitle =
    activeDomain === "documents"
      ? "Документы"
      : activeDomain === "counterparties"
        ? "Контрагенты"
        : "Имущество";

  return (
    <section className="flex h-full min-h-0 flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
      {/* Header */}
      <div className="shrink-0 px-5">
        <div className="py-3">
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">
            Детали направления
          </h2>
          <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
            {domainTitle}
          </p>
        </div>
        <div className="border-t border-[var(--border-subtle)]" />
      </div>

      {/* Scrollable content */}
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-4">
        {activeDomain === "documents" && (
          <DocumentsPipelinePanel runId={runId} />
        )}
        {activeDomain === "counterparties" && <CounterpartiesSummary />}
        {activeDomain === "real_estate" && <RealEstateSummary />}
      </div>
    </section>
  );
};

export default ProjectDomainDetailsPanel;


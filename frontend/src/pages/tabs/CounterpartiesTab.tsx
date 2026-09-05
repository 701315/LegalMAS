// =============================================================
// src/pages/tabs/CounterpartiesTab.tsx
// Counterparty Analysis & Risk Screening tab.
//
// Preview flow:
// 1) Intro screen — section overview and data sources
// 2) Demo screen  — overview + shared split-view workspace
// =============================================================

import React, { useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  ChevronDown,
  ChevronLeft,
  ChevronUp,
  ChevronsUpDown,
  Link2,
  Search,
  ShieldCheck,
} from "lucide-react";

import Button from "../../components/ui/Button";
import PageSection from "../../components/ui/PageSection";

import {
  COVERAGE_ROWS,
  DEMO_AGGREGATES,
  DEMO_DETAILS,
} from "./counterparties/constants";
import type {
  CounterpartiesTabProps,
  CounterpartyAggregate,
  CounterpartyDetail,
  DrilldownKind,
  ExportFormat,
  ExportMenuKind,
  PreviewMode,
  SortKey,
  SortState,
} from "./counterparties/types";
import {
  buildCountryStructure,
  buildCounterpartiesTotals,
  buildCriticalCounterparties,
  buildRiskMeta,
  buildTopByContracts,
  buildTopByValue,
  getAriaSort,
  getNextSortState,
  reviewLabel,
  reviewTone,
  riskBadgeLabel,
  riskBadgeTone,
  sortCounterparties,
} from "./counterparties/utils";

// ---------------------------------------------------------------------------
// Shared UI primitives
// ---------------------------------------------------------------------------

const FeatureCard: React.FC<{
  icon: React.ReactNode;
  title: string;
  description: string;
}> = ({ icon, title, description }) => (
  <div className="flex h-full flex-col gap-3 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 shadow-sm">
    <div className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--accent-primary)]">
      {icon}
    </div>
    <div>
      <p className="text-sm font-semibold text-[var(--text-primary)]">{title}</p>
      <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">{description}</p>
    </div>
  </div>
);

const Badge: React.FC<{
  children: React.ReactNode;
  tone?: "neutral" | "success" | "high" | "medium" | "low";
}> = ({ children, tone = "neutral" }) => {
  const toneClass = {
    neutral:
      "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)]",
    success:
      "border-[var(--accent-primary)] bg-[var(--accent-muted)] text-[var(--accent-primary)]",
    high: "status-border-error status-bg-error status-text-error",
    medium: "status-border-warning status-bg-warning status-text-warning",
    low: "status-border-success status-bg-success status-text-success",
  }[tone];

  return (
    <span
      className={[
        "inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium",
        toneClass,
      ].join(" ")}
    >
      {children}
    </span>
  );
};

const KpiCard: React.FC<{
  label: string;
  value: string;
  hint?: string;
  accent?: boolean;
  onClick?: () => void;
}> = ({ label, value, hint, accent = false, onClick }) => {
  const isInteractive = typeof onClick === "function";

  const content = (
    <>
      <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
        {label}
      </p>
      <p
        className={[
          "mt-1 text-2xl font-semibold tabular-nums",
          accent ? "text-[var(--color-error-text)]" : "text-[var(--text-primary)]",
          isInteractive
            ? "underline decoration-transparent transition group-hover:decoration-current"
            : "",
        ].join(" ")}
      >
        {value}
      </p>
      {hint ? (
        <p className="mt-1 text-[11px] leading-5 text-[var(--text-muted)]">{hint}</p>
      ) : null}
    </>
  );

  if (!isInteractive) {
    return (
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 shadow-sm">
        {content}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      className="group rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 text-left shadow-sm transition hover:bg-[var(--bg-elevated-soft)]"
    >
      {content}
    </button>
  );
};

const RankedListCard: React.FC<{
  title: string;
  items: Array<{
    name: string;
    country: string;
    value: string;
  }>;
}> = ({ title, items }) => (
  <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
    <div className="border-b border-[var(--border-subtle)] px-4 py-3">
      <p className="text-sm font-semibold text-[var(--text-primary)]">{title}</p>
    </div>
    <div className="divide-y divide-[var(--border-subtle)]">
      {items.map((item, index) => (
        <div key={`${item.name}-${index}`} className="flex items-center gap-3 px-4 py-3">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--bg-elevated-soft)] text-[12px] font-semibold text-[var(--text-primary)]">
            {index + 1}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-[var(--text-primary)]">{item.name}</p>
            <p className="text-[12px] text-[var(--text-muted)]">{item.country}</p>
          </div>
          <div className="shrink-0 text-sm font-semibold tabular-nums text-[var(--text-primary)]">
            {item.value}
          </div>
        </div>
      ))}
    </div>
  </div>
);

const CountryStructureCard: React.FC<{
  items: Array<{
    country: string;
    count: number;
  }>;
}> = ({ items }) => {
  const total = items.reduce((sum, item) => sum + item.count, 0);

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
      <div className="space-y-3 px-4 py-4">
        {items.map((item) => {
          const share = total > 0 ? Math.round((item.count / total) * 100) : 0;
          return (
            <div key={item.country}>
              <div className="mb-1 flex items-center justify-between gap-3">
                <p className="text-sm text-[var(--text-primary)]">{item.country}</p>
                <p className="text-[12px] font-medium tabular-nums text-[var(--text-muted)]">
                  {item.count} · {share}%
                </p>
              </div>
              <div className="h-2 rounded-full bg-[var(--bg-elevated-soft)]">
                <div
                  className="h-2 rounded-full bg-[var(--accent-primary)]"
                  style={{ width: `${share}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const CriticalCounterpartiesTable: React.FC<{
  items: Array<{
    name: string;
    country: string;
    reasons: string[];
  }>;
}> = ({ items }) => {
  const { t } = useTranslation("counterparties");

  return (
    <div className="overflow-hidden rounded-2xl border border-[var(--border)]">
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-[var(--bg-elevated-soft)]">
            <tr>
              <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">{t("drilldown.criticalTable.counterparty")}</th>
              <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">{t("drilldown.criticalTable.country")}</th>
              <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">
                {t("drilldown.criticalTable.reasons")}
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.name} className="border-t border-[var(--border-subtle)] align-top">
                <td className="px-4 py-3 font-medium text-[var(--text-primary)]">{item.name}</td>
                <td className="px-4 py-3 text-[var(--text-secondary)]">{item.country}</td>
                <td className="px-4 py-3 text-[var(--text-secondary)]">
                  <ul className="space-y-1">
                    {item.reasons.map((reason) => (
                      <li key={reason} className="flex gap-2">
                        <span className="mt-[8px] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-error)]" />
                        <span>{reason}</span>
                      </li>
                    ))}
                  </ul>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const DrilldownModal: React.FC<{
  title: string;
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
}> = ({ title, open, onClose, children }) => {
  const { t } = useTranslation("counterparties");
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 px-4 py-6">
      <div className="max-h-[85vh] w-full max-w-4xl overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-2xl">
        <div className="flex items-center justify-between gap-4 border-b border-[var(--border-subtle)] px-5 py-4">
          <div>
            <h3 className="text-base font-semibold text-[var(--text-primary)]">{title}</h3>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              {t("drilldown.subtitle")}
            </p>
          </div>
          <Button variant="secondary" size="sm" onClick={onClose}>
            {t("drilldown.close")}
          </Button>
        </div>
        <div className="max-h-[calc(85vh-84px)] overflow-y-auto px-5 py-4">{children}</div>
      </div>
    </div>
  );
};

const ExportMenuButton: React.FC<{
  label: string;
  open: boolean;
  onToggle: () => void;
  onSelect: (format: ExportFormat) => void;
}> = ({ label, open, onToggle, onSelect }) => {
  const { t } = useTranslation("counterparties");

  return (
    <div className="relative">
      <Button
        variant="secondary"
        size="sm"
        onClick={onToggle}
        rightIcon={
          <ChevronDown
            className={`h-4 w-4 transition-transform duration-200 ${
              open ? "rotate-180" : "rotate-0"
            }`}
            aria-hidden
          />
        }
        aria-expanded={open}
        aria-haspopup="menu"
      >
        {label}
      </Button>

      {open ? (
        <div className="absolute right-0 top-[calc(100%+8px)] z-20 min-w-[160px] overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-xl">
          <div className="border-b border-[var(--border-subtle)] px-4 py-3">
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {t("export.formatLabel")}
            </p>
          </div>
          <div className="p-2">
            {[
              { key: "excel", label: "Excel" },
              { key: "docx", label: "Docx" },
              { key: "pdf", label: "Pdf" },
            ].map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => onSelect(item.key as ExportFormat)}
                className="flex w-full items-center rounded-xl px-3 py-2 text-left text-sm text-[var(--text-primary)] transition hover:bg-[var(--bg-elevated-soft)]"
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Intro screen
// ---------------------------------------------------------------------------

const IntroScreen: React.FC<{
  onOpenDemo: () => void;
}> = ({ onOpenDemo }) => {
  const { t } = useTranslation("counterparties");

  const coverageRows = useMemo(() => {
    const localized = t("coverageRows", { returnObjects: true });
    if (Array.isArray(localized) && localized.length > 0) {
      return localized;
    }
    return COVERAGE_ROWS;
  }, [t]);

  return (
    <div className="flex flex-col lg:h-full lg:min-h-0 lg:overflow-hidden">
      <div className="lg:min-h-0 lg:flex-1 lg:overflow-y-auto pr-1">
        <div className="space-y-4">
          <PageSection
            title={t("intro.title")}
            subtitle={t("intro.subtitle")}
            rightSlot={<Badge tone="success">{t("intro.preview")}</Badge>}
          >
            <p className="max-w-4xl text-sm leading-6 text-[var(--text-secondary)]">
              {t("intro.description")}
            </p>
          </PageSection>

          <PageSection
            title={t("intro.howItWorks.title")}
            subtitle={t("intro.howItWorks.subtitle")}
          >
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              <FeatureCard
                icon={<Search className="h-5 w-5" aria-hidden />}
                title={t("intro.howItWorks.detection.title")}
                description={t("intro.howItWorks.detection.description")}
              />
              <FeatureCard
                icon={<Link2 className="h-5 w-5" aria-hidden />}
                title={t("intro.howItWorks.verification.title")}
                description={t("intro.howItWorks.verification.description")}
              />
              <FeatureCard
                icon={<ShieldCheck className="h-5 w-5" aria-hidden />}
                title={t("intro.howItWorks.legal.title")}
                description={t("intro.howItWorks.legal.description")}
              />
            </div>
          </PageSection>

          <PageSection
            title={t("intro.dataSources.title")}
            subtitle={t("intro.dataSources.subtitle")}
          >
            <div className="overflow-hidden rounded-2xl border border-[var(--border)]">
              <div className="overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-[var(--bg-elevated-soft)]">
                    <tr>
                      <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">{t("intro.dataSources.headers.region")}</th>
                      <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">
                        {t("intro.dataSources.headers.global")}
                      </th>
                      <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">
                        {t("intro.dataSources.headers.local")}
                      </th>
                      <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">
                        {t("intro.dataSources.headers.internal")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {coverageRows.map((row) => (
                      <tr
                        key={row.region}
                        className="border-t border-[var(--border-subtle)] align-top"
                      >
                        <td className="px-4 py-3 text-[var(--text-primary)]">{row.region}</td>
                        <td className="px-4 py-3 text-[var(--text-secondary)]">
                          {row.globalProviders}
                        </td>
                        <td className="px-4 py-3 text-[var(--text-secondary)]">
                          {row.localSources}
                        </td>
                        <td className="px-4 py-3 text-[var(--text-secondary)]">
                          {row.internalSources}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </PageSection>
        </div>
      </div>

      <div className="mt-4 shrink-0 border-t border-[var(--border-subtle)] pb-2 pt-4">
        <Button
          variant="primary"
          size="md"
          onClick={onOpenDemo}
          className="w-full sm:w-auto"
        >
          {t("intro.cta")}
        </Button>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Table header
// ---------------------------------------------------------------------------

const SortableHeader: React.FC<{
  label: string;
  sortKey: SortKey;
  currentSort: SortState;
  onSort: (key: SortKey) => void;
  className?: string;
}> = ({ label, sortKey, currentSort, onSort, className = "" }) => {
  const { t } = useTranslation("counterparties");
  const isActive = currentSort.key === sortKey;
  const isAscending = isActive && currentSort.direction === "asc";
  const isDescending = isActive && currentSort.direction === "desc";

  const SortIcon = isAscending ? ChevronUp : isDescending ? ChevronDown : ChevronsUpDown;

  return (
    <th
      scope="col"
      className={["px-4 py-3 font-semibold text-[var(--text-primary)]", className].join(" ")}
      aria-sort={getAriaSort(currentSort, sortKey)}
    >
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className="inline-flex items-center gap-2 text-left transition hover:text-[var(--accent-primary)]"
        title={t("table.sortTitle", { label })}
      >
        <span>{label}</span>
        <SortIcon
          className={`h-3 w-3 ${
            isActive ? "text-[var(--accent-primary)]" : "text-[var(--text-muted)]"
          }`}
          aria-hidden
        />
      </button>
    </th>
  );
};

// ---------------------------------------------------------------------------
// Counterparties table
// ---------------------------------------------------------------------------

const CounterpartiesTable: React.FC<{
  items: CounterpartyAggregate[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  sort: SortState;
  onSort: (key: SortKey) => void;
}> = ({ items, selectedId, onSelect, sort, onSort }) => {
  const { t } = useTranslation("counterparties");

  return (
    <div className="overflow-x-auto rounded-2xl border border-[var(--border)] lg:h-full lg:min-h-0 lg:overflow-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="bg-[var(--bg-elevated-soft)] lg:sticky lg:top-0 lg:z-10">
          <tr>
            <SortableHeader
              label={t("table.headers.index")}
              sortKey="index"
              currentSort={sort}
              onSort={onSort}
              className="w-14"
            />
            <SortableHeader
              label={t("table.headers.name")}
              sortKey="name"
              currentSort={sort}
              onSort={onSort}
            />
            <SortableHeader
              label={t("table.headers.country")}
              sortKey="country"
              currentSort={sort}
              onSort={onSort}
            />
            <SortableHeader
              label={t("table.headers.contractCount")}
              sortKey="contractCount"
              currentSort={sort}
              onSort={onSort}
            />
            <SortableHeader
              label={t("table.headers.contractValue")}
              sortKey="contractValueUsdM"
              currentSort={sort}
              onSort={onSort}
            />
            <SortableHeader
              label={t("table.headers.risk")}
              sortKey="risk"
              currentSort={sort}
              onSort={onSort}
            />
          </tr>
        </thead>
        <tbody>
          {items.map((item, index) => {
            const isSelected = item.id === selectedId;
            const risk = buildRiskMeta(item);

            return (
              <tr
                key={item.id}
                className={[
                  "border-t border-[var(--border-subtle)] transition",
                  isSelected
                    ? "bg-[color:color-mix(in_srgb,var(--accent-primary)_7%,var(--bg-card))]"
                    : "hover:bg-[var(--bg-elevated-soft)]",
                ].join(" ")}
              >
                <td className="px-4 py-3 tabular-nums text-[var(--text-muted)]">{index + 1}</td>
                <td className="px-4 py-3">
                  <button
                    type="button"
                    onClick={() => onSelect(item.id)}
                    className="text-left text-sm font-medium text-[var(--accent-primary)] underline decoration-transparent transition hover:decoration-current"
                  >
                    {item.name}
                  </button>
                </td>
                <td className="px-4 py-3 text-[var(--text-secondary)]">{item.country}</td>
                <td className="px-4 py-3 tabular-nums text-[var(--text-primary)]">
                  {item.contractCount}
                </td>
                <td className="px-4 py-3 tabular-nums text-[var(--text-primary)]">
                  ${item.contractValueUsdM}m
                </td>
                <td className="px-4 py-3">
                  <Badge tone={risk.tone}>{t(`labels.${risk.label}`)}</Badge>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Detail panel
// ---------------------------------------------------------------------------

const DetailPanel: React.FC<{
  aggregate: CounterpartyAggregate;
  detail: CounterpartyDetail;
}> = ({ aggregate, detail }) => {
  const { t } = useTranslation("counterparties");

  return (
    <div className="space-y-4">
      <PageSection
        title={t("detail.card.title")}
        subtitle={t("detail.card.subtitle")}
        rightSlot={
          <Badge tone={reviewTone(aggregate.reviewStatus)}>
            {t(`labels.${reviewLabel(aggregate.reviewStatus)}`)}
          </Badge>
        }
      >
        <div className="space-y-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-base font-semibold text-[var(--text-primary)]">
                {aggregate.name}
              </p>
              <Badge>{aggregate.country}</Badge>
            </div>
            <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
              {detail.shortDescription}
            </p>
          </div>
        </div>
      </PageSection>

      <PageSection
        title={t("detail.documents.title")}
        subtitle={t("detail.documents.subtitle")}
      >
        <div className="space-y-3">
          {detail.contracts.map((contract) => (
            <div
              key={contract.id}
              className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 shadow-sm"
            >
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm font-semibold text-[var(--text-primary)]">
                  {contract.title}
                </p>
                <Badge>{contract.contractType}</Badge>
                <Badge>{contract.section}</Badge>
              </div>
              <div className="mt-2 flex flex-wrap gap-4 text-sm text-[var(--text-secondary)]">
                <span>
                  <span className="font-medium text-[var(--text-primary)]">{t("detail.documents.role")}</span>{" "}
                  {contract.mentionRole}
                </span>
                <span>
                  <span className="font-medium text-[var(--text-primary)]">{t("detail.documents.value")}</span>{" "}
                  {contract.contractValueUsdM != null ? `$${contract.contractValueUsdM}m` : "—"}
                </span>
              </div>
            </div>
          ))}
        </div>
      </PageSection>

      <PageSection
        title={t("detail.financials.title")}
        subtitle={t("detail.financials.subtitle")}
      >
        <div className="grid grid-cols-2 gap-3">
          <KpiCard
            label={t("detail.financials.revenue")}
            value={detail.financials.revenue}
            hint={`${detail.financials.fiscalYear} · ${detail.financials.currency}`}
          />
          <KpiCard label={t("detail.financials.ebitda")} value={detail.financials.ebitda} />
          <KpiCard label={t("detail.financials.assets")} value={detail.financials.totalAssets} />
          <KpiCard label={t("detail.financials.employees")} value={`${detail.financials.employees}`} />
        </div>
      </PageSection>

      <PageSection title={t("detail.risks.title")} subtitle={t("detail.risks.subtitle")}>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {(
            [
              { label: t("detail.risks.types.bankruptcy"), key: "bankruptcy" },
              { label: t("detail.risks.types.sanctions"), key: "sanctions" },
              { label: t("detail.risks.types.litigation"), key: "litigation" },
            ] as const
          ).map(({ label, key }) => (
            <div key={key} className="rounded-2xl border border-[var(--border)] px-4 py-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                {label}
              </p>
              <div className="mt-2">
                <Badge tone={riskBadgeTone(detail.risks[key])}>
                  {t(`labels.${riskBadgeLabel(detail.risks[key])}`)}
                </Badge>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-4 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 shadow-sm">
          <p className="text-sm font-semibold text-[var(--text-primary)]">{t("detail.risks.notes")}</p>
          <ul className="mt-2 space-y-2 text-sm leading-6 text-[var(--text-secondary)]">
            {detail.risks.notes.map((note) => (
              <li key={note} className="flex gap-2">
                <span className="mt-[8px] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-warning)]" />
                <span>{note}</span>
              </li>
            ))}
          </ul>
        </div>
      </PageSection>

      <PageSection
        title={t("detail.ownership.title")}
        subtitle={t("detail.ownership.subtitle")}
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="rounded-2xl border border-[var(--border)] px-4 py-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {t("detail.ownership.owner")}
            </p>
            <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
              {detail.ownership.ownerName}
            </p>
            <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
              {detail.ownership.ownerType} · {detail.ownership.ownerJurisdiction}
              {detail.ownership.ownerShare ? ` · ${detail.ownership.ownerShare}` : ""}
            </p>
          </div>

          <div className="rounded-2xl border border-[var(--border)] px-4 py-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {t("detail.ownership.ubo")}
            </p>
            <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
              {detail.ownership.uboName}
            </p>
            <div className="mt-2">
              <Badge
                tone={
                  detail.ownership.uboSanctionsStatus === "match"
                    ? "high"
                    : detail.ownership.uboSanctionsStatus === "review"
                      ? "medium"
                      : "low"
                }
              >
                {detail.ownership.uboSanctionsStatus === "match"
                  ? t("detail.ownership.statusMatch")
                  : detail.ownership.uboSanctionsStatus === "review"
                    ? t("detail.ownership.statusReview")
                    : t("detail.ownership.statusClear")}
              </Badge>
            </div>
          </div>
        </div>

        <div className="mt-4 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 shadow-sm">
          <p className="text-sm font-semibold text-[var(--text-primary)]">{t("detail.ownership.note")}</p>
          <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
            {detail.ownership.ownershipNote}
          </p>
        </div>
      </PageSection>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Mobile fullscreen drawer
// ---------------------------------------------------------------------------

const MobileDetailDrawer: React.FC<{
  aggregate: CounterpartyAggregate;
  detail: CounterpartyDetail;
  onClose: () => void;
}> = ({ aggregate, detail, onClose }) => {
  const { t } = useTranslation("counterparties");

  React.useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  React.useEffect(() => {
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = originalOverflow;
    };
  }, []);

  return (
    <div className="lg:hidden">
      <div
        className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden
      />

      <aside
        className="fixed inset-0 z-50 flex flex-col bg-[var(--bg-card)]"
        role="dialog"
        aria-modal="true"
        aria-labelledby="cp-mobile-drawer-title"
      >
        <div className="flex min-h-14 shrink-0 items-center justify-between gap-3 border-b border-[var(--border-subtle)] px-4">
          <Button
            variant="secondary"
            size="sm"
            onClick={onClose}
            leftIcon={<ChevronLeft className="h-4 w-4" aria-hidden />}
          >
            {t("drawer.back")}
          </Button>

          <div
            id="cp-mobile-drawer-title"
            className="truncate text-sm font-semibold text-[var(--text-primary)]"
          >
            {aggregate.name}
          </div>

          <div className="w-[80px] shrink-0" aria-hidden />
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain bg-[var(--bg-base)] p-4">
          <DetailPanel aggregate={aggregate} detail={detail} />
        </div>
      </aside>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Demo screen
// ---------------------------------------------------------------------------

const DemoScreen: React.FC<{
  onBack: () => void;
}> = ({ onBack }) => {
  const { t } = useTranslation("counterparties");
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [drilldown, setDrilldown] = React.useState<DrilldownKind>(null);
  const [openExportMenu, setOpenExportMenu] = React.useState<ExportMenuKind>(null);
  const [sort, setSort] = React.useState<SortState>({
    key: "index",
    direction: "asc",
  });

  // Localize country names in demo aggregates
  const localizedAggregates = React.useMemo(() => {
    return DEMO_AGGREGATES.map((agg) => {
      const countryEn = t(`demoData.countries.${agg.country}`, { defaultValue: agg.country });
      return { ...agg, country: countryEn };
    });
  }, [t]);

  const { totalCounterparties, totalContracts, totalContractValue } = React.useMemo(
    () => buildCounterpartiesTotals(localizedAggregates),
    [localizedAggregates]
  );

  const topByContracts = React.useMemo(() => buildTopByContracts(localizedAggregates), [localizedAggregates]);
  const topByValue = React.useMemo(() => buildTopByValue(localizedAggregates), [localizedAggregates]);
  const countryStructure = React.useMemo(() => buildCountryStructure(localizedAggregates), [localizedAggregates]);
  const criticalCounterparties = React.useMemo(
    () => buildCriticalCounterparties(localizedAggregates),
    [localizedAggregates]
  );

  const sortedAggregates = React.useMemo(
    () => sortCounterparties(localizedAggregates, sort),
    [localizedAggregates, sort]
  );

  const selectedAggregate = selectedId
    ? localizedAggregates.find((item) => item.id === selectedId) ?? null
    : null;

  const selectedDetail = selectedAggregate ? DEMO_DETAILS[selectedAggregate.id] ?? null : null;

  const handleExport = (format: ExportFormat) => {
    setOpenExportMenu(null);
    window.alert(t("export.alert", { format: format.toUpperCase() }));
  };

  const handleSort = (key: SortKey) => {
    setSort((prev) => getNextSortState(prev, key));
  };

  const drilldownTitle =
    drilldown === "geography"
      ? t("drilldown.geography")
      : drilldown === "contracts_top"
        ? t("drilldown.contractsTop")
        : drilldown === "value_top"
          ? t("drilldown.valueTop")
          : t("drilldown.critical");

  return (
    <div className="flex min-h-0 flex-col lg:h-full lg:overflow-hidden">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-[var(--text-primary)]">
            {t("demo.title")}
          </h2>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            {t("demo.subtitle")}
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={onBack}>
          {t("demo.back")}
        </Button>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3 xl:grid-cols-4">
        <KpiCard
          label={t("demo.kpi.totalCounterparties")}
          value={`${totalCounterparties}`}
          hint={t("demo.kpi.hintGeography")}
          onClick={() => setDrilldown("geography")}
        />
        <KpiCard
          label={t("demo.kpi.totalContracts")}
          value={`${totalContracts}`}
          hint={t("demo.kpi.hintTop")}
          onClick={() => setDrilldown("contracts_top")}
        />
        <KpiCard
          label={t("demo.kpi.totalValue")}
          value={`$${totalContractValue}m`}
          hint={t("demo.kpi.hintTop")}
          onClick={() => setDrilldown("value_top")}
        />
        <KpiCard
          label={t("demo.kpi.critical")}
          value={`${criticalCounterparties.length}`}
          hint={t("demo.kpi.hintList")}
          accent
          onClick={() => setDrilldown("critical")}
        />
      </div>

      <div className="min-h-0 flex-1">
        {selectedAggregate && selectedDetail ? (
          <div className="hidden lg:block lg:h-full">
            <PageSection
              title={t("demo.workspace.title")}
              subtitle={t("demo.workspace.subtitle")}
              rightSlot={
                <div className="flex items-center gap-2">
                  <ExportMenuButton
                    label={t("export.saveList")}
                    open={openExportMenu === "list"}
                    onToggle={() =>
                      setOpenExportMenu((prev) => (prev === "list" ? null : "list"))
                    }
                    onSelect={handleExport}
                  />
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => setSelectedId(null)}
                  >
                    {t("demo.workspace.closeCard")}
                  </Button>
                </div>
              }
              className="h-full"
              contentClassName="p-0"
              bodyClassName="h-full min-h-0"
            >
              <div className="grid min-h-0 grid-cols-1 lg:h-full xl:grid-cols-[minmax(0,1.1fr)_minmax(420px,560px)]">
                <div className="min-h-0 lg:overflow-hidden border-b border-[var(--border-subtle)] xl:border-b-0 xl:border-r">
                  <div className="flex h-full min-h-0 flex-col p-5">
                    <div className="mb-4 shrink-0">
                      <p className="text-sm font-semibold text-[var(--text-primary)]">
                        {t("demo.workspace.listTitle")}
                      </p>
                      <p className="mt-1 text-sm text-[var(--text-muted)]">
                        {t("demo.workspace.selectHint")}
                      </p>
                    </div>

                    <div className="min-h-0 flex-1">
                      <CounterpartiesTable
                        items={sortedAggregates}
                        selectedId={selectedId}
                        onSelect={setSelectedId}
                        sort={sort}
                        onSort={handleSort}
                      />
                    </div>
                  </div>
                </div>

                <div className="min-h-0 lg:overflow-y-auto">
                  <div className="p-5">
                    <DetailPanel
                      aggregate={selectedAggregate}
                      detail={selectedDetail}
                    />
                  </div>
                </div>
              </div>
            </PageSection>
          </div>
        ) : null}

        {(!selectedAggregate || !selectedDetail) && (
          <div className="hidden lg:block lg:h-full">
            <PageSection
              title={t("demo.fallback.title")}
              subtitle={t("demo.fallback.subtitle")}
              rightSlot={
                <ExportMenuButton
                  label={t("export.saveList")}
                  open={openExportMenu === "list"}
                  onToggle={() =>
                    setOpenExportMenu((prev) => (prev === "list" ? null : "list"))
                  }
                  onSelect={handleExport}
                />
              }
              className="h-full"
              bodyClassName="flex h-full min-h-0 flex-col"
            >
              <div className="mb-3 shrink-0">
                <p className="text-sm text-[var(--text-secondary)]">
                  {t("demo.fallback.demoHintDesktop")}
                </p>
              </div>
              <div className="min-h-0 flex-1 lg:overflow-hidden">
                <CounterpartiesTable
                  items={sortedAggregates}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                  sort={sort}
                  onSort={handleSort}
                />
              </div>
            </PageSection>
          </div>
        )}

        <div className="lg:hidden">
          <PageSection
            title={t("demo.fallback.title")}
            subtitle={t("demo.fallback.subtitle")}
            rightSlot={
              <ExportMenuButton
                label={t("export.saveList")}
                open={openExportMenu === "list"}
                onToggle={() =>
                  setOpenExportMenu((prev) => (prev === "list" ? null : "list"))
                }
                onSelect={handleExport}
              />
            }
          >
            <div className="mb-3">
              <p className="text-sm text-[var(--text-secondary)]">
                {t("demo.fallback.demoHintMobile")}
              </p>
            </div>
            <CounterpartiesTable
              items={sortedAggregates}
              selectedId={selectedId}
              onSelect={setSelectedId}
              sort={sort}
              onSort={handleSort}
            />
          </PageSection>
        </div>
      </div>

      {selectedAggregate && selectedDetail ? (
        <MobileDetailDrawer
          aggregate={selectedAggregate}
          detail={selectedDetail}
          onClose={() => setSelectedId(null)}
        />
      ) : null}

      <DrilldownModal
        open={drilldown !== null}
        onClose={() => setDrilldown(null)}
        title={drilldownTitle}
      >
        {drilldown === "geography" ? (
          <CountryStructureCard items={countryStructure} />
        ) : drilldown === "contracts_top" ? (
          <RankedListCard title={t("drilldown.contractsTop")} items={topByContracts} />
        ) : drilldown === "value_top" ? (
          <RankedListCard title={t("drilldown.valueTop")} items={topByValue} />
        ) : (
          <CriticalCounterpartiesTable items={criticalCounterparties} />
        )}
      </DrilldownModal>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

const CounterpartiesTab: React.FC<CounterpartiesTabProps> = ({
  dealId: _dealId,
  currentRunId: _currentRunId,
}) => {
  const [mode, setMode] = React.useState<PreviewMode>("intro");

  return (
    <div className="flex flex-col lg:h-full lg:min-h-0 lg:overflow-hidden">
      {mode === "intro" ? (
        <IntroScreen onOpenDemo={() => setMode("demo")} />
      ) : (
        <DemoScreen onBack={() => setMode("intro")} />
      )}
    </div>
  );
};

export default CounterpartiesTab;



// =============================================================
// src/pages/tabs/CounterpartiesTab.tsx
// Вкладка «Анализ выявленных контрагентов».
//
// Preview flow:
// 1) Intro screen — короткое описание раздела
// 2) Demo screen  — overview + shared split-view workspace
//
// TODO при подключении API:
// - подключить useCounterparties(dealId, currentRunId)
// - заменить demo-данные на backend DTO
// - привязать summary / table / detail panel к реальному enrichment
// - заменить alert() на реальный export flow
// =============================================================

import React from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type CounterpartyType = "legal_entity" | "individual" | "unknown";
type PreviewMode = "intro" | "demo";
type DrilldownKind = "geography" | "contracts_top" | "value_top" | "critical" | null;
type ExportMenuKind = "list" | null;
type ExportFormat = "excel" | "docx" | "pdf";
type SortDirection = "asc" | "desc";
type SortKey = "index" | "name" | "country" | "contractCount" | "contractValueUsdM" | "risk";

interface SortState {
  key: SortKey;
  direction: SortDirection;
}

interface CoverageRow {
  region: string;
  globalProviders: string;
  localSources: string;
  internalSources: string;
}

export interface CounterpartyAggregate {
  id: string;
  name: string;
  type: CounterpartyType;
  country: string;
  contractCount: number;
  contractValueUsdM: number;
  annualRevenueUsdM: number;
  bankruptcyFlag: boolean;
  sanctionsFlag: boolean;
  litigationFlag: boolean;
  reviewStatus: "critical" | "needs_review" | "normal";
}

interface MentionedContract {
  id: string;
  title: string;
  contractType: string;
  section: string;
  mentionRole: string;
  contractValueUsdM?: number | null;
}

interface CounterpartyDetail {
  id: string;
  shortDescription: string;
  contracts: MentionedContract[];
  financials: {
    fiscalYear: string;
    currency: string;
    revenue: string;
    ebitda: string;
    totalAssets: string;
    employees: number;
  };
  risks: {
    bankruptcy: "yes" | "no" | "review";
    sanctions: "yes" | "no" | "review";
    litigation: "yes" | "no" | "review";
    notes: string[];
  };
  ownership: {
    ownerName: string;
    ownerType: string;
    ownerJurisdiction: string;
    ownerShare?: string | null;
    uboName: string;
    uboSanctionsStatus: "match" | "no_match" | "review";
    ownershipNote: string;
  };
}

interface CounterpartiesTabProps {
  dealId: string;
  currentRunId: string | null;
}

// ---------------------------------------------------------------------------
// Demo data
// ---------------------------------------------------------------------------

const COVERAGE_ROWS: CoverageRow[] = [
  {
    region: "UAE",
    globalProviders: "Orbis, D&B, OpenCorporates",
    localSources: "DED / emirate registries / DIFC / free zones",
    internalSources: "ERP, vendor master, compliance DB",
  },
  {
    region: "Turkey",
    globalProviders: "Orbis, D&B",
    localSources: "MERSIS / trade registry",
    internalSources: "ERP, CRM, historical matters",
  },
  {
    region: "Saudi Arabia",
    globalProviders: "Orbis, D&B",
    localSources: "Commercial Register / Ministry of Commerce",
    internalSources: "Compliance DB, internal watchlists",
  },
  {
    region: "Oman / Qatar",
    globalProviders: "Orbis, D&B, OpenCorporates",
    localSources: "Commercial and ministry registries",
    internalSources: "Vendor records, internal DD notes",
  },
  {
    region: "Europe",
    globalProviders: "Orbis, D&B, OpenCorporates",
    localSources: "National company registers",
    internalSources: "CRM, archived transactions, legal notes",
  },
];

const BASE_AGGREGATES: CounterpartyAggregate[] = [
  {
    id: "1",
    name: "Falcon Industrial Holdings LLC",
    type: "legal_entity",
    country: "UAE",
    contractCount: 7,
    contractValueUsdM: 120,
    annualRevenueUsdM: 48.2,
    bankruptcyFlag: false,
    sanctionsFlag: false,
    litigationFlag: true,
    reviewStatus: "needs_review",
  },
  {
    id: "2",
    name: "Anatolia Infrastructure Trading A.Ş.",
    type: "legal_entity",
    country: "Turkey",
    contractCount: 6,
    contractValueUsdM: 42,
    annualRevenueUsdM: 31.5,
    bankruptcyFlag: false,
    sanctionsFlag: false,
    litigationFlag: false,
    reviewStatus: "normal",
  },
  {
    id: "3",
    name: "Pearl Industrial Services LLC",
    type: "legal_entity",
    country: "Oman",
    contractCount: 5,
    contractValueUsdM: 78,
    annualRevenueUsdM: 12.8,
    bankruptcyFlag: false,
    sanctionsFlag: false,
    litigationFlag: false,
    reviewStatus: "critical",
  },
  {
    id: "4",
    name: "Desert Bridge Advisors Ltd",
    type: "legal_entity",
    country: "Qatar",
    contractCount: 4,
    contractValueUsdM: 9,
    annualRevenueUsdM: 6.4,
    bankruptcyFlag: false,
    sanctionsFlag: false,
    litigationFlag: false,
    reviewStatus: "normal",
  },
  {
    id: "5",
    name: "Nordic Industrial Components GmbH",
    type: "legal_entity",
    country: "Germany",
    contractCount: 4,
    contractValueUsdM: 215,
    annualRevenueUsdM: 38,
    bankruptcyFlag: false,
    sanctionsFlag: false,
    litigationFlag: true,
    reviewStatus: "critical",
  },
  {
    id: "6",
    name: "Blue River Procurement SAS",
    type: "legal_entity",
    country: "France",
    contractCount: 3,
    contractValueUsdM: 14,
    annualRevenueUsdM: 18,
    bankruptcyFlag: false,
    sanctionsFlag: true,
    litigationFlag: false,
    reviewStatus: "critical",
  },
  {
    id: "7",
    name: "Baltic Terminal Solutions Sp. z o.o.",
    type: "legal_entity",
    country: "Poland",
    contractCount: 2,
    contractValueUsdM: 11,
    annualRevenueUsdM: 9.5,
    bankruptcyFlag: true,
    sanctionsFlag: false,
    litigationFlag: false,
    reviewStatus: "critical",
  },
  {
    id: "8",
    name: "Atlas Energy Equipment LLC",
    type: "legal_entity",
    country: "UAE",
    contractCount: 5,
    contractValueUsdM: 26,
    annualRevenueUsdM: 54,
    bankruptcyFlag: false,
    sanctionsFlag: false,
    litigationFlag: false,
    reviewStatus: "normal",
  },
];

const EXTRA_AGGREGATES: CounterpartyAggregate[] = Array.from({ length: 22 }).map((_, index) => {
  const countries = [
    "UAE",
    "Turkey",
    "Saudi Arabia",
    "Oman",
    "Qatar",
    "Germany",
    "France",
    "Italy",
    "Spain",
    "Netherlands",
    "Poland",
    "Belgium",
  ];
  const country = countries[index % countries.length];
  const num = index + 9;
  const contractCount = 2 + (index % 6);
  const contractValueUsdM = 8 + index * 4;
  const annualRevenueUsdM = 12 + index * 2.5;

  return {
    id: String(num),
    name: `Demo Counterparty ${num} ${country}`,
    type: "legal_entity" as const,
    country,
    contractCount,
    contractValueUsdM,
    annualRevenueUsdM,
    bankruptcyFlag: index % 13 === 0,
    sanctionsFlag: index % 17 === 0,
    litigationFlag: index % 5 === 0,
    reviewStatus:
      index % 9 === 0 ? "critical" : index % 4 === 0 ? "needs_review" : "normal",
  };
});

export const DEMO_AGGREGATES: CounterpartyAggregate[] = [
  ...BASE_AGGREGATES,
  ...EXTRA_AGGREGATES,
];

const BASE_DETAILS: Record<string, CounterpartyDetail> = {
  "1": {
    id: "1",
    shortDescription:
      "Regional industrial holding and service platform supporting procurement, logistics and transitional operational functions across UAE-based group companies.",
    contracts: [
      { id: "c-1", title: "Share Purchase Agreement Draft", contractType: "SPA", section: "1.1 Definitions", mentionRole: "Affiliate", contractValueUsdM: 35 },
      { id: "c-2", title: "Transitional Services Agreement", contractType: "TSA", section: "Parties / Service Scope", mentionRole: "Service provider", contractValueUsdM: 28 },
      { id: "c-3", title: "Disclosure Letter", contractType: "Disclosure", section: "Related Party Arrangements", mentionRole: "Related-party service provider", contractValueUsdM: 12 },
      { id: "c-4", title: "Procurement Framework Agreement", contractType: "Commercial", section: "Annex 2", mentionRole: "Supplier", contractValueUsdM: 45 },
    ],
    financials: { fiscalYear: "FY2024", currency: "USD", revenue: "48.2m", ebitda: "7.6m", totalAssets: "61.4m", employees: 126 },
    risks: {
      bankruptcy: "no",
      sanctions: "no",
      litigation: "review",
      notes: [
        "Related-party exposure requires legal review.",
        "Litigation screening produced unresolved commercial dispute references.",
        "Cross-border payment flows should be reviewed together with service scope.",
      ],
    },
    ownership: {
      ownerName: "Falcon Group Holding SPC",
      ownerType: "Corporate shareholder",
      ownerJurisdiction: "UAE",
      ownerShare: "78%",
      uboName: "Ahmad Al Mansoori",
      uboSanctionsStatus: "no_match",
      ownershipNote:
        "Ownership chain appears stable in the demo scenario; UBO screening did not produce a sanctions match, but final confirmation should rely on live provider data.",
    },
  },
  "2": {
    id: "2",
    shortDescription:
      "Turkish commercial counterparty acting as a recurring infrastructure customer under multi-year framework purchasing arrangements.",
    contracts: [
      { id: "c-5", title: "Revenue Concentration Memo", contractType: "Finance memo", section: "Top accounts", mentionRole: "Key customer", contractValueUsdM: 18 },
      { id: "c-6", title: "Commercial Agreement Summary", contractType: "Summary", section: "Annex 4", mentionRole: "Customer", contractValueUsdM: 11 },
      { id: "c-7", title: "Disclosure Letter", contractType: "Disclosure", section: "Major Customers", mentionRole: "Customer", contractValueUsdM: 13 },
    ],
    financials: { fiscalYear: "FY2024", currency: "USD", revenue: "31.5m", ebitda: "4.1m", totalAssets: "22.7m", employees: 74 },
    risks: {
      bankruptcy: "no",
      sanctions: "no",
      litigation: "no",
      notes: [
        "No material red flags in demo scenario.",
        "Entity appears proportionate to contract exposure and operating profile.",
      ],
    },
    ownership: {
      ownerName: "Anatolia Capital Partners",
      ownerType: "Corporate shareholder",
      ownerJurisdiction: "Turkey",
      ownerShare: "61%",
      uboName: "Murat Demir",
      uboSanctionsStatus: "no_match",
      ownershipNote:
        "No elevated ownership concerns in preview scenario; UBO screening does not indicate sanctions exposure.",
    },
  },
  "3": {
    id: "3",
    shortDescription:
      "Omani contractor involved in field operations and legacy service arrangements with possible related-party characteristics.",
    contracts: [
      { id: "c-8", title: "Transitional Services Agreement", contractType: "TSA", section: "Parties", mentionRole: "Contractor", contractValueUsdM: 24 },
      { id: "c-9", title: "Procurement Exceptions Memo", contractType: "Memo", section: "Section 3", mentionRole: "Service contractor", contractValueUsdM: 19 },
      { id: "c-10", title: "Field Operations Support Contract", contractType: "Services", section: "Pricing Schedule", mentionRole: "Operations contractor", contractValueUsdM: 35 },
    ],
    financials: { fiscalYear: "FY2024", currency: "USD", revenue: "12.8m", ebitda: "1.3m", totalAssets: "9.2m", employees: 48 },
    risks: {
      bankruptcy: "no",
      sanctions: "no",
      litigation: "review",
      notes: [
        "Aggregate contract value materially exceeds annual revenue threshold.",
        "Potential related-party characteristics require enhanced review.",
        "Litigation and commercial dispute screening should be checked manually.",
      ],
    },
    ownership: {
      ownerName: "Pearl Energy Holdings SPC",
      ownerType: "Corporate shareholder",
      ownerJurisdiction: "Oman",
      ownerShare: "82%",
      uboName: "Salim Al Harthy",
      uboSanctionsStatus: "no_match",
      ownershipNote:
        "Ownership appears concentrated; no sanctions match detected for named UBO in the preview scenario.",
    },
  },
  "4": {
    id: "4",
    shortDescription:
      "Qatar-based advisory entity supporting transaction structuring, external coordination and market-facing workstreams.",
    contracts: [
      { id: "c-11", title: "Board Consent", contractType: "Corporate approval", section: "Annex 1", mentionRole: "Advisor", contractValueUsdM: 4 },
      { id: "c-12", title: "Engagement Letter Summary", contractType: "Advisory", section: "Scope", mentionRole: "Advisor", contractValueUsdM: 5 },
    ],
    financials: { fiscalYear: "FY2024", currency: "USD", revenue: "6.4m", ebitda: "1.1m", totalAssets: "4.8m", employees: 19 },
    risks: {
      bankruptcy: "no",
      sanctions: "no",
      litigation: "no",
      notes: ["No material alerts in preview scenario."],
    },
    ownership: {
      ownerName: "Desert Bridge Partners WLL",
      ownerType: "Corporate shareholder",
      ownerJurisdiction: "Qatar",
      ownerShare: "67%",
      uboName: "Khalid Al Kuwari",
      uboSanctionsStatus: "no_match",
      ownershipNote:
        "Ownership is straightforward in the demo scenario; no sanctions signal was identified for the stated UBO.",
    },
  },
  "5": {
    id: "5",
    shortDescription:
      "German industrial components supplier with large-value framework contracts and elevated exposure relative to reported revenue base.",
    contracts: [
      { id: "c-13", title: "Master Supply Agreement", contractType: "Supply", section: "Commercial Terms", mentionRole: "Supplier", contractValueUsdM: 95 },
      { id: "c-14", title: "Long-Term Procurement Schedule", contractType: "Schedule", section: "Volume Commitments", mentionRole: "Core supplier", contractValueUsdM: 76 },
      { id: "c-15", title: "Manufacturing Support Addendum", contractType: "Addendum", section: "Annex B", mentionRole: "Technical supplier", contractValueUsdM: 44 },
    ],
    financials: { fiscalYear: "FY2024", currency: "USD", revenue: "38m", ebitda: "5.4m", totalAssets: "27m", employees: 93 },
    risks: {
      bankruptcy: "no",
      sanctions: "no",
      litigation: "review",
      notes: [
        "Aggregate contract value is more than five times annual revenue.",
        "Commercial capacity and dependency assumptions should be validated.",
        "Litigation references require targeted legal review.",
      ],
    },
    ownership: {
      ownerName: "Nordic Components Beteiligungs GmbH",
      ownerType: "Corporate shareholder",
      ownerJurisdiction: "Germany",
      ownerShare: "100%",
      uboName: "Stefan Kruger",
      uboSanctionsStatus: "no_match",
      ownershipNote:
        "Ownership chain is visible at group level in the demo scenario; no sanctions match identified for the named UBO.",
    },
  },
  "6": {
    id: "6",
    shortDescription:
      "French procurement intermediary used in selective sourcing workflows, with a sanctions-related alert requiring immediate review.",
    contracts: [
      { id: "c-16", title: "Procurement Support Agreement", contractType: "Services", section: "Counterparty Details", mentionRole: "Intermediary", contractValueUsdM: 8 },
      { id: "c-17", title: "Supplier Onboarding Memo", contractType: "Memo", section: "Review Notes", mentionRole: "Intermediary", contractValueUsdM: 6 },
    ],
    financials: { fiscalYear: "FY2024", currency: "USD", revenue: "18m", ebitda: "2.2m", totalAssets: "13m", employees: 41 },
    risks: {
      bankruptcy: "no",
      sanctions: "yes",
      litigation: "no",
      notes: [
        "Sanctions-related screening alert requires immediate escalation.",
        "Identity matching should be validated against live provider sources.",
      ],
    },
    ownership: {
      ownerName: "Blue River Holdings SAS",
      ownerType: "Corporate shareholder",
      ownerJurisdiction: "France",
      ownerShare: "72%",
      uboName: "Jean-Luc Martin",
      uboSanctionsStatus: "review",
      ownershipNote:
        "Ownership is identifiable, but sanctions review for the UBO should remain open until confirmed against live screening sources.",
    },
  },
  "7": {
    id: "7",
    shortDescription:
      "Polish terminal solutions provider flagged by insolvency-related screening and requiring caution despite limited contract footprint.",
    contracts: [
      { id: "c-18", title: "Terminal Equipment Supply Contract", contractType: "Supply", section: "Vendor profile", mentionRole: "Supplier", contractValueUsdM: 7 },
      { id: "c-19", title: "Operational Readiness Memo", contractType: "Memo", section: "Section 5", mentionRole: "Vendor", contractValueUsdM: 4 },
    ],
    financials: { fiscalYear: "FY2024", currency: "USD", revenue: "9.5m", ebitda: "0.8m", totalAssets: "6.1m", employees: 27 },
    risks: {
      bankruptcy: "yes",
      sanctions: "no",
      litigation: "review",
      notes: [
        "Bankruptcy / insolvency signal present in preview scenario.",
        "Counterparty should be escalated for legal and commercial review before further reliance.",
      ],
    },
    ownership: {
      ownerName: "Baltic Infrastructure Group sp. z o.o.",
      ownerType: "Corporate shareholder",
      ownerJurisdiction: "Poland",
      ownerShare: "88%",
      uboName: "Piotr Zielinski",
      uboSanctionsStatus: "no_match",
      ownershipNote:
        "No sanctions signal identified for the named UBO in the demo scenario; insolvency risk remains the primary concern.",
    },
  },
  "8": {
    id: "8",
    shortDescription:
      "UAE-based equipment provider with stable exposure profile and no elevated compliance signals in the demo scenario.",
    contracts: [
      { id: "c-20", title: "Equipment Supply Framework", contractType: "Supply", section: "Schedule 1", mentionRole: "Supplier", contractValueUsdM: 16 },
      { id: "c-21", title: "Operations Support Addendum", contractType: "Addendum", section: "Service Matrix", mentionRole: "Technical supplier", contractValueUsdM: 10 },
    ],
    financials: { fiscalYear: "FY2024", currency: "USD", revenue: "54m", ebitda: "6.7m", totalAssets: "39m", employees: 144 },
    risks: {
      bankruptcy: "no",
      sanctions: "no",
      litigation: "no",
      notes: ["No material issues detected in preview scenario."],
    },
    ownership: {
      ownerName: "Atlas Industrial Group LLC",
      ownerType: "Corporate shareholder",
      ownerJurisdiction: "UAE",
      ownerShare: "69%",
      uboName: "Yousef Al Kaabi",
      uboSanctionsStatus: "no_match",
      ownershipNote:
        "Ownership profile is uncomplicated in preview mode; UBO sanctions screening returned no match.",
    },
  },
};

const generateFallbackDetail = (aggregate: CounterpartyAggregate): CounterpartyDetail => ({
  id: aggregate.id,
  shortDescription:
    "Демонстрационная карточка для расширенного списка контрагентов. В production-режиме здесь будет показано автоматическое обогащение данных из глобальных, локальных и внутренних источников.",
  contracts: [
    {
      id: `fc-${aggregate.id}-1`,
      title: "Commercial Agreement Summary",
      contractType: "Commercial",
      section: "Counterparty section",
      mentionRole: "Counterparty",
      contractValueUsdM: Math.max(4, Math.round(aggregate.contractValueUsdM * 0.45)),
    },
    {
      id: `fc-${aggregate.id}-2`,
      title: "Disclosure Letter",
      contractType: "Disclosure",
      section: "Related matters",
      mentionRole: "Mentioned entity",
      contractValueUsdM: Math.max(2, Math.round(aggregate.contractValueUsdM * 0.2)),
    },
  ],
  financials: {
    fiscalYear: "FY2024",
    currency: "USD",
    revenue: `${aggregate.annualRevenueUsdM.toFixed(1)}m`,
    ebitda: `${Math.max(0.8, aggregate.annualRevenueUsdM * 0.14).toFixed(1)}m`,
    totalAssets: `${Math.max(5, aggregate.annualRevenueUsdM * 1.2).toFixed(1)}m`,
    employees: 35 + Number(aggregate.id),
  },
  risks: {
    bankruptcy: aggregate.bankruptcyFlag ? "yes" : "no",
    sanctions: aggregate.sanctionsFlag ? "yes" : "no",
    litigation: aggregate.litigationFlag ? "review" : "no",
    notes: [
      "Карточка сформирована на демо-данных для проверки скролла и split-view layout.",
      "В реальном режиме здесь будут provider hits, структура владения и связка с внутренними базами компании.",
    ],
  },
  ownership: {
    ownerName: `${aggregate.name} Holding Group`,
    ownerType: "Corporate shareholder",
    ownerJurisdiction: aggregate.country,
    ownerShare: "75%",
    uboName: "Demo UBO",
    uboSanctionsStatus: aggregate.sanctionsFlag ? "review" : "no_match",
    ownershipNote:
      "Демо-описание ownership chain. В боевом сценарии поле будет заполняться по результатам внешнего и внутреннего enrichment.",
  },
});

const DEMO_DETAILS: Record<string, CounterpartyDetail> = DEMO_AGGREGATES.reduce(
  (acc, item) => {
    acc[item.id] = BASE_DETAILS[item.id] ?? generateFallbackDetail(item);
    return acc;
  },
  {} as Record<string, CounterpartyDetail>
);

// ---------------------------------------------------------------------------
// Shared UI
// ---------------------------------------------------------------------------

const CardShell: React.FC<{
  title: string;
  eyebrow?: string;
  children: React.ReactNode;
  rightSlot?: React.ReactNode;
  bodyClassName?: string;
  className?: string;
}> = ({ title, eyebrow, children, rightSlot, bodyClassName = "", className = "" }) => (
  <section
    className={[
      "flex min-h-0 flex-col rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm",
      className,
    ].join(" ")}
  >
    <div className="shrink-0 px-5">
      <div className="flex items-start justify-between gap-4 py-4">
        <div className="min-w-0">
          {eyebrow ? (
            <>
              <h2 className="text-base font-semibold text-[var(--text-primary)]">{eyebrow}</h2>
              <p className="mt-1 text-sm text-[var(--text-muted)]">{title}</p>
            </>
          ) : (
            <h2 className="text-base font-semibold text-[var(--text-primary)]">{title}</h2>
          )}
        </div>
        {rightSlot}
      </div>
      <div className="border-t border-[var(--border-subtle)]" />
    </div>

    <div className={["min-h-0 flex-1 px-5 py-4", bodyClassName].join(" ")}>
      {children}
    </div>
  </section>
);

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
      "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-muted)]",
    success:
      "border-[color:color-mix(in_srgb,var(--accent-primary)_24%,transparent)] bg-[color:color-mix(in_srgb,var(--accent-primary)_10%,transparent)] text-[var(--accent-primary)]",
    high:
      "border-[color:color-mix(in_srgb,var(--color-error)_24%,transparent)] bg-[color:color-mix(in_srgb,var(--color-error)_10%,transparent)] text-[var(--color-error)]",
    medium:
      "border-[color:color-mix(in_srgb,var(--color-warning)_24%,transparent)] bg-[color:color-mix(in_srgb,var(--color-warning)_10%,transparent)] text-[var(--color-warning)]",
    low:
      "border-[color:color-mix(in_srgb,var(--color-success)_24%,transparent)] bg-[color:color-mix(in_srgb,var(--color-success)_10%,transparent)] text-[var(--color-success)]",
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

const PrimaryButton: React.FC<React.ButtonHTMLAttributes<HTMLButtonElement>> = ({
  className = "",
  children,
  ...props
}) => (
  <button
    {...props}
    className={[
      "inline-flex items-center justify-center rounded-xl bg-[var(--accent-primary)] px-4 py-2.5 text-sm font-medium text-white transition hover:opacity-95",
      className,
    ].join(" ")}
  >
    {children}
  </button>
);

const SecondaryButton: React.FC<React.ButtonHTMLAttributes<HTMLButtonElement>> = ({
  className = "",
  children,
  ...props
}) => (
  <button
    {...props}
    className={[
      "inline-flex items-center justify-center rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-2.5 text-sm font-medium text-[var(--text-primary)] transition hover:bg-[var(--bg-elevated-soft)]",
      className,
    ].join(" ")}
  >
    {children}
  </button>
);

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
          accent ? "text-[var(--color-error)]" : "text-[var(--text-primary)]",
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
}> = ({ items }) => (
  <div className="overflow-hidden rounded-2xl border border-[var(--border)]">
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="bg-[var(--bg-elevated-soft)]">
          <tr>
            <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">Контрагент</th>
            <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">Страна</th>
            <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">
              Основания критичности
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

const DrilldownModal: React.FC<{
  title: string;
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
}> = ({ title, open, onClose, children }) => {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 px-4 py-6">
      <div className="max-h-[85vh] w-full max-w-4xl overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-2xl">
        <div className="flex items-center justify-between gap-4 border-b border-[var(--border-subtle)] px-5 py-4">
          <div>
            <h3 className="text-base font-semibold text-[var(--text-primary)]">{title}</h3>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              Демонстрационный drilldown по выбранному показателю
            </p>
          </div>
          <SecondaryButton onClick={onClose}>Закрыть</SecondaryButton>
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
}> = ({ label, open, onToggle, onSelect }) => (
  <div className="relative">
    <SecondaryButton onClick={onToggle} className="gap-2">
      <span>{label}</span>
      <span className="text-[10px] text-[var(--text-muted)]">▼</span>
    </SecondaryButton>

    {open ? (
      <div className="absolute right-0 top-[calc(100%+8px)] z-20 min-w-[160px] overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-xl">
        <div className="border-b border-[var(--border-subtle)] px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Формат сохранения
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

// ---------------------------------------------------------------------------
// Sort helpers
// ---------------------------------------------------------------------------

const riskBadgeTone = (value: "yes" | "no" | "review"): "high" | "low" | "medium" => {
  if (value === "yes") return "high";
  if (value === "review") return "medium";
  return "low";
};

const riskBadgeLabel = (value: "yes" | "no" | "review"): string => {
  if (value === "yes") return "Yes";
  if (value === "review") return "Review";
  return "No";
};

const buildRiskMeta = (
  item: CounterpartyAggregate
): { label: string; tone: "high" | "medium" | "low"; rank: number } => {
  if (
    item.bankruptcyFlag ||
    item.sanctionsFlag ||
    item.contractValueUsdM > item.annualRevenueUsdM * 5
  ) {
    return { label: "Высокий", tone: "high", rank: 3 };
  }

  if (item.litigationFlag || item.reviewStatus === "needs_review") {
    return { label: "Средний", tone: "medium", rank: 2 };
  }

  return { label: "Низкий", tone: "low", rank: 1 };
};

const reviewTone = (
  value: CounterpartyAggregate["reviewStatus"]
): "high" | "medium" | "low" => {
  if (value === "critical") return "high";
  if (value === "needs_review") return "medium";
  return "low";
};

const reviewLabel = (value: CounterpartyAggregate["reviewStatus"]): string => {
  if (value === "critical") return "Critical";
  if (value === "needs_review") return "Needs review";
  return "Normal";
};

const getAriaSort = (
  sort: SortState,
  key: SortKey
): "ascending" | "descending" | "none" => {
  if (sort.key !== key) return "none";
  return sort.direction === "asc" ? "ascending" : "descending";
};

const sortIcon = (sort: SortState, key: SortKey): string => {
  if (sort.key !== key) return "↕";
  return sort.direction === "asc" ? "↑" : "↓";
};

// ---------------------------------------------------------------------------
// Icons
// ---------------------------------------------------------------------------

const IconSearch = () => (
  <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <circle cx="9" cy="9" r="6" stroke="currentColor" strokeWidth="1.5" />
    <path d="M13.5 13.5L17 17" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

const IconShield = () => (
  <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path
      d="M10 2L3.5 5v4.5c0 3.86 2.75 7.47 6.5 8.5 3.75-1.03 6.5-4.64 6.5-8.5V5L10 2z"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinejoin="round"
    />
    <path
      d="M7 10l2 2 4-4"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

const IconLink = () => (
  <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path
      d="M8.5 11.5a4.243 4.243 0 006 0l2-2a4.243 4.243 0 00-6-6L9 5"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
    <path
      d="M11.5 8.5a4.243 4.243 0 00-6 0l-2 2a4.243 4.243 0 006 6L11 15"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
  </svg>
);

// ---------------------------------------------------------------------------
// Intro screen
// ---------------------------------------------------------------------------

const IntroScreen: React.FC<{
  onOpenDemo: () => void;
}> = ({ onOpenDemo }) => {
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto pr-1">
        <div className="space-y-4">
          <CardShell
            eyebrow="Демонстрационный сценарий работы раздела"
            title="Как будет выглядеть анализ выявленных контрагентов"
            rightSlot={<Badge tone="success">Preview</Badge>}
          >
            <p className="max-w-4xl text-sm leading-6 text-[var(--text-secondary)]">
              Этот раздел будет автоматически выявлять контрагентов в документах сделки,
              сопоставлять их с внешними и внутренними источниками данных и формировать
              рабочий интерфейс для юридического и due diligence анализа.
            </p>
          </CardShell>

          <CardShell eyebrow="Как это будет работать" title="Основной сценарий обработки контрагентов">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              <FeatureCard
                icon={<IconSearch />}
                title="Выявление в документах"
                description="Система находит контрагентов в тексте, таблицах, приложениях и иных материалах сделки."
              />
              <FeatureCard
                icon={<IconLink />}
                title="Сопоставление и enrichment"
                description="Найденные сущности связываются с глобальными, локальными и внутренними источниками данных."
              />
              <FeatureCard
                icon={<IconShield />}
                title="Рабочий интерфейс анализа"
                description="Пользователь получает сводную картину, список контрагентов и detail panel по выбранной сущности."
              />
            </div>
          </CardShell>

          <CardShell eyebrow="Источники данных" title="Глобальные, локальные и внутренние провайдеры">
            <div className="overflow-hidden rounded-2xl border border-[var(--border)]">
              <div className="overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-[var(--bg-elevated-soft)]">
                    <tr>
                      <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">Регион</th>
                      <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">Глобальные</th>
                      <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">Локальные</th>
                      <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">Внутренние</th>
                    </tr>
                  </thead>
                  <tbody>
                    {COVERAGE_ROWS.map((row) => (
                      <tr key={row.region} className="border-t border-[var(--border-subtle)] align-top">
                        <td className="px-4 py-3 text-[var(--text-primary)]">{row.region}</td>
                        <td className="px-4 py-3 text-[var(--text-secondary)]">{row.globalProviders}</td>
                        <td className="px-4 py-3 text-[var(--text-secondary)]">{row.localSources}</td>
                        <td className="px-4 py-3 text-[var(--text-secondary)]">{row.internalSources}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </CardShell>
        </div>
      </div>

      <div className="mt-4 border-t border-[var(--border-subtle)] pt-4">
        <PrimaryButton onClick={onOpenDemo} className="w-full sm:w-auto">
          Перейти на демостраницу работы блока
        </PrimaryButton>
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
}> = ({ label, sortKey, currentSort, onSort, className = "" }) => (
  <th
    scope="col"
    className={["px-4 py-3 font-semibold text-[var(--text-primary)]", className].join(" ")}
    aria-sort={getAriaSort(currentSort, sortKey)}
  >
    <button
      type="button"
      onClick={() => onSort(sortKey)}
      className="inline-flex items-center gap-2 text-left transition hover:text-[var(--accent-primary)]"
      title={`Сортировать по колонке ${label}`}
    >
      <span>{label}</span>
      <span className="text-[11px] text-[var(--text-muted)]" aria-hidden="true">
        {sortIcon(currentSort, sortKey)}
      </span>
    </button>
  </th>
);

// ---------------------------------------------------------------------------
// Counterparties table
// ---------------------------------------------------------------------------

const CounterpartiesTable: React.FC<{
  items: CounterpartyAggregate[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  sort: SortState;
  onSort: (key: SortKey) => void;
}> = ({ items, selectedId, onSelect, sort, onSort }) => (
  <div className="h-full min-h-0 overflow-auto rounded-2xl border border-[var(--border)]">
    <table className="min-w-full text-left text-sm">
      <thead className="sticky top-0 z-10 bg-[var(--bg-elevated-soft)]">
        <tr>
          <SortableHeader label="№" sortKey="index" currentSort={sort} onSort={onSort} className="w-14" />
          <SortableHeader label="Название" sortKey="name" currentSort={sort} onSort={onSort} />
          <SortableHeader label="Страна" sortKey="country" currentSort={sort} onSort={onSort} />
          <SortableHeader
            label="Кол-во контрактов"
            sortKey="contractCount"
            currentSort={sort}
            onSort={onSort}
          />
          <SortableHeader
            label="Сумма контрактов"
            sortKey="contractValueUsdM"
            currentSort={sort}
            onSort={onSort}
          />
          <SortableHeader label="Оценка риска" sortKey="risk" currentSort={sort} onSort={onSort} />
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
              <td className="px-4 py-3 tabular-nums text-[var(--text-primary)]">{item.contractCount}</td>
              <td className="px-4 py-3 tabular-nums text-[var(--text-primary)]">${item.contractValueUsdM}m</td>
              <td className="px-4 py-3">
                <Badge tone={risk.tone}>{risk.label}</Badge>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  </div>
);

// ---------------------------------------------------------------------------
// Detail panel
// ---------------------------------------------------------------------------

const DetailPanel: React.FC<{
  aggregate: CounterpartyAggregate;
  detail: CounterpartyDetail;
  onClose: () => void;
}> = ({ aggregate, detail, onClose }) => (
  <div className="space-y-4">
    <CardShell
      eyebrow="Карточка контрагента"
      title="Детальная информация"
      rightSlot={
        <div className="flex items-center gap-2">
          <Badge tone={reviewTone(aggregate.reviewStatus)}>{reviewLabel(aggregate.reviewStatus)}</Badge>
          <SecondaryButton onClick={onClose} className="px-3 py-2">
            Закрыть
          </SecondaryButton>
        </div>
      }
    >
      <div className="space-y-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-base font-semibold text-[var(--text-primary)]">{aggregate.name}</p>
            <Badge>{aggregate.country}</Badge>
          </div>
          <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
            {detail.shortDescription}
          </p>
        </div>
      </div>
    </CardShell>

    <CardShell
      eyebrow="Упоминания в контрактах"
      title="Список документов и контрактов, в которых найден контрагент"
    >
      <div className="space-y-3">
        {detail.contracts.map((contract) => (
          <div
            key={contract.id}
            className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 shadow-sm"
          >
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm font-semibold text-[var(--text-primary)]">{contract.title}</p>
              <Badge>{contract.contractType}</Badge>
              <Badge>{contract.section}</Badge>
            </div>
            <div className="mt-2 flex flex-wrap gap-4 text-sm text-[var(--text-secondary)]">
              <span>
                <span className="font-medium text-[var(--text-primary)]">Role:</span> {contract.mentionRole}
              </span>
              <span>
                <span className="font-medium text-[var(--text-primary)]">Value:</span>{" "}
                {contract.contractValueUsdM != null ? `$${contract.contractValueUsdM}m` : "—"}
              </span>
            </div>
          </div>
        ))}
      </div>
    </CardShell>

    <CardShell
      eyebrow="Финансовая выжимка"
      title="Ключевые финансовые показатели по контрагенту"
    >
      <div className="grid grid-cols-2 gap-3">
        <KpiCard
          label="Revenue"
          value={detail.financials.revenue}
          hint={`${detail.financials.fiscalYear} · ${detail.financials.currency}`}
        />
        <KpiCard label="EBITDA" value={detail.financials.ebitda} />
        <KpiCard label="Assets" value={detail.financials.totalAssets} />
        <KpiCard label="Employees" value={`${detail.financials.employees}`} />
      </div>
    </CardShell>

    <CardShell eyebrow="Риски" title="Состояние банкротства, санкции и суды">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="rounded-2xl border border-[var(--border)] px-4 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Банкротство
          </p>
          <div className="mt-2">
            <Badge tone={riskBadgeTone(detail.risks.bankruptcy)}>{riskBadgeLabel(detail.risks.bankruptcy)}</Badge>
          </div>
        </div>
        <div className="rounded-2xl border border-[var(--border)] px-4 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Санкции
          </p>
          <div className="mt-2">
            <Badge tone={riskBadgeTone(detail.risks.sanctions)}>{riskBadgeLabel(detail.risks.sanctions)}</Badge>
          </div>
        </div>
        <div className="rounded-2xl border border-[var(--border)] px-4 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Суды
          </p>
          <div className="mt-2">
            <Badge tone={riskBadgeTone(detail.risks.litigation)}>{riskBadgeLabel(detail.risks.litigation)}</Badge>
          </div>
        </div>
      </div>

      <div className="mt-4 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 shadow-sm">
        <p className="text-sm font-semibold text-[var(--text-primary)]">Risk notes</p>
        <ul className="mt-2 space-y-2 text-sm leading-6 text-[var(--text-secondary)]">
          {detail.risks.notes.map((note) => (
            <li key={note} className="flex gap-2">
              <span className="mt-[8px] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-warning)]" />
              <span>{note}</span>
            </li>
          ))}
        </ul>
      </div>
    </CardShell>

    <CardShell
      eyebrow="Собственник / UBO"
      title="Ownership context и санкционная проверка UBO"
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="rounded-2xl border border-[var(--border)] px-4 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            Owner
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
            UBO
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
                ? "Sanctions match"
                : detail.ownership.uboSanctionsStatus === "review"
                  ? "Sanctions review"
                  : "No sanctions match"}
            </Badge>
          </div>
        </div>
      </div>

      <div className="mt-4 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 shadow-sm">
        <p className="text-sm font-semibold text-[var(--text-primary)]">Ownership note</p>
        <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
          {detail.ownership.ownershipNote}
        </p>
      </div>
    </CardShell>
  </div>
);

// ---------------------------------------------------------------------------
// Demo screen
// ---------------------------------------------------------------------------

const DemoScreen: React.FC<{
  onBack: () => void;
}> = ({ onBack }) => {
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [drilldown, setDrilldown] = React.useState<DrilldownKind>(null);
  const [openExportMenu, setOpenExportMenu] = React.useState<ExportMenuKind>(null);
  const [sort, setSort] = React.useState<SortState>({
    key: "index",
    direction: "asc",
  });

  const totalCounterparties = DEMO_AGGREGATES.length;
  const totalContracts = DEMO_AGGREGATES.reduce((sum, item) => sum + item.contractCount, 0);
  const totalContractValue = DEMO_AGGREGATES.reduce((sum, item) => sum + item.contractValueUsdM, 0);

  const topByContracts = [...DEMO_AGGREGATES]
    .sort((a, b) => b.contractCount - a.contractCount)
    .slice(0, 5)
    .map((item) => ({
      name: item.name,
      country: item.country,
      value: `${item.contractCount}`,
    }));

  const topByValue = [...DEMO_AGGREGATES]
    .sort((a, b) => b.contractValueUsdM - a.contractValueUsdM)
    .slice(0, 5)
    .map((item) => ({
      name: item.name,
      country: item.country,
      value: `$${item.contractValueUsdM}m`,
    }));

  const countryMap = new Map<string, number>();
  for (const item of DEMO_AGGREGATES) {
    countryMap.set(item.country, (countryMap.get(item.country) ?? 0) + 1);
  }

  const countryStructure = [...countryMap.entries()]
    .map(([country, count]) => ({ country, count }))
    .sort((a, b) => b.count - a.count);

  const criticalCounterparties = DEMO_AGGREGATES
    .map((item) => {
      const reasons: string[] = [];
      if (item.bankruptcyFlag) reasons.push("Признак банкротства / insolvency alert.");
      if (item.sanctionsFlag) reasons.push("Совпадение с санкционным screening signal.");
      if (item.contractValueUsdM > item.annualRevenueUsdM * 5) {
        reasons.push("Сумма контрактов превышает годовую выручку более чем в 5 раз.");
      }

      return reasons.length > 0
        ? {
            name: item.name,
            country: item.country,
            reasons,
          }
        : null;
    })
    .filter(Boolean) as Array<{ name: string; country: string; reasons: string[] }>;

  const sortedAggregates = React.useMemo(() => {
    const withIndex = DEMO_AGGREGATES.map((item, index) => ({
      ...item,
      originalIndex: index + 1,
      risk: buildRiskMeta(item),
    }));

    const sorted = [...withIndex].sort((a, b) => {
      let comparison = 0;

      switch (sort.key) {
        case "index":
          comparison = a.originalIndex - b.originalIndex;
          break;
        case "name":
          comparison = a.name.localeCompare(b.name);
          break;
        case "country":
          comparison = a.country.localeCompare(b.country);
          break;
        case "contractCount":
          comparison = a.contractCount - b.contractCount;
          break;
        case "contractValueUsdM":
          comparison = a.contractValueUsdM - b.contractValueUsdM;
          break;
        case "risk":
          comparison = a.risk.rank - b.risk.rank;
          break;
        default:
          comparison = 0;
      }

      return sort.direction === "asc" ? comparison : -comparison;
    });

    return sorted.map(({ risk: _risk, originalIndex: _originalIndex, ...item }) => item);
  }, [sort]);

  const selectedAggregate = selectedId
    ? DEMO_AGGREGATES.find((item) => item.id === selectedId) ?? null
    : null;

  const selectedDetail = selectedAggregate ? DEMO_DETAILS[selectedAggregate.id] : null;

  const handleExport = (format: ExportFormat) => {
    setOpenExportMenu(null);
    window.alert(`Сохранить список контрагентов: ${format.toUpperCase()}`);
  };

  const handleSort = (key: SortKey) => {
    setSort((prev) => {
      if (prev.key === key) {
        return {
          key,
          direction: prev.direction === "asc" ? "desc" : "asc",
        };
      }

      return {
        key,
        direction: "asc",
      };
    });
  };

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-[var(--text-primary)]">Выявленные контрагенты</h2>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            Агрегированное представление по результатам анализа контрактов и связанных источников
          </p>
        </div>
        <SecondaryButton onClick={onBack}>Назад к описанию</SecondaryButton>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3 xl:grid-cols-4">
        <KpiCard
          label="Выявлено контрагентов"
          value={`${totalCounterparties}`}
          hint="Нажмите, чтобы открыть географию"
          onClick={() => setDrilldown("geography")}
        />
        <KpiCard
          label="Контрактов с контрагентами"
          value={`${totalContracts}`}
          hint="Нажмите, чтобы открыть топ-5"
          onClick={() => setDrilldown("contracts_top")}
        />
        <KpiCard
          label="Сумма контрактов"
          value={`$${totalContractValue}m`}
          hint="Нажмите, чтобы открыть топ-5"
          onClick={() => setDrilldown("value_top")}
        />
        <KpiCard
          label="Критические контрагенты"
          value={`${criticalCounterparties.length}`}
          hint="Нажмите, чтобы открыть список"
          accent
          onClick={() => setDrilldown("critical")}
        />
      </div>

      <div className="min-h-0 flex-1">
        {selectedAggregate && selectedDetail ? (
          <CardShell
            eyebrow="Рабочая область анализа"
            title="Список контрагентов и карточка выбранной компании"
            rightSlot={
              <div className="flex items-center gap-2">
                <ExportMenuButton
                  label="Сохранить список контрагентов"
                  open={openExportMenu === "list"}
                  onToggle={() => setOpenExportMenu((prev) => (prev === "list" ? null : "list"))}
                  onSelect={handleExport}
                />
                <SecondaryButton onClick={() => setSelectedId(null)}>
                  Закрыть карточку
                </SecondaryButton>
              </div>
            }
            bodyClassName="h-full p-0"
            className="h-full"
          >
            <div className="grid h-full min-h-0 grid-cols-1 xl:grid-cols-2">
              <div className="min-h-0 overflow-hidden border-b border-[var(--border-subtle)] xl:border-b-0 xl:border-r">
                <div className="flex h-full min-h-0 flex-col p-5">
                  <div className="mb-4 shrink-0">
                    <p className="text-sm font-semibold text-[var(--text-primary)]">
                      Список контрагентов
                    </p>
                    <p className="mt-1 text-sm text-[var(--text-muted)]">
                      Выберите компанию в таблице, чтобы просмотреть детальную карточку справа
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

              <div className="min-h-0 overflow-auto">
                <div className="p-5">
                  <DetailPanel
                    aggregate={selectedAggregate}
                    detail={selectedDetail}
                    onClose={() => setSelectedId(null)}
                  />
                </div>
              </div>
            </div>
          </CardShell>
        ) : (
          <CardShell
            eyebrow="Список контрагентов"
            title="Табличный перечень контрагентов, выявленных в документах сделки"
            rightSlot={
              <ExportMenuButton
                label="Сохранить список контрагентов"
                open={openExportMenu === "list"}
                onToggle={() => setOpenExportMenu((prev) => (prev === "list" ? null : "list"))}
                onSelect={handleExport}
              />
            }
            bodyClassName="h-full"
            className="h-full"
          >
            <div className="flex h-full min-h-0 flex-col">
              <div className="mb-3 shrink-0">
                <p className="text-sm text-[var(--text-secondary)]">
                  В демонстрационном списке добавлено больше компаний, чтобы таблица имела собственную внутреннюю прокрутку.
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
          </CardShell>
        )}
      </div>

      <DrilldownModal
        open={drilldown !== null}
        onClose={() => setDrilldown(null)}
        title={
          drilldown === "geography"
            ? "География выявленных контрагентов"
            : drilldown === "contracts_top"
              ? "Топ-5 контрагентов по количеству контрактов"
              : drilldown === "value_top"
                ? "Топ-5 контрагентов по сумме контрактов"
                : "Критические контрагенты"
        }
      >
        {drilldown === "geography" ? (
          <CountryStructureCard items={countryStructure} />
        ) : drilldown === "contracts_top" ? (
          <RankedListCard title="Топ-5 по количеству контрактов" items={topByContracts} />
        ) : drilldown === "value_top" ? (
          <RankedListCard title="Топ-5 по сумме контрактов" items={topByValue} />
        ) : (
          <CriticalCounterpartiesTable items={criticalCounterparties} />
        )}
      </DrilldownModal>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

const CounterpartiesTab: React.FC<CounterpartiesTabProps> = ({
  dealId: _dealId,
  currentRunId: _currentRunId,
}) => {
  const [mode, setMode] = React.useState<PreviewMode>("intro");

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      {mode === "intro" ? (
        <IntroScreen onOpenDemo={() => setMode("demo")} />
      ) : (
        <DemoScreen onBack={() => setMode("intro")} />
      )}
    </div>
  );
};

export default CounterpartiesTab;



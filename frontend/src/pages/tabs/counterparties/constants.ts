// =============================================================
// src/pages/tabs/counterparties/constants.ts
// =============================================================

import type {
  CounterpartyAggregate,
  CounterpartyDetail,
  CoverageRow,
} from "./types";

export const COVERAGE_ROWS: CoverageRow[] = [
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

const EXTRA_AGGREGATES: CounterpartyAggregate[] = Array.from({ length: 22 }).map(
  (_, index) => {
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
  }
);

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
      {
        id: "c-1",
        title: "Share Purchase Agreement Draft",
        contractType: "SPA",
        section: "1.1 Definitions",
        mentionRole: "Affiliate",
        contractValueUsdM: 35,
      },
      {
        id: "c-2",
        title: "Transitional Services Agreement",
        contractType: "TSA",
        section: "Parties / Service Scope",
        mentionRole: "Service provider",
        contractValueUsdM: 28,
      },
      {
        id: "c-3",
        title: "Disclosure Letter",
        contractType: "Disclosure",
        section: "Related Party Arrangements",
        mentionRole: "Related-party service provider",
        contractValueUsdM: 12,
      },
      {
        id: "c-4",
        title: "Procurement Framework Agreement",
        contractType: "Commercial",
        section: "Annex 2",
        mentionRole: "Supplier",
        contractValueUsdM: 45,
      },
    ],
    financials: {
      fiscalYear: "FY2024",
      currency: "USD",
      revenue: "48.2m",
      ebitda: "7.6m",
      totalAssets: "61.4m",
      employees: 126,
    },
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
      {
        id: "c-5",
        title: "Revenue Concentration Memo",
        contractType: "Finance memo",
        section: "Top accounts",
        mentionRole: "Key customer",
        contractValueUsdM: 18,
      },
      {
        id: "c-6",
        title: "Commercial Agreement Summary",
        contractType: "Summary",
        section: "Annex 4",
        mentionRole: "Customer",
        contractValueUsdM: 11,
      },
      {
        id: "c-7",
        title: "Disclosure Letter",
        contractType: "Disclosure",
        section: "Major Customers",
        mentionRole: "Customer",
        contractValueUsdM: 13,
      },
    ],
    financials: {
      fiscalYear: "FY2024",
      currency: "USD",
      revenue: "31.5m",
      ebitda: "4.1m",
      totalAssets: "22.7m",
      employees: 74,
    },
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
      {
        id: "c-8",
        title: "Transitional Services Agreement",
        contractType: "TSA",
        section: "Parties",
        mentionRole: "Contractor",
        contractValueUsdM: 24,
      },
      {
        id: "c-9",
        title: "Procurement Exceptions Memo",
        contractType: "Memo",
        section: "Section 3",
        mentionRole: "Service contractor",
        contractValueUsdM: 19,
      },
      {
        id: "c-10",
        title: "Field Operations Support Contract",
        contractType: "Services",
        section: "Pricing Schedule",
        mentionRole: "Operations contractor",
        contractValueUsdM: 35,
      },
    ],
    financials: {
      fiscalYear: "FY2024",
      currency: "USD",
      revenue: "12.8m",
      ebitda: "1.3m",
      totalAssets: "9.2m",
      employees: 48,
    },
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
      {
        id: "c-11",
        title: "Board Consent",
        contractType: "Corporate approval",
        section: "Annex 1",
        mentionRole: "Advisor",
        contractValueUsdM: 4,
      },
      {
        id: "c-12",
        title: "Engagement Letter Summary",
        contractType: "Advisory",
        section: "Scope",
        mentionRole: "Advisor",
        contractValueUsdM: 5,
      },
    ],
    financials: {
      fiscalYear: "FY2024",
      currency: "USD",
      revenue: "6.4m",
      ebitda: "1.1m",
      totalAssets: "4.8m",
      employees: 19,
    },
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
      {
        id: "c-13",
        title: "Master Supply Agreement",
        contractType: "Supply",
        section: "Commercial Terms",
        mentionRole: "Supplier",
        contractValueUsdM: 95,
      },
      {
        id: "c-14",
        title: "Long-Term Procurement Schedule",
        contractType: "Schedule",
        section: "Volume Commitments",
        mentionRole: "Core supplier",
        contractValueUsdM: 76,
      },
      {
        id: "c-15",
        title: "Manufacturing Support Addendum",
        contractType: "Addendum",
        section: "Annex B",
        mentionRole: "Technical supplier",
        contractValueUsdM: 44,
      },
    ],
    financials: {
      fiscalYear: "FY2024",
      currency: "USD",
      revenue: "38m",
      ebitda: "5.4m",
      totalAssets: "27m",
      employees: 93,
    },
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
      {
        id: "c-16",
        title: "Procurement Support Agreement",
        contractType: "Services",
        section: "Counterparty Details",
        mentionRole: "Intermediary",
        contractValueUsdM: 8,
      },
      {
        id: "c-17",
        title: "Supplier Onboarding Memo",
        contractType: "Memo",
        section: "Review Notes",
        mentionRole: "Intermediary",
        contractValueUsdM: 6,
      },
    ],
    financials: {
      fiscalYear: "FY2024",
      currency: "USD",
      revenue: "18m",
      ebitda: "2.2m",
      totalAssets: "13m",
      employees: 41,
    },
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
      {
        id: "c-18",
        title: "Terminal Equipment Supply Contract",
        contractType: "Supply",
        section: "Vendor profile",
        mentionRole: "Supplier",
        contractValueUsdM: 7,
      },
      {
        id: "c-19",
        title: "Operational Readiness Memo",
        contractType: "Memo",
        section: "Section 5",
        mentionRole: "Vendor",
        contractValueUsdM: 4,
      },
    ],
    financials: {
      fiscalYear: "FY2024",
      currency: "USD",
      revenue: "9.5m",
      ebitda: "0.8m",
      totalAssets: "6.1m",
      employees: 27,
    },
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
      {
        id: "c-20",
        title: "Equipment Supply Framework",
        contractType: "Supply",
        section: "Schedule 1",
        mentionRole: "Supplier",
        contractValueUsdM: 16,
      },
      {
        id: "c-21",
        title: "Operations Support Addendum",
        contractType: "Addendum",
        section: "Service Matrix",
        mentionRole: "Technical supplier",
        contractValueUsdM: 10,
      },
    ],
    financials: {
      fiscalYear: "FY2024",
      currency: "USD",
      revenue: "54m",
      ebitda: "6.7m",
      totalAssets: "39m",
      employees: 144,
    },
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
    "Demonstration card for expanded list of counterparties. In production mode, automated data enrichment from global, local, and internal sources will be displayed here.",
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
      "Card generated from demo data to verify scroll and split-view layout.",
      "In production mode, provider hits, ownership structure, and links to internal databases will be shown here.",
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
      "Demo ownership chain description. In production mode, this field will be populated based on external and internal enrichment results.",
  },
});

export const DEMO_DETAILS: Record<string, CounterpartyDetail> = DEMO_AGGREGATES.reduce(
  (acc, item) => {
    acc[item.id] = BASE_DETAILS[item.id] ?? generateFallbackDetail(item);
    return acc;
  },
  {} as Record<string, CounterpartyDetail>
);



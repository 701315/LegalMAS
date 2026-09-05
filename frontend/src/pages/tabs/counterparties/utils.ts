// =============================================================
// src/pages/tabs/counterparties/utils.ts
// Pure helpers for counterparties tab.
// All label-producing helpers return i18n KEYS (not translated text).
// Callers are expected to invoke t(`labels.${key}`) or similar.
// =============================================================

import type {
  CountryStructureItem,
  CounterpartiesTotals,
  CounterpartyAggregate,
  CriticalCounterpartyItem,
  RankedListItem,
  RiskMeta,
  SortAriaValue,
  SortKey,
  SortState,
} from "./types";

type TranslateFn = (key: string, options?: Record<string, unknown>) => string;

// ---------------------------------------------------------------------------
// Risk / review key helpers (return canonical i18n keys, not display strings)
// ---------------------------------------------------------------------------

export const riskBadgeTone = (
  value: "yes" | "no" | "review",
): "high" | "low" | "medium" => {
  if (value === "yes") return "high";
  if (value === "review") return "medium";
  return "low";
};

/**
 * Returns i18n label key (yes | no | review).
 * Consumer should render t(`labels.${key}`).
 */
export const riskBadgeLabel = (value: "yes" | "no" | "review"): string => {
  if (value === "yes") return "yes";
  if (value === "review") return "review";
  return "no";
};

/**
 * Returns risk meta with i18n label key (high | medium | low).
 * Consumer should render t(`labels.${meta.label}`).
 */
export const buildRiskMeta = (item: CounterpartyAggregate): RiskMeta => {
  if (
    item.bankruptcyFlag ||
    item.sanctionsFlag ||
    item.contractValueUsdM > item.annualRevenueUsdM * 5
  ) {
    return { label: "high", tone: "high", rank: 3 };
  }

  if (item.litigationFlag || item.reviewStatus === "needs_review") {
    return { label: "medium", tone: "medium", rank: 2 };
  }

  return { label: "low", tone: "low", rank: 1 };
};

export const reviewTone = (
  value: CounterpartyAggregate["reviewStatus"],
): "high" | "medium" | "low" => {
  if (value === "critical") return "high";
  if (value === "needs_review") return "medium";
  return "low";
};

/**
 * Returns i18n label key (critical | review | ok).
 * Consumer should render t(`labels.${key}`).
 */
export const reviewLabel = (
  value: CounterpartyAggregate["reviewStatus"],
): string => {
  if (value === "critical") return "critical";
  if (value === "needs_review") return "review";
  return "ok";
};

// ---------------------------------------------------------------------------
// Sort helpers
// ---------------------------------------------------------------------------

export const getAriaSort = (sort: SortState, key: SortKey): SortAriaValue => {
  if (sort.key !== key) return "none";
  return sort.direction === "asc" ? "ascending" : "descending";
};

export const getNextSortState = (prev: SortState, key: SortKey): SortState => {
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
};

export const sortCounterparties = (
  items: CounterpartyAggregate[],
  sort: SortState,
  locale: string = "en-US",
): CounterpartyAggregate[] => {
  const withMeta = items.map((item, index) => ({
    ...item,
    originalIndex: index + 1,
    riskMeta: buildRiskMeta(item),
  }));

  const sorted = [...withMeta].sort((a, b) => {
    let comparison = 0;

    switch (sort.key) {
      case "index":
        comparison = a.originalIndex - b.originalIndex;
        break;
      case "name":
        comparison = a.name.localeCompare(b.name, locale);
        break;
      case "country":
        comparison = a.country.localeCompare(b.country, locale);
        break;
      case "contractCount":
        comparison = a.contractCount - b.contractCount;
        break;
      case "contractValueUsdM":
        comparison = a.contractValueUsdM - b.contractValueUsdM;
        break;
      case "risk":
        comparison = a.riskMeta.rank - b.riskMeta.rank;
        break;
      default:
        comparison = 0;
    }

    return sort.direction === "asc" ? comparison : -comparison;
  });

  return sorted.map(
    ({ originalIndex: _originalIndex, riskMeta: _riskMeta, ...item }) => item,
  );
};

// ---------------------------------------------------------------------------
// Derived aggregates (KPI + drilldown data)
// ---------------------------------------------------------------------------

export const buildCounterpartiesTotals = (
  items: CounterpartyAggregate[],
): CounterpartiesTotals => ({
  totalCounterparties: items.length,
  totalContracts: items.reduce((sum, item) => sum + item.contractCount, 0),
  totalContractValue: items.reduce(
    (sum, item) => sum + item.contractValueUsdM,
    0,
  ),
});

export const buildTopByContracts = (
  items: CounterpartyAggregate[],
): RankedListItem[] =>
  [...items]
    .sort((a, b) => b.contractCount - a.contractCount)
    .slice(0, 5)
    .map((item) => ({
      name: item.name,
      country: item.country,
      value: `${item.contractCount}`,
    }));

export const buildTopByValue = (
  items: CounterpartyAggregate[],
): RankedListItem[] =>
  [...items]
    .sort((a, b) => b.contractValueUsdM - a.contractValueUsdM)
    .slice(0, 5)
    .map((item) => ({
      name: item.name,
      country: item.country,
      value: `$${item.contractValueUsdM}m`,
    }));

export const buildCountryStructure = (
  items: CounterpartyAggregate[],
): CountryStructureItem[] => {
  const countryMap = new Map<string, number>();

  for (const item of items) {
    countryMap.set(item.country, (countryMap.get(item.country) ?? 0) + 1);
  }

  return [...countryMap.entries()]
    .map(([country, count]) => ({ country, count }))
    .sort((a, b) => b.count - a.count);
};

export const buildCriticalCounterparties = (
  items: CounterpartyAggregate[],
  tFn?: TranslateFn,
): CriticalCounterpartyItem[] =>
  items.reduce<CriticalCounterpartyItem[]>((acc, item) => {
    const reasons: string[] = [];

    if (item.bankruptcyFlag) {
      reasons.push(
        tFn
          ? tFn("drilldown.criticalTable.reasonsList.bankruptcy", {
              defaultValue: "Insolvency alert / bankruptcy indicator.",
            })
          : "Insolvency alert / bankruptcy indicator.",
      );
    }
    if (item.sanctionsFlag) {
      reasons.push(
        tFn
          ? tFn("drilldown.criticalTable.reasonsList.sanctions", {
              defaultValue: "Sanctions screening signal match.",
            })
          : "Sanctions screening signal match.",
      );
    }
    if (item.contractValueUsdM > item.annualRevenueUsdM * 5) {
      reasons.push(
        tFn
          ? tFn("drilldown.criticalTable.reasonsList.revenueRatio", {
              defaultValue:
                "Total contract value exceeds annual revenue by more than 5 times.",
            })
          : "Total contract value exceeds annual revenue by more than 5 times.",
      );
    }

    if (reasons.length > 0) {
      acc.push({
        name: item.name,
        country: item.country,
        reasons,
      });
    }

    return acc;
  }, []);


  
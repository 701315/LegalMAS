// =============================================================
// src/pages/tabs/real-estate/utils.ts
// =============================================================

import {
  OBJECT_TYPE_LABELS,
  OBJECT_TYPE_SHORT_LABELS,
} from "./constants";
import type {
  CriticalObjectItem,
  RankedListItem,
  RealEstateObjectAggregate,
  RealEstateObjectType,
  RegionStructureItem,
  RiskMeta,
  SortAriaValue,
  SortKey,
  SortState,
} from "./types";

type TranslateFn = (key: string, options?: Record<string, unknown>) => string;

export const objectTypeLabel = (
  value: RealEstateObjectType,
  tFn?: TranslateFn,
): string => {
  if (tFn) {
    return tFn(`detail.registry.types.${value}`, {
      defaultValue: OBJECT_TYPE_LABELS[value] ?? "Unknown",
    });
  }
  return OBJECT_TYPE_LABELS[value] ?? "Unknown";
};

export const objectTypeShortLabel = (
  value: RealEstateObjectType,
  tFn?: TranslateFn,
): string => {
  if (tFn) {
    return tFn(`detail.registry.typesShort.${value}`, {
      defaultValue: OBJECT_TYPE_SHORT_LABELS[value] ?? "Unknown",
    });
  }
  return OBJECT_TYPE_SHORT_LABELS[value] ?? "Unknown";
};

export const riskBadgeTone = (value: "yes" | "no" | "review"): "high" | "low" | "medium" => {
  if (value === "yes") return "high";
  if (value === "review") return "medium";
  return "low";
};

export const riskBadgeLabel = (value: "yes" | "no" | "review"): string => {
  if (value === "yes") return "Yes";
  if (value === "review") return "Review";
  return "No";
};

export const buildRiskMeta = (
  item: RealEstateObjectAggregate,
  tFn?: TranslateFn,
): RiskMeta => {
  if (
    item.risk === "high" ||
    item.encumbrance === true ||
    item.ownership_status === "not_confirmed"
  ) {
    return {
      label: tFn ? tFn("detail.encumbrances.types.high", { defaultValue: "High" }) : "High",
      tone: "high",
      rank: 3,
    };
  }

  if (item.risk === "medium" || item.ownership_status === "review") {
    return {
      label: tFn ? tFn("detail.encumbrances.types.medium", { defaultValue: "Medium" }) : "Medium",
      tone: "medium",
      rank: 2,
    };
  }

  return {
    label: tFn ? tFn("detail.encumbrances.types.low", { defaultValue: "Low" }) : "Low",
    tone: "low",
    rank: 1,
  };
};

export const checkTone = (value: "ok" | "review" | "issue"): "low" | "medium" | "high" => {
  if (value === "issue") return "high";
  if (value === "review") return "medium";
  return "low";
};

export const checkLabel = (value: "ok" | "review" | "issue"): string => {
  if (value === "issue") return "Issue";
  if (value === "review") return "Review";
  return "OK";
};

export const getAriaSort = (
  sort: SortState,
  key: SortKey
): SortAriaValue => {
  if (sort.key !== key) return "none";
  return sort.direction === "asc" ? "ascending" : "descending";
};

export const sortIcon = (sort: SortState, key: SortKey): string => {
  if (sort.key !== key) return "↕";
  return sort.direction === "asc" ? "↑" : "↓";
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

export const buildRealEstateTotals = (items: RealEstateObjectAggregate[]) => ({
  totalObjects: items.length,
  totalLand: items.filter((item) => item.object_type === "land").length,
  totalBuildingsAndPremises: items.filter(
    (item) => item.object_type === "building" || item.object_type === "premises"
  ).length,
  totalEncumbered: items.filter((item) => item.encumbrance === true).length,
});

export const buildTopByArea = (
  items: RealEstateObjectAggregate[],
  tFn?: TranslateFn,
  locale: string = "en-US",
): RankedListItem[] => {
  const noAddress = tFn ? tFn("table.noAddress", { defaultValue: "No address" }) : "No address";
  const unit = tFn ? tFn("areaUnit", { defaultValue: "m²" }) : "m²";

  return [...items]
    .sort((a, b) => (b.area_sqm ?? 0) - (a.area_sqm ?? 0))
    .slice(0, 5)
    .map((item) => ({
      name: item.address ?? noAddress,
      subtitle: item.region,
      value: item.area_sqm ? `${item.area_sqm.toLocaleString(locale)} ${unit}` : "—",
    }));
};

export const buildEncumberedObjects = (
  items: RealEstateObjectAggregate[],
  tFn?: TranslateFn,
): RankedListItem[] => {
  const noAddress = tFn ? tFn("table.noAddress", { defaultValue: "No address" }) : "No address";
  const noCadastral = tFn ? tFn("table.noCadastral", { defaultValue: "No cadastral number" }) : "No cadastral number";

  return items
    .filter((item) => item.encumbrance === true)
    .map((item) => ({
      name: item.address ?? noAddress,
      subtitle: item.cadastral_number ?? noCadastral,
      value: buildRiskMeta(item, tFn).label,
    }));
};

export const buildRegionStructure = (
  items: RealEstateObjectAggregate[]
): RegionStructureItem[] => {
  const regionMap = new Map<string, number>();

  for (const item of items) {
    regionMap.set(item.region, (regionMap.get(item.region) ?? 0) + 1);
  }

  return [...regionMap.entries()]
    .map(([region, count]) => ({ region, count }))
    .sort((a, b) => b.count - a.count);
};

export const buildCriticalObjects = (
  items: RealEstateObjectAggregate[],
  tFn?: TranslateFn,
): CriticalObjectItem[] => {
  const noAddress = tFn ? tFn("table.noAddress", { defaultValue: "No address" }) : "No address";

  return items.reduce<CriticalObjectItem[]>((acc, item) => {
    const reasons: string[] = [];

    if (item.encumbrance === true) {
      reasons.push(tFn ? tFn("criticalTable.reasons.encumbrance", { defaultValue: "Encumbrance indicators detected." }) : "Encumbrance indicators detected.");
    }
    if (item.risk === "high") {
      reasons.push(tFn ? tFn("criticalTable.reasons.highRisk", { defaultValue: "Object has a high level of risk." }) : "Object has a high level of risk.");
    }
    if (item.ownership_status === "not_confirmed") {
      reasons.push(tFn ? tFn("criticalTable.reasons.notConfirmed", { defaultValue: "Ownership is not confirmed." }) : "Ownership is not confirmed.");
    }
    if (item.object_type === "unfinished") {
      reasons.push(tFn ? tFn("criticalTable.reasons.unfinished", { defaultValue: "Unfinished construction object requires separate verification." }) : "Unfinished construction object requires separate verification.");
    }

    if (reasons.length > 0) {
      acc.push({
        name: item.address ?? noAddress,
        region: item.region,
        reasons,
      });
    }

    return acc;
  }, []);
};

export const sortRealEstateObjects = (
  items: RealEstateObjectAggregate[],
  sort: SortState,
  locale: string = "en-US",
  tFn?: TranslateFn,
): RealEstateObjectAggregate[] => {
  const withIndex = items.map((item, index) => ({
    ...item,
    originalIndex: index + 1,
    riskMeta: buildRiskMeta(item, tFn),
  }));

  const sorted = [...withIndex].sort((a, b) => {
    let comparison = 0;

    switch (sort.key) {
      case "index":
        comparison = a.originalIndex - b.originalIndex;
        break;
      case "address":
        comparison = (a.address ?? "").localeCompare(b.address ?? "", locale);
        break;
      case "region":
        comparison = a.region.localeCompare(b.region, locale);
        break;
      case "objectType":
        comparison = objectTypeLabel(a.object_type, tFn).localeCompare(objectTypeLabel(a.object_type, tFn), locale);
        break;
      case "area":
        comparison = (a.area_sqm ?? 0) - (b.area_sqm ?? 0);
        break;
      case "documentCount":
        comparison = a.document_count - b.document_count;
        break;
      case "encumbrance":
        comparison = Number(a.encumbrance === true) - Number(b.encumbrance === true);
        break;
      case "risk":
        comparison = a.riskMeta.rank - b.riskMeta.rank;
        break;
      default:
        comparison = 0;
    }

    return sort.direction === "asc" ? comparison : -comparison;
  });

  return sorted.map(({ originalIndex: _originalIndex, riskMeta: _riskMeta, ...item }) => item);
};



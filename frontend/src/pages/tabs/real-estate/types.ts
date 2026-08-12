export type RealEstateObjectType =
  | "land"
  | "building"
  | "premises"
  | "construction"
  | "unfinished"
  | "unknown";

export type RealEstateRisk = "high" | "medium" | "low" | "unknown";

export type PreviewMode = "intro" | "demo";
export type DrilldownKind = "geography" | "encumbrances" | "area_top" | "critical" | null;
export type ExportMenuKind = "list" | null;
export type ExportFormat = "excel" | "docx" | "pdf";
export type SortDirection = "asc" | "desc";
export type SortKey =
  | "index"
  | "address"
  | "region"
  | "objectType"
  | "area"
  | "documentCount"
  | "encumbrance"
  | "risk";

export type SortAriaValue = "ascending" | "descending" | "none";

export interface SortState {
  key: SortKey;
  direction: SortDirection;
}

export interface RealEstateObject {
  id: string;
  address?: string | null;
  cadastral_number?: string | null;
  object_type: RealEstateObjectType;
  risk: RealEstateRisk;
  document_count: number;
  area_sqm?: number | null;
  encumbrance?: boolean | null;
  first_mentioned_at?: string | null;
}

export interface RealEstateObjectAggregate extends RealEstateObject {
  region: string;
  market: "RU" | "UAE" | "EU";
  ownership_status: "registered" | "review" | "not_confirmed";
  usage_type: "office" | "warehouse" | "land_plot" | "industrial" | "retail" | "mixed";
}

export interface MentionedDocument {
  id: string;
  title: string;
  documentType: string;
  section: string;
  mentionRole: string;
}

export interface RealEstateObjectDetail {
  id: string;
  shortDescription: string;
  documents: MentionedDocument[];
  registry: {
    registrySource: string;
    ownershipStatus: string;
    ownerName: string;
    cadastralNumber: string;
    objectTypeLabel: string;
    areaLabel: string;
    addressLabel: string;
  };
  encumbrances: {
    hasEncumbrances: "yes" | "no" | "review";
    mortgage: "yes" | "no" | "review";
    arrest: "yes" | "no" | "review";
    easement: "yes" | "no" | "review";
    notes: string[];
  };
  legalChecks: {
    titleChain: "ok" | "review" | "issue";
    registryMatch: "ok" | "review" | "issue";
    zoning: "ok" | "review" | "issue";
    notes: string[];
  };
  mapContext: {
    region: string;
    district: string;
    geoNote: string;
  };
}

export interface CoverageRow {
  jurisdiction: string;
  registrySources: string;
  whatChecked: string;
  remarks: string;
}

export interface RealEstateTabProps {
  dealId: string;
  currentRunId: string | null;
}

export interface RiskMeta {
  label: string;
  tone: "high" | "medium" | "low";
  rank: number;
}

export interface RankedListItem {
  name: string;
  subtitle: string;
  value: string;
}

export interface RegionStructureItem {
  region: string;
  count: number;
}

export interface CriticalObjectItem {
  name: string;
  region: string;
  reasons: string[];
}



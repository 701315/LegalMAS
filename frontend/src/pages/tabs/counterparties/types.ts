export type CounterpartyType = "legal_entity" | "individual" | "unknown";

export type PreviewMode = "intro" | "demo";
export type DrilldownKind = "geography" | "contracts_top" | "value_top" | "critical" | null;
export type ExportMenuKind = "list" | null;
export type ExportFormat = "excel" | "docx" | "pdf";
export type SortDirection = "asc" | "desc";
export type SortKey =
  | "index"
  | "name"
  | "country"
  | "contractCount"
  | "contractValueUsdM"
  | "risk";

export type SortAriaValue = "ascending" | "descending" | "none";

export interface SortState {
  key: SortKey;
  direction: SortDirection;
}

export interface CoverageRow {
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

export interface MentionedContract {
  id: string;
  title: string;
  contractType: string;
  section: string;
  mentionRole: string;
  contractValueUsdM?: number | null;
}

export interface CounterpartyDetail {
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

export interface CounterpartiesTabProps {
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
  country: string;
  value: string;
}

export interface CountryStructureItem {
  country: string;
  count: number;
}

export interface CriticalCounterpartyItem {
  name: string;
  country: string;
  reasons: string[];
}

export interface CounterpartiesTotals {
  totalCounterparties: number;
  totalContracts: number;
  totalContractValue: number;
}



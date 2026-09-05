// =============================================================
// src/pages/tabs/RealEstateTab.tsx
// Вкладка «Анализ выявленного недвижимого имущества».
//
// Preview flow:
// 1) Intro screen — короткое описание раздела
// 2) Demo screen  — overview + shared split-view workspace
// =============================================================

import React, { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import {
  ChevronDown,
  ChevronLeft,
  ChevronUp,
  ChevronsUpDown,
} from "lucide-react";

import Button from "../../components/ui/Button";
import PageSection from "../../components/ui/PageSection";

import {
  COVERAGE_ROWS,
  DEMO_DETAILS,
  DEMO_OBJECTS,
} from "./real-estate/constants";
import type {
  DrilldownKind,
  ExportFormat,
  ExportMenuKind,
  PreviewMode,
  RealEstateObjectAggregate,
  RealEstateObjectDetail,
  RealEstateObjectType,
  RealEstateTabProps,
  SortKey,
  SortState,
} from "./real-estate/types";
import {
  buildCriticalObjects,
  buildEncumberedObjects,
  buildRealEstateTotals,
  buildRegionStructure,
  buildRiskMeta,
  buildTopByArea,
  checkTone,
  getAriaSort,
  getNextSortState,
  riskBadgeTone,
  sortRealEstateObjects,
} from "./real-estate/utils";

// ---------------------------------------------------------------------------
// Helpers for typed i18n resolution
// ---------------------------------------------------------------------------

const getObjectTypeLabel = (type: RealEstateObjectType, t: TFunction): string => {
  return t(`types.${type}`, { defaultValue: type });
};

const getObjectTypeShortLabel = (type: RealEstateObjectType, t: TFunction): string => {
  return t(`typesShort.${type}`, { defaultValue: type });
};

const getRiskLabel = (tone: "high" | "medium" | "low", t: TFunction): string => {
  return t(`riskLevels.${tone}`, { defaultValue: tone });
};

const getEncumbranceLabel = (value: boolean | string | null, t: TFunction): string => {
  if (value === true) return t("table.encumbranceYes");
  if (value === false) return t("table.encumbranceNo");
  if (value === "high") return t("riskLevels.high");
  if (value === "medium") return t("riskLevels.medium");
  if (value === "low") return t("riskLevels.low");
  return t("table.encumbranceCheck");
};

const getCheckStatusLabel = (value: "ok" | "warning" | "critical" | string, t: TFunction): string => {
  if (value === "ok") return t("checks.ok");
  if (value === "warning") return t("checks.warning");
  if (value === "critical") return t("checks.critical");
  return t(`checks.${value}`, { defaultValue: String(value) });
};

// ---------------------------------------------------------------------------
// Shared UI primitives
// ---------------------------------------------------------------------------

/**
 * Badge — семантические тоны:
 *   neutral — нейтральный тэг (регион, тип объекта)
 *   success — accent-статус (Preview badge)
 *   high    — критичный / negative signal (красный)
 *   medium  — требует внимания (жёлтый)
 *   low     — позитивный статус (зелёный)
 */
const Badge: React.FC<{
  children: React.ReactNode;
  tone?: "neutral" | "success" | "high" | "medium" | "low";
}> = ({ children, tone = "neutral" }) => {
  const toneClass = {
    neutral:
      "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)]",
    success:
      "border-[var(--accent-primary)] bg-[var(--accent-muted)] text-[var(--accent-primary)]",
    high:
      "status-border-error status-bg-error status-text-error",
    medium:
      "status-border-warning status-bg-warning status-text-warning",
    low:
      "status-border-success status-bg-success status-text-success",
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
    subtitle: string;
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
            <p className="text-[12px] text-[var(--text-muted)]">{item.subtitle}</p>
          </div>
          <div className="shrink-0 text-sm font-semibold tabular-nums text-[var(--text-primary)]">
            {item.value}
          </div>
        </div>
      ))}
    </div>
  </div>
);

const RegionStructureCard: React.FC<{
  items: Array<{
    region: string;
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
            <div key={item.region}>
              <div className="mb-1 flex items-center justify-between gap-3">
                <p className="text-sm text-[var(--text-primary)]">{item.region}</p>
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

const CriticalObjectsTable: React.FC<{
  items: Array<{
    name: string;
    region: string;
    reasons: string[];
  }>;
}> = ({ items }) => {
  const { t } = useTranslation("realEstate");

  return (
    <div className="overflow-hidden rounded-2xl border border-[var(--border)]">
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-[var(--bg-elevated-soft)]">
            <tr>
              <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">{t("criticalTable.headers.object")}</th>
              <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">{t("criticalTable.headers.region")}</th>
              <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">
                {t("criticalTable.headers.reasons")}
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.name} className="border-t border-[var(--border-subtle)] align-top">
                <td className="px-4 py-3 font-medium text-[var(--text-primary)]">{item.name}</td>
                <td className="px-4 py-3 text-[var(--text-secondary)]">{item.region}</td>
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
  const { t } = useTranslation("realEstate");
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
  const { t } = useTranslation("realEstate");

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
// Icons
// ---------------------------------------------------------------------------

const IconBuilding = () => (
  <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="3" y="5" width="14" height="13" rx="1" stroke="currentColor" strokeWidth="1.5" />
    <path d="M3 8h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M7 18v-5h6v5" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    <path
      d="M7 11.5h1.5M11.5 11.5H13"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
    <path d="M10 2v3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

const IconCadaster = () => (
  <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="3" y="3" width="14" height="14" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
    <path d="M3 10h14M10 3v14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <rect x="5.5" y="5.5" width="3" height="3" rx="0.5" stroke="currentColor" strokeWidth="1" />
    <rect
      x="11.5"
      y="11.5"
      width="3"
      height="3"
      rx="0.5"
      stroke="currentColor"
      strokeWidth="1"
    />
  </svg>
);

const IconEncumbrance = () => (
  <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path
      d="M10 2L3.5 5v4.5c0 3.86 2.75 7.47 6.5 8.5 3.75-1.03 6.5-4.64 6.5-8.5V5L10 2z"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinejoin="round"
    />
    <path
      d="M7.5 10.5l1.5 1.5 3.5-3.5"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

// ---------------------------------------------------------------------------
// Intro screen
// ---------------------------------------------------------------------------

const IntroScreen: React.FC<{
  onOpenDemo: () => void;
}> = ({ onOpenDemo }) => {
  const { t } = useTranslation("realEstate");

  const coverageRows = useMemo(() => {
    const localized = t("coverageRows", { returnObjects: true });
    if (Array.isArray(localized) && localized.length > 0) {
      return localized;
    }
    return COVERAGE_ROWS;
  }, [t]);

  return (
    <div className="lg:flex lg:h-full lg:min-h-0 lg:flex-col lg:overflow-hidden">
      {/* Content */}
      <div className="space-y-4 lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:pr-1">
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
              icon={<IconBuilding />}
              title={t("intro.howItWorks.detection.title")}
              description={t("intro.howItWorks.detection.description")}
            />
            <FeatureCard
              icon={<IconCadaster />}
              title={t("intro.howItWorks.verification.title")}
              description={t("intro.howItWorks.verification.description")}
            />
            <FeatureCard
              icon={<IconEncumbrance />}
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
                    <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">
                      {t("intro.dataSources.headers.jurisdiction")}
                    </th>
                    <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">
                      {t("intro.dataSources.headers.sources")}
                    </th>
                    <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">
                      {t("intro.dataSources.headers.checked")}
                    </th>
                    <th className="px-4 py-3 font-semibold text-[var(--text-primary)]">
                      {t("intro.dataSources.headers.remarks")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {coverageRows.map((row) => (
                    <tr
                      key={row.jurisdiction}
                      className="border-t border-[var(--border-subtle)] align-top"
                    >
                      <td className="px-4 py-3 text-[var(--text-primary)]">
                        {row.jurisdiction}
                      </td>
                      <td className="px-4 py-3 text-[var(--text-secondary)]">
                        {row.registrySources}
                      </td>
                      <td className="px-4 py-3 text-[var(--text-secondary)]">
                        {row.whatChecked}
                      </td>
                      <td className="px-4 py-3 text-[var(--text-secondary)]">
                        {row.remarks}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </PageSection>
      </div>

      {/* Sticky CTA (desktop) / natural block (mobile) */}
      <div className="mt-4 border-t border-[var(--border-subtle)] pt-4 lg:shrink-0">
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
// Table — sortable header
// ---------------------------------------------------------------------------

const SortableHeader: React.FC<{
  label: string;
  sortKey: SortKey;
  currentSort: SortState;
  onSort: (key: SortKey) => void;
  className?: string;
}> = ({ label, sortKey, currentSort, onSort, className = "" }) => {
  const { t } = useTranslation("realEstate");
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
// Real estate table
// ---------------------------------------------------------------------------

const RealEstateTable: React.FC<{
  items: RealEstateObjectAggregate[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  sort: SortState;
  onSort: (key: SortKey) => void;
}> = ({ items, selectedId, onSelect, sort, onSort }) => {
  const { t, i18n } = useTranslation("realEstate");
  const areaUnit = t("areaUnit", { defaultValue: "m²" });

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
              label={t("table.headers.address")}
              sortKey="address"
              currentSort={sort}
              onSort={onSort}
            />
            <SortableHeader
              label={t("table.headers.region")}
              sortKey="region"
              currentSort={sort}
              onSort={onSort}
            />
            <SortableHeader
              label={t("table.headers.type")}
              sortKey="objectType"
              currentSort={sort}
              onSort={onSort}
            />
            <SortableHeader
              label={t("table.headers.area")}
              sortKey="area"
              currentSort={sort}
              onSort={onSort}
            />
            <SortableHeader
              label={t("table.headers.documents")}
              sortKey="documentCount"
              currentSort={sort}
              onSort={onSort}
            />
            <SortableHeader
              label={t("table.headers.encumbrance")}
              sortKey="encumbrance"
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
                    className="text-left"
                  >
                    <span className="block text-sm font-medium text-[var(--accent-primary)] underline decoration-transparent transition hover:decoration-current">
                      {item.address ?? t("table.noAddress")}
                    </span>
                    <span className="mt-1 block text-[12px] text-[var(--text-muted)]">
                      {item.cadastral_number ?? t("table.noCadastral")}
                    </span>
                  </button>
                </td>
                <td className="px-4 py-3 text-[var(--text-secondary)]">{item.region}</td>
                <td className="px-4 py-3 text-[var(--text-secondary)]">
                  {getObjectTypeShortLabel(item.object_type, t)}
                </td>
                <td className="px-4 py-3 tabular-nums text-[var(--text-primary)]">
                  {item.area_sqm ? `${item.area_sqm.toLocaleString(i18n.language)} ${areaUnit}` : "—"}
                </td>
                <td className="px-4 py-3 tabular-nums text-[var(--text-primary)]">
                  {item.document_count}
                </td>
                <td className="px-4 py-3">
                  <Badge
                    tone={
                      item.encumbrance === true
                        ? "high"
                        : item.encumbrance === false
                          ? "low"
                          : "medium"
                    }
                  >
                    {item.encumbrance === true
                      ? t("table.encumbranceYes")
                      : item.encumbrance === false
                        ? t("table.encumbranceNo")
                        : t("table.encumbranceCheck")}
                  </Badge>
                </td>
                <td className="px-4 py-3">
                  <Badge tone={risk.tone}>{getRiskLabel(risk.tone, t)}</Badge>
                </td>
              </tr>
            );
          })}
          <tr aria-hidden="true">
            <td colSpan={8} className="h-2 bg-transparent" />
          </tr>
        </tbody>
      </table>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Detail panel
// ---------------------------------------------------------------------------

const RealEstateDetailPanel: React.FC<{
  object: RealEstateObjectAggregate;
  detail: RealEstateObjectDetail;
}> = ({ object, detail }) => {
  const { t } = useTranslation("realEstate");
  const risk = buildRiskMeta(object);

  return (
    <div className="space-y-4 pb-2">
      <PageSection
        title={t("detail.card.title")}
        subtitle={t("detail.card.subtitle")}
        rightSlot={<Badge tone={risk.tone}>{getRiskLabel(risk.tone, t)}</Badge>}
      >
        <div className="space-y-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-base font-semibold text-[var(--text-primary)]">
                {detail.registry.addressLabel}
              </p>
              <Badge>{object.region}</Badge>
              <Badge>{getObjectTypeLabel(object.object_type, t)}</Badge>
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
          {detail.documents.map((doc) => (
            <div
              key={doc.id}
              className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 shadow-sm"
            >
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm font-semibold text-[var(--text-primary)]">{doc.title}</p>
                <Badge>{doc.documentType}</Badge>
                <Badge>{doc.section}</Badge>
              </div>
              <div className="mt-2 text-sm text-[var(--text-secondary)]">
                <span className="font-medium text-[var(--text-primary)]">{t("detail.documents.role")}</span>{" "}
                {doc.mentionRole}
              </div>
            </div>
          ))}
        </div>
      </PageSection>

      <PageSection
        title={t("detail.registry.title")}
        subtitle={t("detail.registry.subtitle")}
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="rounded-2xl border border-[var(--border)] px-4 py-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {t("detail.registry.source")}
            </p>
            <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
              {detail.registry.registrySource}
            </p>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              {detail.registry.ownershipStatus}
            </p>
          </div>

          <div className="rounded-2xl border border-[var(--border)] px-4 py-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {t("detail.registry.owner")}
            </p>
            <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
              {detail.registry.ownerName}
            </p>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              {detail.registry.cadastralNumber}
            </p>
          </div>

          <div className="rounded-2xl border border-[var(--border)] px-4 py-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {t("detail.registry.objectType")}
            </p>
            <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
              {getObjectTypeLabel(object.object_type, t)}
            </p>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              {detail.registry.areaLabel}
            </p>
          </div>

          <div className="rounded-2xl border border-[var(--border)] px-4 py-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {t("detail.registry.address")}
            </p>
            <p className="mt-1 text-sm leading-6 text-[var(--text-primary)]">
              {detail.registry.addressLabel}
            </p>
          </div>
        </div>
      </PageSection>

      <PageSection
        title={t("detail.encumbrances.title")}
        subtitle={t("detail.encumbrances.subtitle")}
      >
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {(
            [
              { label: t("detail.encumbrances.types.encumbrances"), key: "hasEncumbrances" },
              { label: t("detail.encumbrances.types.mortgage"), key: "mortgage" },
              { label: t("detail.encumbrances.types.arrest"), key: "arrest" },
              { label: t("detail.encumbrances.types.easement"), key: "easement" },
            ] as const
          ).map(({ label, key }) => (
            <div key={key} className="rounded-2xl border border-[var(--border)] px-4 py-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                {label}
              </p>
              <div className="mt-2">
                <Badge tone={riskBadgeTone(detail.encumbrances[key])}>
                  {getEncumbranceLabel(detail.encumbrances[key], t)}
                </Badge>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-4 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 shadow-sm">
          <p className="text-sm font-semibold text-[var(--text-primary)]">{t("detail.encumbrances.notes")}</p>
          <ul className="mt-2 space-y-2 text-sm leading-6 text-[var(--text-secondary)]">
            {detail.encumbrances.notes.map((note) => (
              <li key={note} className="flex gap-2">
                <span className="mt-[8px] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-warning)]" />
                <span>{note}</span>
              </li>
            ))}
          </ul>
        </div>
      </PageSection>

      <PageSection
        title={t("detail.legal.title")}
        subtitle={t("detail.legal.subtitle")}
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {(
            [
              { label: t("detail.legal.types.titleChain"), key: "titleChain" },
              { label: t("detail.legal.types.registryMatch"), key: "registryMatch" },
              { label: t("detail.legal.types.zoning"), key: "zoning" },
            ] as const
          ).map(({ label, key }) => (
            <div key={key} className="rounded-2xl border border-[var(--border)] px-4 py-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
                {label}
              </p>
              <div className="mt-2">
                <Badge tone={checkTone(detail.legalChecks[key])}>
                  {getCheckStatusLabel(detail.legalChecks[key], t)}
                </Badge>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-4 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 shadow-sm">
          <p className="text-sm font-semibold text-[var(--text-primary)]">{t("detail.legal.notes")}</p>
          <ul className="mt-2 space-y-2 text-sm leading-6 text-[var(--text-secondary)]">
            {detail.legalChecks.notes.map((note) => (
              <li key={note} className="flex gap-2">
                <span className="mt-[8px] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--accent-primary)]" />
                <span>{note}</span>
              </li>
            ))}
          </ul>
        </div>
      </PageSection>

      <PageSection
        title={t("detail.map.title")}
        subtitle={t("detail.map.subtitle")}
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="rounded-2xl border border-[var(--border)] px-4 py-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {t("detail.map.region")}
            </p>
            <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
              {detail.mapContext.region}
            </p>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">
              {detail.mapContext.district}
            </p>
          </div>
          <div className="rounded-2xl border border-[var(--border)] px-4 py-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {t("detail.map.geoNote")}
            </p>
            <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
              {detail.mapContext.geoNote}
            </p>
          </div>
        </div>
      </PageSection>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Mobile fullscreen drawer
// ---------------------------------------------------------------------------

const MobileDetailDrawer: React.FC<{
  object: RealEstateObjectAggregate;
  detail: RealEstateObjectDetail;
  onClose: () => void;
}> = ({ object, detail, onClose }) => {
  const { t } = useTranslation("realEstate");

  // Escape close
  React.useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  // Body scroll lock — предотвращает прокрутку страницы под drawer'ом
  React.useEffect(() => {
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = originalOverflow;
    };
  }, []);

  return (
    <div className="lg:hidden">
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden
      />

      {/* Drawer */}
      <aside
        className="fixed inset-0 z-50 flex flex-col bg-[var(--bg-card)]"
        role="dialog"
        aria-modal="true"
        aria-labelledby="re-mobile-drawer-title"
      >
        {/* Header */}
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
            id="re-mobile-drawer-title"
            className="truncate text-sm font-semibold text-[var(--text-primary)]"
          >
            {object.address ?? t("drawer.noAddress")}
          </div>

          {/* Балансирующий spacer для центрирования title */}
          <div className="w-[100px] shrink-0" aria-hidden />
        </div>

        {/* Body — scrollable detail panel */}
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain bg-[var(--bg-base)] p-4">
          <RealEstateDetailPanel object={object} detail={detail} />
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
  const { t, i18n } = useTranslation("realEstate");
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [drilldown, setDrilldown] = React.useState<DrilldownKind>(null);
  const [openExportMenu, setOpenExportMenu] = React.useState<ExportMenuKind>(null);
  const [sort, setSort] = React.useState<SortState>({
    key: "index",
    direction: "asc",
  });

  // Локализация демо-объектов реестра
  const localizedDemoObjects = useMemo(() => {
    return DEMO_OBJECTS.map((obj) => {
      const regionEn = t(`demoData.regions.${obj.region}`, { defaultValue: obj.region });
      const demoObj = t(`demoData.objects.${obj.id}`, { returnObjects: true }) as any;
      return {
        ...obj,
        region: regionEn,
        address: (demoObj && typeof demoObj === "object" && demoObj.address) ? demoObj.address : obj.address,
      };
    });
  }, [t, i18n.language]);

  const { totalObjects, totalLand, totalBuildingsAndPremises, totalEncumbered } =
    React.useMemo(() => buildRealEstateTotals(localizedDemoObjects), [localizedDemoObjects]);

  const topByArea = React.useMemo(
    () => buildTopByArea(localizedDemoObjects, t, i18n.language),
    [localizedDemoObjects, t, i18n.language]
  );
  const encumberedObjects = React.useMemo(
    () => buildEncumberedObjects(localizedDemoObjects, t),
    [localizedDemoObjects, t]
  );
  const regionStructure = React.useMemo(
    () => buildRegionStructure(localizedDemoObjects),
    [localizedDemoObjects]
  );
  const criticalObjects = React.useMemo(
    () => buildCriticalObjects(localizedDemoObjects, t),
    [localizedDemoObjects, t]
  );

  const sortedObjects = React.useMemo(
    () => sortRealEstateObjects(localizedDemoObjects, sort, i18n.language, t),
    [localizedDemoObjects, sort, i18n.language, t]
  );

  const selectedObject = selectedId
    ? localizedDemoObjects.find((item) => item.id === selectedId) ?? null
    : null;

  const rawDetail = selectedObject ? DEMO_DETAILS[selectedObject.id] ?? null : null;

  // Локализация детальной карточки объекта
  const selectedDetail = useMemo(() => {
    if (!selectedObject || !rawDetail) return null;
    const demoObj = t(`demoData.objects.${selectedObject.id}`, { returnObjects: true }) as any;
    if (!demoObj || typeof demoObj !== "object") return rawDetail;

    return {
      ...rawDetail,
      shortDescription: demoObj.shortDescription ?? rawDetail.shortDescription,
      registry: {
        ...rawDetail.registry,
        registrySource: demoObj.registrySource ?? rawDetail.registry.registrySource,
        ownershipStatus: demoObj.ownershipStatus ?? rawDetail.registry.ownershipStatus,
        ownerName: demoObj.ownerName ?? rawDetail.registry.ownerName,
        addressLabel: demoObj.address ?? rawDetail.registry.addressLabel,
      },
      encumbrances: {
        ...rawDetail.encumbrances,
        notes: demoObj.encumbranceNotes ?? rawDetail.encumbrances.notes,
      },
      legalChecks: {
        ...rawDetail.legalChecks,
        notes: demoObj.legalNotes ?? rawDetail.legalChecks.notes,
      },
      mapContext: {
        ...rawDetail.mapContext,
        region: selectedObject.region,
        district: demoObj.district ?? rawDetail.mapContext.district,
        geoNote: demoObj.geoNote ?? rawDetail.mapContext.geoNote,
      },
    };
  }, [selectedObject, rawDetail, t, i18n.language]);

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
      : drilldown === "encumbrances"
        ? t("drilldown.encumbrances")
        : drilldown === "area_top"
          ? t("drilldown.areaTop")
          : t("drilldown.critical");

  return (
    <div className="flex min-h-0 flex-col lg:h-full lg:overflow-hidden">
      {/* Header */}
      <div className="mb-4 shrink-0 flex items-center justify-between gap-3">
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

      {/* KPI row */}
      <div className="mb-4 shrink-0 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard
          label={t("demo.kpi.totalObjects")}
          value={`${totalObjects}`}
          hint={t("demo.kpi.hintGeography")}
          onClick={() => setDrilldown("geography")}
        />
        <KpiCard
          label={t("demo.kpi.totalLand")}
          value={`${totalLand}`}
          hint={t("demo.kpi.hintRegistry")}
        />
        <KpiCard
          label={t("demo.kpi.buildings")}
          value={`${totalBuildingsAndPremises}`}
          hint={t("demo.kpi.hintArea")}
          onClick={() => setDrilldown("area_top")}
        />
        <KpiCard
          label={t("demo.kpi.encumbered")}
          value={`${totalEncumbered}`}
          hint={t("demo.kpi.hintList")}
          accent
          onClick={() => setDrilldown("encumbrances")}
        />
      </div>

      {/* Main workspace */}
      <div className="min-h-0 flex-1">
        {/* Desktop: split-view при selectedObject */}
        {selectedObject && selectedDetail ? (
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
                {/* Left: table */}
                <div className="min-h-0 lg:overflow-hidden border-b border-[var(--border-subtle)] xl:border-b-0 xl:border-r">
                  <div className="flex h-full min-h-0 flex-col p-5">
                    <div className="mb-4 shrink-0">
                      <p className="text-sm font-semibold text-[var(--text-primary)]">
                        {t("demo.registry.title")}
                      </p>
                      <p className="mt-1 text-sm text-[var(--text-muted)]">
                        {t("demo.workspace.selectHint")}
                      </p>
                    </div>
                    <div className="min-h-0 flex-1 lg:overflow-hidden">
                      <RealEstateTable
                        items={sortedObjects}
                        selectedId={selectedId}
                        onSelect={setSelectedId}
                        sort={sort}
                        onSort={handleSort}
                      />
                    </div>
                  </div>
                </div>

                {/* Right: detail panel */}
                <div className="min-h-0 lg:overflow-hidden">
                  <div className="min-h-0 p-5 lg:h-full lg:overflow-y-auto">
                    <RealEstateDetailPanel
                      object={selectedObject}
                      detail={selectedDetail}
                    />
                  </div>
                </div>
              </div>
            </PageSection>
          </div>
        ) : null}

        {/* Desktop: fallback — plain table без выбранного объекта */}
        {(!selectedObject || !selectedDetail) && (
          <div className="hidden lg:block lg:h-full">
            <PageSection
              title={t("demo.registry.title")}
              subtitle={t("demo.registry.subtitle")}
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
                  {t("demo.registry.demoHintDesktop")}
                </p>
              </div>
              <div className="min-h-0 flex-1 lg:overflow-hidden">
                <RealEstateTable
                  items={sortedObjects}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                  sort={sort}
                  onSort={handleSort}
                />
              </div>
            </PageSection>
          </div>
        )}

        {/* Mobile: всегда plain table */}
        <div className="lg:hidden">
          <PageSection
            title={t("demo.registry.title")}
            subtitle={t("demo.registry.subtitle")}
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
                {t("demo.registry.demoHintMobile")}
              </p>
            </div>
            <RealEstateTable
              items={sortedObjects}
              selectedId={selectedId}
              onSelect={setSelectedId}
              sort={sort}
              onSort={handleSort}
            />
          </PageSection>
        </div>
      </div>

      {selectedObject && selectedDetail ? (
        <MobileDetailDrawer
          object={selectedObject}
          detail={selectedDetail}
          onClose={() => setSelectedId(null)}
        />
      ) : null}

      {/* Drilldown modal */}
      <DrilldownModal
        open={drilldown !== null}
        onClose={() => setDrilldown(null)}
        title={drilldownTitle}
      >
        {drilldown === "geography" ? (
          <RegionStructureCard items={regionStructure} />
        ) : drilldown === "encumbrances" ? (
          <RankedListCard title={t("drilldown.encumberedList")} items={encumberedObjects} />
        ) : drilldown === "area_top" ? (
          <RankedListCard title={t("drilldown.areaTopList")} items={topByArea} />
        ) : (
          <CriticalObjectsTable items={criticalObjects} />
        )}
      </DrilldownModal>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

const RealEstateTab: React.FC<RealEstateTabProps> = ({
  dealId: _dealId,
  currentRunId: _currentRunId,
}) => {
  const [mode, setMode] = React.useState<PreviewMode>("intro");

  return (
    <div className="lg:flex lg:h-full lg:min-h-0 lg:flex-col lg:overflow-hidden">
      {mode === "intro" ? (
        <IntroScreen onOpenDemo={() => setMode("demo")} />
      ) : (
        <DemoScreen onBack={() => setMode("intro")} />
      )}
    </div>
  );
};

export default RealEstateTab;



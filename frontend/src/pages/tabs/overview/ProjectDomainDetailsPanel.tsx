// =============================================================
// src/pages/tabs/overview/ProjectDomainDetailsPanel.tsx
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  ChevronRight,
  ChevronDown,
  FileText,
  X,
} from "lucide-react";
import { CollapsedPipelineRail } from "./CollapsedPipelineRail";
import { PipelineLayoutProvider } from "./pipelineLayoutContext";
import type { Deal } from "../../../types";
import DocumentsPipelinePanel from "./DocumentsPipelinePanel";
import { LLMUsageWidget } from "./LLMUsageWidget";
import { DocumentsOverviewWidget } from "./DocumentsOverviewWidget";
import { AnalysisResultsWidget } from "./AnalysisResultsWidget";
import { RunSummaryPanel } from "./RunSummaryPanel";
import { useDealLLMUsage } from "../../../api/deals";
import { useDocuments } from "../../../api/documents";
import { useRunProgress, useRunSummary } from "../../../api/runs";
import {
  getPersistedOutputLocale,
  setPersistedOutputLocale,
} from "../../../i18n/localePersistence";
import Button from "../../../components/ui/Button";
import { DEMO_AGGREGATES } from "../counterparties/constants";
import {
  buildCounterpartiesTotals,
  buildCountryStructure,
  buildCriticalCounterparties,
  buildRiskMeta,
  buildTopByValue,
} from "../counterparties/utils";
import {
  buildCriticalObjects,
  buildRealEstateTotals,
  buildRegionStructure,
  buildRiskMeta as buildRealEstateRiskMeta,
  buildTopByArea,
  objectTypeShortLabel,
} from "../real-estate/utils";
import { DEMO_OBJECTS } from "../real-estate/constants";

type DomainKey = "documents" | "counterparties" | "real_estate";

interface ProjectDomainDetailsPanelProps {
  activeDomain: DomainKey;
  onDomainChange: (d: DomainKey) => void;
  runId: string | null;
  deal: Deal;
}

// ---------------------------------------------------------------------------
// Column shell
// ---------------------------------------------------------------------------

interface ColumnShellProps {
  title: string;
  children: React.ReactNode;
}

const ColumnShell: React.FC<ColumnShellProps> = ({ title, children }) => (
  <div className="flex h-full min-h-0 min-w-0 flex-col">
    <p className="mb-2 shrink-0 text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">
      {title}
    </p>
    <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1">
      {children}
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// Counterparties summary (rich preview)
// ---------------------------------------------------------------------------

const CounterpartiesSummary: React.FC = () => {
  const { t } = useTranslation("projects");
  const navigate = useNavigate();
  const location = useLocation();

  const aggregates = DEMO_AGGREGATES;

  const { totalCounterparties, totalContracts, totalContractValue } =
    React.useMemo(() => buildCounterpartiesTotals(aggregates), [aggregates]);

  const critical = React.useMemo(
    () => buildCriticalCounterparties(aggregates),
    [aggregates],
  );
  const sanctionsCount = aggregates.filter((item) => item.sanctionsFlag).length;
  const bankruptcyCount = aggregates.filter((item) => item.bankruptcyFlag).length;

  const topByValue = React.useMemo(
    () => buildTopByValue(aggregates).slice(0, 5),
    [aggregates],
  );

  const countryStructure = React.useMemo(
    () => buildCountryStructure(aggregates).slice(0, 5),
    [aggregates],
  );

  const attentionRows = React.useMemo(() => {
    return aggregates
      .filter((item) => {
        const risk = buildRiskMeta(item);
        return (
          item.reviewStatus === "critical" ||
          item.reviewStatus === "needs_review" ||
          item.sanctionsFlag ||
          item.bankruptcyFlag ||
          risk.tone === "high"
        );
      })
      .slice(0, 6)
      .map((item) => {
        const risk = buildRiskMeta(item);
        const flags: string[] = [];
        if (item.sanctionsFlag) {
          flags.push(
            t("overviewPanels.domainDetails.counterparties.sanctions"),
          );
        }
        if (item.bankruptcyFlag) {
          flags.push(
            t("overviewPanels.domainDetails.counterparties.bankruptcy"),
          );
        }
        if (item.reviewStatus === "critical") {
          flags.push(
            t("overviewPanels.domainDetails.counterparties.critical"),
          );
        }
        return {
          id: item.id,
          name: item.name,
          country: item.country,
          contractCount: item.contractCount,
          value: `$${item.contractValueUsdM}m`,
          riskLabel: risk.label,
          riskTone: risk.tone,
          flags,
        };
      });
  }, [aggregates, t]);

  const handleOpenFull = React.useCallback(() => {
    const params = new URLSearchParams(location.search);
    params.set("tab", "counterparties");
    navigate(
      {
        pathname: location.pathname,
        search: params.toString(),
      },
      { replace: false },
    );
  }, [location.pathname, location.search, navigate]);

  const riskToneClass = (tone: string) => {
    if (tone === "high") {
      return "border-[var(--color-error-border)] bg-[var(--color-error-bg)] text-[var(--color-error-text)]";
    }
    if (tone === "medium") {
      return "border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] text-[var(--color-warning-text)]";
    }
    return "border-[var(--color-success-border)] bg-[var(--color-success-bg)] text-[var(--color-success-text)]";
  };

  const countryTotal = countryStructure.reduce((sum, item) => sum + item.count, 0);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain pr-1 pb-4">
        {/* KPI strip — same language as full Counterparties demo */}
        <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3.5 shadow-sm">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {t("overviewPanels.domainDetails.counterparties.total")}
            </p>
            <p className="mt-1 text-2xl font-semibold tabular-nums text-[var(--text-primary)]">
              {totalCounterparties}
            </p>
            <p className="mt-1 text-[11px] text-[var(--text-muted)]">
              {t("overviewPanels.domainDetails.counterparties.geography")}
            </p>
          </div>

          <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3.5 shadow-sm">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {t("overviewPanels.domainDetails.counterparties.contracts")}
            </p>
            <p className="mt-1 text-2xl font-semibold tabular-nums text-[var(--text-primary)]">
              {totalContracts}
            </p>
            <p className="mt-1 text-[11px] text-[var(--text-muted)]">
              {t("overviewPanels.domainDetails.counterparties.contractsShort")}
            </p>
          </div>

          <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3.5 shadow-sm">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {t("overviewPanels.domainDetails.counterparties.value")}
            </p>
            <p className="mt-1 text-2xl font-semibold tabular-nums text-[var(--text-primary)]">
              ${totalContractValue}m
            </p>
          </div>

          <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3.5 shadow-sm">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {t("overviewPanels.domainDetails.counterparties.critical")}
            </p>
            <p className="mt-1 text-2xl font-semibold tabular-nums text-[var(--color-error-text)]">
              {critical.length}
            </p>
            <p className="mt-1 text-[11px] text-[var(--text-muted)]">
              {t("overviewPanels.domainDetails.counterparties.sanctions")}:{" "}
              <span className="font-semibold text-[var(--color-error-text)]">
                {sanctionsCount}
              </span>
              {" · "}
              {t("overviewPanels.domainDetails.counterparties.bankruptcy")}:{" "}
              <span className="font-semibold text-[var(--color-warning-text)]">
                {bankruptcyCount}
              </span>
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {/* Top by value */}
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
            <div className="border-b border-[var(--border-subtle)] px-4 py-3">
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {t("overviewPanels.domainDetails.counterparties.topByValue")}
              </p>
            </div>
            <div className="divide-y divide-[var(--border-subtle)]">
              {topByValue.map((item, index) => (
                <div
                  key={`${item.name}-${index}`}
                  className="flex items-center gap-3 px-4 py-3"
                >
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--bg-elevated-soft)] text-[12px] font-semibold text-[var(--text-primary)]">
                    {index + 1}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-[var(--text-primary)]">
                      {item.name}
                    </p>
                    <p className="text-[12px] text-[var(--text-muted)]">
                      {item.country}
                    </p>
                  </div>
                  <div className="shrink-0 text-sm font-semibold tabular-nums text-[var(--text-primary)]">
                    {item.value}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Geography */}
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
            <div className="border-b border-[var(--border-subtle)] px-4 py-3">
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {t("overviewPanels.domainDetails.counterparties.geography")}
              </p>
            </div>
            <div className="space-y-3 px-4 py-4">
              {countryStructure.map((item) => {
                const share =
                  countryTotal > 0
                    ? Math.round((item.count / countryTotal) * 100)
                    : 0;
                return (
                  <div key={item.country}>
                    <div className="mb-1 flex items-center justify-between gap-3">
                      <p className="text-sm text-[var(--text-primary)]">
                        {item.country}
                      </p>
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
        </div>

        {/* Needs attention table */}
        <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
          <div className="border-b border-[var(--border-subtle)] px-4 py-3">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {t("overviewPanels.domainDetails.counterparties.needsAttention")}
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-[var(--bg-elevated-soft)]">
                <tr>
                  <th className="px-4 py-2.5 font-semibold text-[var(--text-primary)]">
                    #
                  </th>
                  <th className="px-4 py-2.5 font-semibold text-[var(--text-primary)]">
                    {t("overviewPanels.domainDetails.counterparties.total")}
                  </th>
                  <th className="px-4 py-2.5 font-semibold text-[var(--text-primary)]">
                    {t("overviewPanels.domainDetails.counterparties.country")}
                  </th>
                  <th className="px-4 py-2.5 font-semibold text-[var(--text-primary)]">
                    {t(
                      "overviewPanels.domainDetails.counterparties.contractsShort",
                    )}
                  </th>
                  <th className="px-4 py-2.5 font-semibold text-[var(--text-primary)]">
                    {t("overviewPanels.domainDetails.counterparties.value")}
                  </th>
                  <th className="px-4 py-2.5 font-semibold text-[var(--text-primary)]">
                    {t("overviewPanels.domainDetails.counterparties.risk")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {attentionRows.map((row, index) => (
                  <tr
                    key={row.id}
                    className="border-t border-[var(--border-subtle)] align-top"
                  >
                    <td className="px-4 py-3 tabular-nums text-[var(--text-muted)]">
                      {index + 1}
                    </td>
                    <td className="px-4 py-3">
                      <p className="font-medium text-[var(--text-primary)]">
                        {row.name}
                      </p>
                      {row.flags.length > 0 ? (
                        <div className="mt-1.5 flex flex-wrap gap-1.5">
                          {row.flags.map((flag) => (
                            <span
                              key={flag}
                              className="inline-flex rounded-full border border-[var(--color-error-border)] bg-[var(--color-error-bg)] px-2 py-0.5 text-[10px] font-medium text-[var(--color-error-text)]"
                            >
                              {flag}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </td>
                    <td className="px-4 py-3 text-[var(--text-secondary)]">
                      {row.country}
                    </td>
                    <td className="px-4 py-3 tabular-nums text-[var(--text-primary)]">
                      {row.contractCount}
                    </td>
                    <td className="px-4 py-3 tabular-nums text-[var(--text-primary)]">
                      {row.value}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={[
                          "inline-flex rounded-full border px-2.5 py-1 text-[11px] font-medium",
                          riskToneClass(row.riskTone),
                        ].join(" ")}
                      >
                        {row.riskLabel}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <p className="text-[11px] leading-5 text-[var(--text-muted)]">
          {t("overviewPanels.domainDetails.counterparties.demoNote")}
        </p>
      </div>

      {/* Sticky footer CTA */}
      <div className="shrink-0 border-t border-[var(--border-subtle)] bg-[var(--bg-card)] pt-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-[11px] text-[var(--text-muted)]">
            {t("overviewPanels.domainDetails.counterparties.openFullHint")}
          </p>
          <Button
            type="button"
            variant="primary"
            size="sm"
            onClick={handleOpenFull}
            rightIcon={<ArrowRight className="h-4 w-4" aria-hidden />}
            className="w-full sm:ml-auto sm:w-auto"
          >
            {t("overviewPanels.domainDetails.counterparties.openFull")}
          </Button>
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Real estate summary
// ---------------------------------------------------------------------------

const RealEstateSummary: React.FC = () => {
  const { t, i18n } = useTranslation("projects");
  const navigate = useNavigate();
  const location = useLocation();

  const objects = DEMO_OBJECTS;

  const { totalObjects, totalLand, totalBuildingsAndPremises, totalEncumbered } =
    React.useMemo(() => buildRealEstateTotals(objects), [objects]);

  const ownershipReviewCount = objects.filter(
    (item) =>
      item.ownership_status === "review" ||
      item.ownership_status === "not_confirmed",
  ).length;

  const topByArea = React.useMemo(
    () => buildTopByArea(objects, t, i18n.language).slice(0, 5),
    [objects, t, i18n.language],
  );

  const regionStructure = React.useMemo(
    () => buildRegionStructure(objects).slice(0, 5),
    [objects],
  );

  const criticalObjects = React.useMemo(
    () => buildCriticalObjects(objects, t),
    [objects, t],
  );

  const attentionRows = React.useMemo(() => {
    return objects
      .filter((item) => {
        const risk = buildRealEstateRiskMeta(item);
        return (
          item.encumbrance === true ||
          item.ownership_status === "review" ||
          item.ownership_status === "not_confirmed" ||
          risk.tone === "high"
        );
      })
      .slice(0, 6)
      .map((item) => {
        const risk = buildRealEstateRiskMeta(item);
        const flags: string[] = [];
        if (item.encumbrance === true) {
          flags.push(t("overviewPanels.domainDetails.realEstate.encumbered"));
        }
        if (
          item.ownership_status === "review" ||
          item.ownership_status === "not_confirmed"
        ) {
          flags.push(
            t("overviewPanels.domainDetails.realEstate.ownershipReview"),
          );
        }
        if (risk.tone === "high") {
          flags.push(t("overviewPanels.domainDetails.realEstate.highRisk"));
        }
        return {
          id: item.id,
          name: item.address ?? item.cadastral_number ?? item.id,
          region: item.region,
          typeLabel: objectTypeShortLabel(item.object_type),
          areaLabel: item.area_sqm
            ? `${item.area_sqm.toLocaleString(i18n.language)} m²`
            : "—",
          documents: item.document_count,
          riskLabel: risk.label,
          riskTone: risk.tone,
          flags,
        };
      });
  }, [objects, t, i18n.language]);

  const handleOpenFull = React.useCallback(() => {
    const params = new URLSearchParams(location.search);
    params.set("tab", "real_estate");
    navigate(
      {
        pathname: location.pathname,
        search: params.toString(),
      },
      { replace: false },
    );
  }, [location.pathname, location.search, navigate]);

  const riskToneClass = (tone: string) => {
    if (tone === "high") {
      return "border-[var(--color-error-border)] bg-[var(--color-error-bg)] text-[var(--color-error-text)]";
    }
    if (tone === "medium") {
      return "border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] text-[var(--color-warning-text)]";
    }
    return "border-[var(--color-success-border)] bg-[var(--color-success-bg)] text-[var(--color-success-text)]";
  };

  const regionTotal = regionStructure.reduce((sum, item) => sum + item.count, 0);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain pr-1 pb-4">
        {/* KPI strip */}
        <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3.5 shadow-sm">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {t("overviewPanels.domainDetails.realEstate.objects")}
            </p>
            <p className="mt-1 text-2xl font-semibold tabular-nums text-[var(--text-primary)]">
              {totalObjects}
            </p>
            <p className="mt-1 text-[11px] text-[var(--text-muted)]">
              {t("overviewPanels.domainDetails.realEstate.topRegions")}
            </p>
          </div>

          <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3.5 shadow-sm">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {t("overviewPanels.domainDetails.realEstate.land")}
            </p>
            <p className="mt-1 text-2xl font-semibold tabular-nums text-[var(--text-primary)]">
              {totalLand}
            </p>
          </div>

          <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3.5 shadow-sm">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {t("overviewPanels.domainDetails.realEstate.buildings")}
            </p>
            <p className="mt-1 text-2xl font-semibold tabular-nums text-[var(--text-primary)]">
              {totalBuildingsAndPremises}
            </p>
          </div>

          <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3.5 shadow-sm">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              {t("overviewPanels.domainDetails.realEstate.encumbered")}
            </p>
            <p className="mt-1 text-2xl font-semibold tabular-nums text-[var(--color-error-text)]">
              {totalEncumbered}
            </p>
            <p className="mt-1 text-[11px] text-[var(--text-muted)]">
              {t("overviewPanels.domainDetails.realEstate.ownershipReview")}:{" "}
              <span className="font-semibold text-[var(--color-warning-text)]">
                {ownershipReviewCount}
              </span>
              {" · "}
              {t("overviewPanels.domainDetails.realEstate.highRisk")}:{" "}
              <span className="font-semibold text-[var(--color-error-text)]">
                {criticalObjects.length}
              </span>
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {/* Top by area */}
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
            <div className="border-b border-[var(--border-subtle)] px-4 py-3">
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {t("overviewPanels.domainDetails.realEstate.topByArea")}
              </p>
            </div>
            <div className="divide-y divide-[var(--border-subtle)]">
              {topByArea.map((item, index) => (
                <div
                  key={`${item.name}-${index}`}
                  className="flex items-center gap-3 px-4 py-3"
                >
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--bg-elevated-soft)] text-[12px] font-semibold text-[var(--text-primary)]">
                    {index + 1}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-[var(--text-primary)]">
                      {item.name}
                    </p>
                    <p className="text-[12px] text-[var(--text-muted)]">
                      {item.subtitle}
                    </p>
                  </div>
                  <div className="shrink-0 text-sm font-semibold tabular-nums text-[var(--text-primary)]">
                    {item.value}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Regions */}
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
            <div className="border-b border-[var(--border-subtle)] px-4 py-3">
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {t("overviewPanels.domainDetails.realEstate.topRegions")}
              </p>
            </div>
            <div className="space-y-3 px-4 py-4">
              {regionStructure.map((item) => {
                const share =
                  regionTotal > 0
                    ? Math.round((item.count / regionTotal) * 100)
                    : 0;
                return (
                  <div key={item.region}>
                    <div className="mb-1 flex items-center justify-between gap-3">
                      <p className="text-sm text-[var(--text-primary)]">
                        {item.region}
                      </p>
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
        </div>

        {/* Needs attention */}
        <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
          <div className="border-b border-[var(--border-subtle)] px-4 py-3">
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {t("overviewPanels.domainDetails.realEstate.needsAttention")}
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-[var(--bg-elevated-soft)]">
                <tr>
                  <th className="px-4 py-2.5 font-semibold text-[var(--text-primary)]">
                    #
                  </th>
                  <th className="px-4 py-2.5 font-semibold text-[var(--text-primary)]">
                    {t("overviewPanels.domainDetails.realEstate.objects")}
                  </th>
                  <th className="px-4 py-2.5 font-semibold text-[var(--text-primary)]">
                    {t("overviewPanels.domainDetails.realEstate.region")}
                  </th>
                  <th className="px-4 py-2.5 font-semibold text-[var(--text-primary)]">
                    {t("overviewPanels.domainDetails.realEstate.type")}
                  </th>
                  <th className="px-4 py-2.5 font-semibold text-[var(--text-primary)]">
                    {t("overviewPanels.domainDetails.realEstate.area")}
                  </th>
                  <th className="px-4 py-2.5 font-semibold text-[var(--text-primary)]">
                    {t("overviewPanels.domainDetails.realEstate.documents")}
                  </th>
                  <th className="px-4 py-2.5 font-semibold text-[var(--text-primary)]">
                    {t("overviewPanels.domainDetails.realEstate.risk")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {attentionRows.map((row, index) => (
                  <tr
                    key={row.id}
                    className="border-t border-[var(--border-subtle)] align-top"
                  >
                    <td className="px-4 py-3 tabular-nums text-[var(--text-muted)]">
                      {index + 1}
                    </td>
                    <td className="px-4 py-3">
                      <p className="font-medium text-[var(--text-primary)]">
                        {row.name}
                      </p>
                      {row.flags.length > 0 ? (
                        <div className="mt-1.5 flex flex-wrap gap-1.5">
                          {row.flags.map((flag) => (
                            <span
                              key={flag}
                              className="inline-flex rounded-full border border-[var(--color-error-border)] bg-[var(--color-error-bg)] px-2 py-0.5 text-[10px] font-medium text-[var(--color-error-text)]"
                            >
                              {flag}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </td>
                    <td className="px-4 py-3 text-[var(--text-secondary)]">
                      {row.region}
                    </td>
                    <td className="px-4 py-3 text-[var(--text-secondary)]">
                      {row.typeLabel}
                    </td>
                    <td className="px-4 py-3 tabular-nums text-[var(--text-primary)]">
                      {row.areaLabel}
                    </td>
                    <td className="px-4 py-3 tabular-nums text-[var(--text-primary)]">
                      {row.documents}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={[
                          "inline-flex rounded-full border px-2.5 py-1 text-[11px] font-medium",
                          riskToneClass(row.riskTone),
                        ].join(" ")}
                      >
                        {row.riskLabel}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <p className="text-[11px] leading-5 text-[var(--text-muted)]">
          {t("overviewPanels.domainDetails.realEstate.demoNote")}
        </p>
      </div>

      {/* Sticky CTA */}
      <div className="shrink-0 border-t border-[var(--border-subtle)] bg-[var(--bg-card)] pt-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-[11px] text-[var(--text-muted)]">
            {t("overviewPanels.domainDetails.realEstate.openFullHint")}
          </p>
          <Button
            type="button"
            variant="primary"
            size="sm"
            onClick={handleOpenFull}
            rightIcon={<ArrowRight className="h-4 w-4" aria-hidden />}
            className="w-full sm:ml-auto sm:w-auto"
          >
            {t("overviewPanels.domainDetails.realEstate.openFull")}
          </Button>
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// DocumentsContent
// ---------------------------------------------------------------------------

function isTerminalRunStatus(status: string | undefined): boolean {
  return (
    status === "completed" ||
    status === "completed_with_errors" ||
    status === "failed"
  );
}

const CollapsedPipelineSummary: React.FC<{
  runId: string | null;
  onExpand: () => void;
  summaryStatus?: string | null;
}> = ({ runId, onExpand }) => {
  const { data: progress } = useRunProgress(runId);

  return (
    <CollapsedPipelineRail
      runId={runId}
      onExpand={onExpand}
      runStatus={progress?.run_status ?? null}
    />
  );
};

const CollapsedSummaryRail: React.FC<{
  onExpand: () => void;
  hasErrors?: boolean;
}> = ({ onExpand, hasErrors = false }) => {
  const { t } = useTranslation("projects");

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col">
      <p className="mb-2 shrink-0 text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">
        {t("overviewPanels.domainDetails.columns.summary")}
      </p>

      <button
        type="button"
        onClick={onExpand}
        title={t("overviewPanels.domainDetails.expandSummary")}
        aria-label={t("overviewPanels.domainDetails.expandSummaryAria")}
        className={`group min-h-0 flex-1 overflow-hidden rounded-xl border p-0 text-left transition-colors ${
          hasErrors
            ? "border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] hover:border-[var(--color-warning)]"
            : "border-[var(--border)] bg-[var(--bg-card)] hover:border-[var(--accent-primary)] hover:bg-[var(--bg-elevated-soft)]"
        }`}
      >
        <div className="flex h-full w-full flex-col items-center justify-center gap-2 py-4">
          <div
            className={`flex h-10 w-10 items-center justify-center rounded-full transition-colors ${
              hasErrors
                ? "bg-[var(--color-warning)] text-white"
                : "bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] group-hover:bg-[var(--accent-primary)] group-hover:text-white"
            }`}
          >
            <FileText className="h-5 w-5" />
          </div>
          <ChevronRight className="h-3.5 w-3.5 text-[var(--text-muted)] transition-transform group-hover:translate-x-0.5" />
        </div>
      </button>
    </div>
  );
};

const DocumentsContent: React.FC<{
  runId: string | null;
  dealId: string;
}> = ({ runId, dealId }) => {
  const { t, i18n } = useTranslation("projects");
  const [isPipelineExpanded, setIsPipelineExpanded] = React.useState(false);
  const [isSummaryExpanded, setIsSummaryExpanded] = React.useState(false);
  const [isMobilePipelineOpen, setIsMobilePipelineOpen] = React.useState(false);

  // Summary locale state с persistence (инициализация из localStorage)
  const [summaryLocale, setSummaryLocaleState] = React.useState<string>(() => {
    return getPersistedOutputLocale() || "ru";
  });

  // Wrapper для записи в localStorage + state
  const setSummaryLocale = (locale: string) => {
    setPersistedOutputLocale(locale);
    setSummaryLocaleState(locale);
  };

  const { data: progress } = useRunProgress(runId);
  const isTerminal = isTerminalRunStatus(progress?.run_status);
  const isRunActive = !!runId && !isTerminal;

  const { data: summary, refetch: refetchSummary } = useRunSummary(
    runId,
    summaryLocale,
  );

  React.useEffect(() => {
    if (isTerminal && summary?.status === "ready") {
      setIsPipelineExpanded(false);
      setIsSummaryExpanded(true);
    }
  }, [isTerminal, summary?.status]);

  React.useEffect(() => {
    if (!isTerminal) {
      setIsPipelineExpanded(false);
      setIsSummaryExpanded(false);
    }
  }, [isTerminal]);

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

  const documentNames = React.useMemo<Record<string, string>>(() => {
    const map: Record<string, string> = {};
    for (const doc of documents ?? []) {
      if (doc.id && doc.filename) map[doc.id] = doc.filename;
    }
    return map;
  }, [documents]);

  return (
    <>
      {!isTerminal && (
        <div className="hidden h-full min-h-0 xl:block">
          <div className="flex h-full min-h-0 flex-col">
            <p className="mb-2 shrink-0 text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">
              {t("overviewPanels.domainDetails.columns.pipeline")}
            </p>
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1">
              <DocumentsPipelinePanel runId={runId} />
            </div>
          </div>
        </div>
      )}

      {isTerminal && isPipelineExpanded && (
        <div className="hidden h-full min-h-0 xl:flex xl:flex-col rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm overflow-hidden">
          <div className="shrink-0 flex items-start justify-between border-b border-[var(--border-subtle)] px-5 py-4">
            <div>
              <h3 className="text-sm font-semibold text-[var(--text-primary)]">
                {t("overviewPanels.domainDetails.columns.pipeline")}
              </h3>
              <p className="mt-1 text-[11px] text-[var(--text-muted)]">
                {progress?.started_at && (
                  <>
                    {t("overviewPanels.domainDetails.pipelineStarted", {
                      time: new Date(progress.started_at).toLocaleString(
                        i18n.language,
                      ),
                    })}{" "}
                    ·{" "}
                  </>
                )}
                {progress?.elapsed_seconds != null && (
                  <>
                    {t("overviewPanels.domainDetails.pipelineElapsed", {
                      m: Math.floor(progress.elapsed_seconds / 60),
                      s: progress.elapsed_seconds % 60,
                    })}
                  </>
                )}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setIsPipelineExpanded(false)}
              className="rounded-lg p-1.5 text-[var(--text-muted)] transition hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)]"
              title={t("overviewPanels.domainDetails.collapsePipeline")}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain p-5">
            <DocumentsPipelinePanel runId={runId} />
          </div>
        </div>
      )}

      {isTerminal && !isPipelineExpanded && (
        <div
          className="hidden h-full min-h-0 grid-rows-[minmax(0,1fr)] gap-4 xl:grid"
          style={{
            gridTemplateColumns: isSummaryExpanded
              ? "minmax(72px,72px) minmax(0,3fr)"
              : "minmax(72px,72px) minmax(72px,72px) minmax(0,1fr) minmax(0,1fr) minmax(0,1fr)",
          }}
        >
          <div className="flex h-full min-h-0 flex-col">
            <div className="h-full flex flex-col">
              <CollapsedPipelineSummary
                runId={runId}
                onExpand={() => setIsPipelineExpanded(true)}
                summaryStatus={summary?.status ?? null}
              />
            </div>
          </div>

          {isSummaryExpanded ? (
            <div className="flex h-full min-h-0 flex-col">
              <div className="h-full flex flex-col">
                {summary && (
                  <RunSummaryPanel
                    summary={summary}
                    onRegenerate={() => refetchSummary()}
                    onLocaleChange={setSummaryLocale}
                    onClose={() => setIsSummaryExpanded(false)}
                    documents={documents}
                    dealId={dealId}
                  />
                )}
              </div>
            </div>
          ) : (
            <>
              <div className="flex h-full min-h-0 flex-col">
                <div className="h-full flex flex-col">
                  <CollapsedSummaryRail
                    onExpand={() => setIsSummaryExpanded(true)}
                    hasErrors={summary?.status === "failed"}
                  />
                </div>
              </div>

              <ColumnShell
                title={t("overviewPanels.domainDetails.columns.documentsOverview")}
              >
                <DocumentsOverviewWidget
                  documents={documents}
                  isLoading={documentsLoading}
                  isError={documentsError}
                />
              </ColumnShell>

              <ColumnShell
                title={t("overviewPanels.domainDetails.columns.analysisResults")}
              >
                <AnalysisResultsWidget dealId={dealId} runId={runId} />
              </ColumnShell>

              <ColumnShell
                title={t("overviewPanels.domainDetails.columns.llmUsage")}
              >
                <LLMUsageWidget
                  data={llmUsage}
                  isLoading={llmLoading}
                  isError={llmError}
                  documentNames={documentNames}
                />
              </ColumnShell>
            </>
          )}
        </div>
      )}

      <div className="grid min-h-0 grid-cols-1 gap-4 xl:hidden lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className="min-w-0">
          <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
            <button
              type="button"
              onClick={() => setIsMobilePipelineOpen((prev) => !prev)}
              aria-expanded={isMobilePipelineOpen}
              aria-controls="mobile-pipeline-content"
              className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition hover:bg-[var(--bg-elevated-soft)]"
            >
              <span className="text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">
                {t("overviewPanels.domainDetails.columns.pipeline")}
              </span>
              <ChevronDown
                className={[
                  "h-4 w-4 shrink-0 text-[var(--text-muted)] transition-transform duration-200",
                  isMobilePipelineOpen ? "rotate-180" : "",
                ].join(" ")}
                aria-hidden
              />
            </button>

            {isMobilePipelineOpen && (
              <>
                <div className="mx-4 border-t border-[var(--border-subtle)]" />
                <div id="mobile-pipeline-content" className="px-4 py-3">
                  <DocumentsPipelinePanel runId={runId} />
                </div>
              </>
            )}
          </section>
        </div>

        {isTerminal && (
          <div className="min-w-0 space-y-4">
            {summary && (
              <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
                <button
                  type="button"
                  onClick={() => setIsSummaryExpanded((prev) => !prev)}
                  aria-expanded={isSummaryExpanded}
                  aria-controls="mobile-summary-content"
                  className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition hover:bg-[var(--bg-elevated-soft)]"
                >
                  <span className="text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">
                    {t("overviewPanels.domainDetails.columns.summary")}
                  </span>
                  <ChevronDown
                    className={[
                      "h-4 w-4 shrink-0 text-[var(--text-muted)] transition-transform duration-200",
                      isSummaryExpanded ? "rotate-180" : "",
                    ].join(" ")}
                    aria-hidden
                  />
                </button>

                {isSummaryExpanded && (
                  <>
                    <div className="mx-4 border-t border-[var(--border-subtle)]" />
                    <div id="mobile-summary-content" className="px-4 py-3">
                      <RunSummaryPanel
                        summary={summary}
                        onRegenerate={() => refetchSummary()}
                        onLocaleChange={setSummaryLocale}
                        onClose={() => setIsSummaryExpanded(false)}
                        documents={documents}
                        dealId={dealId}
                      />
                    </div>
                  </>
                )}
              </section>
            )}
            <div>
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">
                {t("overviewPanels.domainDetails.columns.documentsOverview")}
              </p>
              <DocumentsOverviewWidget
                documents={documents}
                isLoading={documentsLoading}
                isError={documentsError}
              />
            </div>
            <div>
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">
                {t("overviewPanels.domainDetails.columns.analysisResults")}
              </p>
              <AnalysisResultsWidget dealId={dealId} runId={runId} />
            </div>
            <div>
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">
                {t("overviewPanels.domainDetails.columns.llmUsage")}
              </p>
              <LLMUsageWidget
                data={llmUsage}
                isLoading={llmLoading}
                isError={llmError}
                documentNames={documentNames}
              />
            </div>
          </div>
        )}
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
  const { t } = useTranslation("projects");

  const domainLabel =
    activeDomain === "documents"
      ? t("overviewPanels.domainDetails.domains.documents")
      : activeDomain === "counterparties"
        ? t("overviewPanels.domainDetails.domains.counterparties")
        : t("overviewPanels.domainDetails.domains.realEstate");

  return (
    <section className="flex flex-col lg:h-full lg:min-h-0 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm xl:rounded-t-none xl:border-t-0">
      <div className="relative flex flex-col text-[var(--text-primary)] lg:min-h-0 lg:flex-1">
        <div className="shrink-0 px-5">
          <div className="py-3">
            <div className="flex items-center gap-1.5">
              <span
                className="h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--accent-primary)]"
                aria-hidden
              />
              <span className="text-xs font-semibold text-[var(--accent-primary)]">
                {domainLabel}
              </span>
              <ChevronRight
                className="h-3 w-3 shrink-0 text-[var(--text-muted)]"
                aria-hidden
              />
              <h2 className="text-sm font-semibold text-[var(--text-primary)]">
                {t("overviewPanels.domainDetails.detailsTitle")}
              </h2>
            </div>
          </div>
          <div className="border-t border-[var(--border-subtle)]" />
        </div>

        <div className="px-5 py-4 lg:min-h-0 lg:flex-1 lg:overflow-hidden">
          {activeDomain === "documents" && (
            <PipelineLayoutProvider>
              <DocumentsContent runId={runId} dealId={deal.id} />
            </PipelineLayoutProvider>
          )}
          {activeDomain === "counterparties" && (
            <div className="flex h-full min-h-0 flex-col lg:overflow-hidden">
              <CounterpartiesSummary />
            </div>
          )}
          {activeDomain === "real_estate" && (
            <div className="flex h-full min-h-0 flex-col lg:overflow-hidden">
              <RealEstateSummary />
            </div>
          )}
        </div>
      </div>
    </section>
  );
};

export default ProjectDomainDetailsPanel;



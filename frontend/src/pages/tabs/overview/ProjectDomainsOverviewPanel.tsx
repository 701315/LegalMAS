// =============================================================
// src/pages/tabs/overview/ProjectDomainsOverviewPanel.tsx
// Три равные карточки: Документы · Контрагенты · Имущество
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import type { Deal } from "../../../types";
import { useRunProgress } from "../../../api/runs";
import { DEMO_AGGREGATES } from "../counterparties/constants";
import { DEMO_OBJECTS } from "../real-estate/constants";

type DomainKey = "documents" | "counterparties" | "real_estate";
type TranslateFn = (key: string, options?: Record<string, unknown>) => string;

interface ProjectDomainsOverviewPanelProps {
  runId: string | null;
  deal: Deal;
  activeDomain: DomainKey;
  onDomainSelect: (d: DomainKey) => void;
}

function formatRelativeTime(
  iso: string | undefined | null,
  tFn: TranslateFn,
): string {
  if (!iso) return "";
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 5) return tFn("overviewPanels.pipelineStep.justNow");
  if (diff < 60) {
    return tFn("overviewPanels.pipelineStep.secAgo", { count: diff });
  }
  if (diff < 3600) {
    return tFn("overviewPanels.pipelineStep.minAgo", {
      count: Math.floor(diff / 60),
    });
  }
  return tFn("overviewPanels.pipelineStep.hrAgo", {
    count: Math.floor(diff / 3600),
  });
}

const DomainCard: React.FC<{
  isActive: boolean;
  onClick: () => void;
  title: string;
  statusLine: React.ReactNode;
  lines: React.ReactNode[];
  isRunning?: boolean;
}> = ({ isActive, onClick, title, statusLine, lines, isRunning = false }) => (
  <button
    type="button"
    onClick={onClick}
    className={[
      "relative flex min-h-[4rem] w-full min-w-0 flex-col px-2 py-1.5 text-left shadow-sm transition sm:min-h-[4.5rem] sm:px-3 sm:py-2",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]",
      "rounded-2xl",
      isActive ? "xl:rounded-b-none" : "",
      isActive
        ? [
            "border border-[var(--border)]",
            "xl:border-b-0",
            "bg-[var(--bg-card)]",
            "shadow-md",
          ].join(" ")
        : [
            "border border-[var(--border)]",
            "bg-[var(--bg-card)]",
            "hover:bg-[var(--bg-elevated-soft)]",
          ].join(" "),
    ].join(" ")}
  >
    {isActive && (
      <div
        className="pointer-events-none absolute inset-y-0 left-0 w-[3px] rounded-l-2xl bg-[var(--accent-primary)] xl:rounded-bl-none"
        aria-hidden
      />
    )}

    <div className="mb-0.5 flex min-w-0 items-center gap-1">
      <p className="min-w-0 truncate text-[9px] font-semibold uppercase tracking-[0.06em] text-[var(--text-muted)] sm:text-[10px] sm:tracking-[0.12em]">
        {title}
      </p>
      {isRunning && (
        <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-[var(--accent-primary)]" />
      )}
    </div>

    <p
      className={`truncate text-[11px] font-semibold sm:text-xs ${
        isActive
          ? "text-[var(--accent-primary)]"
          : "text-[var(--text-primary)]"
      }`}
    >
      {statusLine}
    </p>

    {lines.length > 0 && (
      <div className="mt-0.5 min-w-0 space-y-0">
        {lines.slice(0, 2).map((line, i) => (
          <p
            key={i}
            className="min-w-0 truncate text-[9px] leading-3.5 text-[var(--text-muted)] sm:text-[10px] sm:leading-4"
          >
            {line}
          </p>
        ))}
      </div>
    )}
  </button>
);

export const ProjectDomainsOverviewPanel: React.FC<
  ProjectDomainsOverviewPanelProps
> = ({ runId, activeDomain, onDomainSelect }) => {
  const { t } = useTranslation("projects");
  const { data: progress } = useRunProgress(runId);

  const docStatus = (() => {
    if (!runId) return t("overviewPanels.domainsOverview.docStatus.notStarted");
    if (!progress) return t("overviewPanels.domainsOverview.docStatus.loading");
    if (progress.run_status === "completed") {
      return t("overviewPanels.domainsOverview.docStatus.completed");
    }
    if (progress.run_status === "completed_with_errors") {
      return t("overviewPanels.domainsOverview.docStatus.completedWithErrors");
    }
    if (progress.run_status === "failed") {
      return t("overviewPanels.domainsOverview.docStatus.failed");
    }
    if (progress.run_status === "running") {
      return t("overviewPanels.domainsOverview.docStatus.running");
    }
    return t("overviewPanels.domainsOverview.docStatus.pending");
  })();

  const docRunning = progress?.run_status === "running";

  const stepCode = progress?.current_step_code;
  const currentStep = stepCode
    ? t(`overviewPanels.pipelineStep.stepTitles.${stepCode}`, {
        defaultValue: progress?.current_step_title ?? "",
      })
    : progress?.current_step_title;

  const activeStep = progress?.steps.find((s) => s.status === "running");
  const subProgress = activeStep?.sub_progress;

  const docLines: React.ReactNode[] = [];
  if (currentStep) {
    docLines.push(
      t("overviewPanels.domainsOverview.stage", { title: currentStep }),
    );
  }
  if (subProgress && subProgress.total > 0) {
    const kind = t(
      `overviewPanels.domainsOverview.subKinds.${subProgress.kind}`,
      { defaultValue: subProgress.kind },
    );
    docLines.push(
      t("overviewPanels.domainsOverview.subProgress", {
        current: subProgress.current,
        total: subProgress.total,
        kind,
      }),
    );
  }
  if (progress?.last_activity_at && docRunning && docLines.length < 2) {
    docLines.push(
      t("overviewPanels.domainsOverview.updated", {
        time: formatRelativeTime(progress.last_activity_at, t),
      }),
    );
  }
  if (progress?.documents_total && docLines.length === 0) {
    docLines.push(
      t("overviewPanels.domainsOverview.documentsTotal", {
        count: progress.documents_total,
      }),
    );
  }

  const totalCounterparties = DEMO_AGGREGATES.length;
  const needsAttention = DEMO_AGGREGATES.filter(
    (item) =>
      item.reviewStatus === "critical" || item.reviewStatus === "needs_review",
  ).length;
  const sanctionsBankruptcy = DEMO_AGGREGATES.filter(
    (item) => item.sanctionsFlag || item.bankruptcyFlag,
  ).length;

  const totalObjects = DEMO_OBJECTS.length;
  const encumbered = DEMO_OBJECTS.filter(
    (item) => item.encumbrance === true,
  ).length;
  const ownershipReview = DEMO_OBJECTS.filter(
    (item) =>
      item.ownership_status === "review" ||
      item.ownership_status === "not_confirmed",
  ).length;

  return (
    <section
      className={[
        "rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm",
        "xl:rounded-b-none xl:border-b-0 xl:shadow-none",
      ].join(" ")}
    >
      <div className="px-5 py-2">
        <h2 className="text-sm font-semibold text-[var(--text-primary)]">
          {t("overviewPanels.domainsOverview.sectionTitle")}
        </h2>
      </div>

      <div className="grid grid-cols-3 gap-1.5 px-3 pb-3 sm:gap-2 sm:px-5">
        <DomainCard
          isActive={activeDomain === "documents"}
          onClick={() => onDomainSelect("documents")}
          title={t("overviewPanels.domainsOverview.domains.documents")}
          statusLine={docStatus}
          lines={docLines}
          isRunning={docRunning}
        />

        <DomainCard
          isActive={activeDomain === "counterparties"}
          onClick={() => onDomainSelect("counterparties")}
          title={t("overviewPanels.domainsOverview.domains.counterparties")}
          statusLine={t("overviewPanels.domainsOverview.counterpartiesFound", {
            count: totalCounterparties,
          })}
          lines={[
            t("overviewPanels.domainsOverview.needAttention", {
              count: needsAttention,
            }),
            t("overviewPanels.domainsOverview.sanctionsBankruptcy", {
              count: sanctionsBankruptcy,
            }),
          ]}
        />

        <DomainCard
          isActive={activeDomain === "real_estate"}
          onClick={() => onDomainSelect("real_estate")}
          title={t("overviewPanels.domainsOverview.domains.realEstate")}
          statusLine={t("overviewPanels.domainsOverview.objectsCount", {
            count: totalObjects,
          })}
          lines={[
            t("overviewPanels.domainsOverview.encumbered", {
              count: encumbered,
            }),
            t("overviewPanels.domainsOverview.ownershipReview", {
              count: ownershipReview,
            }),
          ]}
        />
      </div>
    </section>
  );
};

export default ProjectDomainsOverviewPanel;



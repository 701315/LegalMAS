// =============================================================
// src/pages/tabs/overview/AnalysisResultsWidget.tsx
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import {
  CheckCircle2,
  ChevronRight,
  HelpCircle,
  MinusCircle,
  XCircle,
} from "lucide-react";
import { useRun } from "../../../api/runs";
import { useDealReviewDdGridV1 } from "../../../api/dealReview";
import { useDDGridV1UIStore } from "../dd-grid-v1/ddGridV1.collapseStore";
import { selectDDGridV1DerivedModel } from "../dd-grid-v1/ddGridV1.selectors";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MAX_ITEMS_IN_LIST = 3;
const MAX_CHECKS_IN_GROUP = 5;

// ---------------------------------------------------------------------------
// Helpers — types
// ---------------------------------------------------------------------------

type CheckWorstStatus = "fail" | "unclear" | "pass" | "unknown";

interface CheckAggregate {
  checkId: string;
  checkName: string;
  passCount: number;
  failCount: number;
  unclearCount: number;
  worstStatus: CheckWorstStatus;
}

interface CheckGroupSummary {
  totalChecks: number;
  passedChecksCount: number;
  failedChecksCount: number;
  unclearChecksCount: number;
  topChecks: CheckAggregate[];
}

interface UnclearFindingsItem {
  documentId: string;
  filename: string;
  unclearCount: number;
}

// ---------------------------------------------------------------------------
// Helpers — filename
// ---------------------------------------------------------------------------

function truncateFilename(filename: string, maxLength = 24): string {
  if (filename.length <= maxLength) return filename;
  const ext = filename.split(".").pop();
  const base = filename.slice(0, maxLength - 4 - (ext?.length ?? 0));
  return ext ? `${base}…${ext}` : `${base}…`;
}

function truncateCheckName(name: string, maxLength = 32): string {
  if (name.length <= maxLength) return name;
  return `${name.slice(0, maxLength - 1)}…`;
}

// ---------------------------------------------------------------------------
// Helpers — worst status
// ---------------------------------------------------------------------------

function computeWorstStatus(
  passCount: number,
  failCount: number,
  unclearCount: number,
): CheckWorstStatus {
  if (failCount > 0) return "fail";
  if (unclearCount > 0) return "unclear";
  if (passCount > 0) return "pass";
  return "unknown";
}

function StatusIcon({ status }: { status: CheckWorstStatus }) {
  const iconClass = "h-3 w-3 shrink-0";
  if (status === "fail") {
    return (
      <XCircle
        className={`${iconClass} text-[var(--color-error-text)]`}
        aria-hidden
      />
    );
  }
  if (status === "unclear") {
    return (
      <HelpCircle
        className={`${iconClass} text-[var(--color-warning-text)]`}
        aria-hidden
      />
    );
  }
  if (status === "pass") {
    return (
      <CheckCircle2
        className={`${iconClass} text-[var(--color-success-text)]`}
        aria-hidden
      />
    );
  }
  return (
    <MinusCircle
      className={`${iconClass} text-[var(--text-muted)]`}
      aria-hidden
    />
  );
}

// ---------------------------------------------------------------------------
// Aggregation
// ---------------------------------------------------------------------------

function collectGlobalCheckIds(
  model: ReturnType<typeof selectDDGridV1DerivedModel>,
): Set<string> {
  const set = new Set<string>();
  for (const group of model.globalGroups) {
    for (const check of group.checks) {
      set.add(check.checkId);
    }
  }
  return set;
}

function collectDocTypeOnlyCheckIds(
  model: ReturnType<typeof selectDDGridV1DerivedModel>,
  globalCheckIds: Set<string>,
): Set<string> {
  const set = new Set<string>();
  for (const cls of model.docTypeClasses) {
    for (const t of cls.types) {
      for (const check of t.checks) {
        if (!globalCheckIds.has(check.checkId)) {
          set.add(check.checkId);
        }
      }
    }
  }
  return set;
}

function collectCheckNamesMap(
  model: ReturnType<typeof selectDDGridV1DerivedModel>,
): Map<string, string> {
  const map = new Map<string, string>();
  for (const group of model.globalGroups) {
    for (const check of group.checks) {
      if (!map.has(check.checkId)) {
        map.set(check.checkId, check.checkName || check.checkId);
      }
    }
  }
  for (const cls of model.docTypeClasses) {
    for (const t of cls.types) {
      for (const check of t.checks) {
        if (!map.has(check.checkId)) {
          map.set(check.checkId, check.checkName || check.checkId);
        }
      }
    }
  }
  return map;
}

function buildCheckGroupSummary(
  model: ReturnType<typeof selectDDGridV1DerivedModel>,
  checkIds: Set<string>,
  checkNames: Map<string, string>,
  locale: string,
): CheckGroupSummary {
  const aggregateMap = new Map<
    string,
    { passCount: number; failCount: number; unclearCount: number }
  >();

  for (const row of model.rows) {
    const segmentId = row.segmentId ?? "_default";
    const drawerBySegment = model.drawerContents[row.documentId]?.[segmentId] ?? {};

    for (const [checkId, drawer] of Object.entries(drawerBySegment)) {
      if (!checkIds.has(checkId)) continue;
      if (!drawer) continue;

      const status = drawer.review_status;
      let bucket: "pass" | "fail" | "unclear" | null = null;
      if (status === "ok" || status === "no_issue_detected") {
        bucket = "pass";
      } else if (status === "needs_review") {
        bucket = "fail";
      } else if (status === "unclear") {
        bucket = "unclear";
      }

      if (!bucket) continue;

      const existing = aggregateMap.get(checkId);
      if (existing) {
        if (bucket === "pass") existing.passCount++;
        else if (bucket === "fail") existing.failCount++;
        else existing.unclearCount++;
      } else {
        aggregateMap.set(checkId, {
          passCount: bucket === "pass" ? 1 : 0,
          failCount: bucket === "fail" ? 1 : 0,
          unclearCount: bucket === "unclear" ? 1 : 0,
        });
      }
    }
  }

  const aggregates: CheckAggregate[] = [];
  for (const checkId of checkIds) {
    const stats = aggregateMap.get(checkId);
    if (!stats) continue;
    aggregates.push({
      checkId,
      checkName: checkNames.get(checkId) ?? checkId,
      passCount: stats.passCount,
      failCount: stats.failCount,
      unclearCount: stats.unclearCount,
      worstStatus: computeWorstStatus(
        stats.passCount,
        stats.failCount,
        stats.unclearCount,
      ),
    });
  }

  const statusRank: Record<CheckWorstStatus, number> = {
    fail: 0,
    unclear: 1,
    pass: 2,
    unknown: 3,
  };
  aggregates.sort((a, b) => {
    const rankDiff = statusRank[a.worstStatus] - statusRank[b.worstStatus];
    if (rankDiff !== 0) return rankDiff;
    return a.checkName.localeCompare(b.checkName, locale);
  });

  return {
    totalChecks: aggregates.length,
    passedChecksCount: aggregates.filter((c) => c.worstStatus === "pass").length,
    failedChecksCount: aggregates.filter((c) => c.worstStatus === "fail").length,
    unclearChecksCount: aggregates.filter((c) => c.worstStatus === "unclear")
      .length,
    topChecks: aggregates.slice(0, MAX_CHECKS_IN_GROUP),
  };
}

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

const AnalysisResultsSkeleton: React.FC = () => (
  <div className="animate-pulse space-y-2">
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-3">
      <div className="h-3 w-24 rounded bg-[var(--bg-elevated-soft)]" />
      <div className="mt-2 h-8 w-20 rounded bg-[var(--bg-elevated-soft)]" />
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// Unclear findings row
// ---------------------------------------------------------------------------

interface UnclearFindingsRowProps {
  filename: string;
  unclearCount: number;
  onClick: () => void;
}

const UnclearFindingsRow: React.FC<UnclearFindingsRowProps> = ({
  filename,
  unclearCount,
  onClick,
}) => (
  <button
    type="button"
    onClick={onClick}
    className="group flex w-full items-center gap-1.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-base)] px-2 py-1.5 text-left transition-colors hover:bg-[var(--bg-elevated-soft)]"
    title={filename}
  >
    <span className="min-w-0 flex-1 truncate text-[11px] text-[var(--text-primary)]">
      {truncateFilename(filename)}
    </span>
    <span className="shrink-0 rounded-full bg-[var(--color-warning-bg)] px-1.5 py-0.5 text-[9px] font-semibold tabular-nums text-[var(--color-warning-text)]">
      {unclearCount}
    </span>
    <ChevronRight className="h-3 w-3 shrink-0 text-[var(--text-muted)] opacity-0 transition-opacity group-hover:opacity-100" />
  </button>
);

// ---------------------------------------------------------------------------
// Check group section
// ---------------------------------------------------------------------------

interface CheckGroupSectionProps {
  title: string;
  summary: CheckGroupSummary;
  onGroupClick: () => void;
}

const CheckGroupSection: React.FC<CheckGroupSectionProps> = ({
  title,
  summary,
  onGroupClick,
}) => {
  const { t } = useTranslation("projects");

  if (summary.totalChecks === 0) {
    return (
      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-2.5">
        <p className="text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">
          {title}
        </p>
        <p className="mt-1 text-[11px] text-[var(--text-muted)]">
          {t("overviewPanels.resultsWidget.checksNotExecuted")}
        </p>
      </div>
    );
  }

  const hiddenCount = summary.totalChecks - summary.topChecks.length;
  const typesCounterText = t("overviewPanels.resultsWidget.checkTypesCount", { count: summary.totalChecks });

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-2.5">
      <button
        type="button"
        onClick={onGroupClick}
        className="group flex w-full items-center justify-between gap-2 text-left transition-colors hover:bg-[var(--bg-elevated-soft)] rounded-md -mx-1 px-1 py-0.5"
      >
        <p className="min-w-0 flex-1 truncate text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">
          {title}
        </p>

        <ChevronRight
          className="h-3.5 w-3.5 shrink-0 text-[var(--text-muted)] transition-transform group-hover:translate-x-0.5 group-hover:text-[var(--text-primary)]"
          aria-hidden
        />
      </button>

      <div className="mt-1 flex items-center justify-between gap-2">
        <p className="min-w-0 truncate text-[11px] font-medium text-[var(--text-primary)]">
          {typesCounterText}
        </p>

        <div className="flex shrink-0 items-center gap-2 text-[10px] tabular-nums">
          {summary.passedChecksCount > 0 && (
            <span
              className="flex items-center gap-0.5 text-[var(--color-success-text)]"
              title={t("overviewPanels.resultsWidget.passedTooltip", { count: summary.passedChecksCount })}
            >
              <CheckCircle2 className="h-2.5 w-2.5" aria-hidden />
              {summary.passedChecksCount}
            </span>
          )}
          {summary.failedChecksCount > 0 && (
            <span
              className="flex items-center gap-0.5 text-[var(--color-error-text)]"
              title={t("overviewPanels.resultsWidget.failedTooltip", { count: summary.failedChecksCount })}
            >
              <XCircle className="h-2.5 w-2.5" aria-hidden />
              {summary.failedChecksCount}
            </span>
          )}
          {summary.unclearChecksCount > 0 && (
            <span
              className="flex items-center gap-0.5 text-[var(--color-warning-text)]"
              title={t("overviewPanels.resultsWidget.unclearTooltip", { count: summary.unclearChecksCount })}
            >
              <HelpCircle className="h-2.5 w-2.5" aria-hidden />
              {summary.unclearChecksCount}
            </span>
          )}
        </div>
      </div>

      <div className="mt-2 space-y-0.5">
        {summary.topChecks.map((check) => (
          <div
            key={check.checkId}
            className="flex items-center gap-1.5"
            title={check.checkName}
          >
            <StatusIcon status={check.worstStatus} />
            <span className="min-w-0 flex-1 truncate text-[11px] leading-4 text-[var(--text-primary)]">
              {truncateCheckName(check.checkName)}
            </span>
          </div>
        ))}
        {hiddenCount > 0 && (
          <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
            {t("overviewPanels.resultsWidget.moreCount", { count: hiddenCount })}
          </p>
        )}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Widget
// ---------------------------------------------------------------------------

interface AnalysisResultsWidgetProps {
  dealId: string;
  runId: string | null;
}

export const AnalysisResultsWidget: React.FC<
  AnalysisResultsWidgetProps
> = ({ dealId, runId }) => {
  const { t, i18n } = useTranslation("projects");
  const navigate = useNavigate();
  const location = useLocation();
  const { data: run, isLoading, isError } = useRun(runId, false);
  const { data: ddGridResponse } = useDealReviewDdGridV1(dealId, runId);

  const ddGridModel = React.useMemo(
    () => selectDDGridV1DerivedModel(ddGridResponse ?? null),
    [ddGridResponse],
  );

  const { globalSummary, docTypeSummary } = React.useMemo(() => {
    const checkNames = collectCheckNamesMap(ddGridModel);
    const globalCheckIds = collectGlobalCheckIds(ddGridModel);
    const docTypeOnlyCheckIds = collectDocTypeOnlyCheckIds(
      ddGridModel,
      globalCheckIds,
    );

    return {
      globalSummary: buildCheckGroupSummary(
        ddGridModel,
        globalCheckIds,
        checkNames,
        i18n.language,
      ),
      docTypeSummary: buildCheckGroupSummary(
        ddGridModel,
        docTypeOnlyCheckIds,
        checkNames,
        i18n.language,
      ),
    };
  }, [ddGridModel, i18n.language]);

  const unclearFindingsItems = React.useMemo<UnclearFindingsItem[]>(() => {
    if (!ddGridResponse) return [];

    const documentMap = new Map<
      string,
      { filename: string; unclearCount: number }
    >();

    for (const row of ddGridModel.rows) {
      const segmentId = row.segmentId ?? "_default";
      const drawerBySegment = ddGridModel.drawerContents[row.documentId]?.[segmentId] ?? {};

      for (const drawer of Object.values(drawerBySegment)) {
        if (!drawer) continue;
        if (drawer.review_status === "unclear") {
          const existing = documentMap.get(row.documentId);
          if (existing) {
            existing.unclearCount += 1;
          } else {
            documentMap.set(row.documentId, {
              filename: row.filename || "[no name]",
              unclearCount: 1,
            });
          }
        }
      }
    }

    return [...documentMap.entries()]
      .map(([documentId, meta]) => ({
        documentId,
        filename: meta.filename,
        unclearCount: meta.unclearCount,
      }))
      .sort((a, b) => b.unclearCount - a.unclearCount);
  }, [ddGridModel, ddGridResponse]);

  const totalUnclearFindingsCount = React.useMemo(
    () =>
      unclearFindingsItems.reduce((sum, item) => sum + item.unclearCount, 0),
    [unclearFindingsItems],
  );

  const affectedDocumentsCount = unclearFindingsItems.length;

  const navigateToDDGrid = React.useCallback(() => {
    const params = new URLSearchParams(location.search);
    params.set("tab", "dd_grid");
    navigate(
      {
        pathname: location.pathname,
        search: params.toString(),
      },
      { replace: false },
    );
  }, [location.pathname, location.search, navigate]);

  const handleOpenUnclearInDDGrid = React.useCallback(() => {
    const store = useDDGridV1UIStore.getState();
    store.setFormat("list");
    store.setShowPassInList(false);
    store.setChecksScope("all");
    navigateToDDGrid();
  }, [navigateToDDGrid]);

  const handleOpenAllResultsInDDGrid = React.useCallback(() => {
    const store = useDDGridV1UIStore.getState();
    store.setFormat("list");
    store.setShowPassInList(true);
    store.setChecksScope("all");
    navigateToDDGrid();
  }, [navigateToDDGrid]);

  const handleOpenGlobalChecksInDDGrid = React.useCallback(() => {
    const store = useDDGridV1UIStore.getState();
    store.setFormat("matrix");
    store.setChecksScope("global_only");
    navigateToDDGrid();
  }, [navigateToDDGrid]);

  const handleOpenDocTypeChecksInDDGrid = React.useCallback(() => {
    const store = useDDGridV1UIStore.getState();
    store.setFormat("matrix");
    store.setChecksScope("doc_type_only");
    navigateToDDGrid();
  }, [navigateToDDGrid]);

  if (!runId) {
    return (
      <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-base)] px-3 py-4 text-center">
        <p className="text-[11px] text-[var(--text-muted)]">
          {t("overviewPanels.resultsWidget.notLaunched")}
        </p>
        <p className="mt-0.5 text-[10px] text-[var(--text-muted)]">
          {t("overviewPanels.resultsWidget.notLaunchedSub")}
        </p>
      </div>
    );
  }

  if (isLoading) return <AnalysisResultsSkeleton />;

  if (isError || !run) {
    return (
      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-3">
        <p className="text-[11px] text-[var(--text-muted)]">
          {t("overviewPanels.resultsWidget.loadError")}
        </p>
      </div>
    );
  }

  const totalChecks = run.total_checks ?? 0;
  const completedChecks = run.completed_checks ?? 0;
  const hasErrors = run.has_errors ?? false;
  const failedDocs = run.failed_docs_count ?? 0;
  const quarantineDocs = run.quarantine_docs_count ?? 0;

  const isRunning = run.status === "pending" || run.status === "running";
  const isTerminal =
    run.status === "completed" || run.status === "completed_with_errors";

  const progressPercent =
    totalChecks > 0 ? Math.round((completedChecks / totalChecks) * 100) : 0;

  const canOpenDDGrid = isTerminal;

  const visibleUnclearFindings = unclearFindingsItems.slice(0, MAX_ITEMS_IN_LIST);
  const hiddenUnclearFindingsCount =
    unclearFindingsItems.length - visibleUnclearFindings.length;

  const counterText = t("overviewPanels.resultsWidget.unclearSummary", {
    checksCount: totalUnclearFindingsCount,
    docsCount: affectedDocumentsCount
  });

  return (
    <div className="space-y-2">
      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <p className="text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">
              {t("overviewPanels.resultsWidget.checksCompleted")}
            </p>
            <p className="mt-1 text-xl font-semibold tabular-nums text-[var(--text-primary)]">
              {completedChecks}
              <span className="text-sm font-normal text-[var(--text-muted)]">
                {" / "}
                {totalChecks}
              </span>
            </p>
          </div>

          {isRunning && (
            <span className="shrink-0 rounded-full bg-[var(--accent-muted)] px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.08em] text-[var(--accent-primary)]">
              {t("overviewPanels.resultsWidget.running")}
            </span>
          )}
        </div>

        {totalChecks > 0 && (
          <div className="mt-3">
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--bg-elevated-soft)]">
              <div
                className="h-full rounded-full bg-[var(--accent-primary)] transition-all duration-500"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {(hasErrors || failedDocs > 0 || quarantineDocs > 0) && (
        <div className="rounded-xl border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-3 py-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--color-warning-text)]">
            {t("overviewPanels.resultsWidget.problemsDetected")}
          </p>
          <div className="mt-1.5 space-y-1">
            {failedDocs > 0 && (
              <p className="text-[11px] text-[var(--color-warning-text)]">
                {t("overviewPanels.resultsWidget.processingErrors", { count: failedDocs })}
              </p>
            )}
            {quarantineDocs > 0 && (
              <p className="text-[11px] text-[var(--color-warning-text)]">
                {t("overviewPanels.resultsWidget.inQuarantine", { count: quarantineDocs })}
              </p>
            )}
          </div>
        </div>
      )}

      {isTerminal && (
        <CheckGroupSection
          title={t("overviewPanels.resultsWidget.globalChecks")}
          summary={globalSummary}
          onGroupClick={handleOpenGlobalChecksInDDGrid}
        />
      )}

      {isTerminal && (
        <CheckGroupSection
          title={t("overviewPanels.resultsWidget.docTypeChecks")}
          summary={docTypeSummary}
          onGroupClick={handleOpenDocTypeChecksInDDGrid}
        />
      )}

      <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-2.5">
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">
          {t("overviewPanels.resultsWidget.unclearTitle")}
        </p>

        {unclearFindingsItems.length === 0 ? (
          <p className="text-[11px] leading-5 text-[var(--text-secondary)]">
            {t("overviewPanels.resultsWidget.unclearEmpty")}
          </p>
        ) : (
          <div className="space-y-1.5">
            <p className="text-[11px] leading-5 text-[var(--text-secondary)]">
              {counterText}
            </p>
            <div className="space-y-1">
              {visibleUnclearFindings.map((item) => (
                <UnclearFindingsRow
                  key={item.documentId}
                  filename={item.filename}
                  unclearCount={item.unclearCount}
                  onClick={handleOpenUnclearInDDGrid}
                />
              ))}
            </div>
            {hiddenUnclearFindingsCount > 0 && (
              <p className="text-[10px] text-[var(--text-muted)]">
                {t("overviewPanels.resultsWidget.moreCount", { count: hiddenUnclearFindingsCount })}
              </p>
            )}
          </div>
        )}
      </div>

      {canOpenDDGrid && (
        <button
          type="button"
          onClick={handleOpenAllResultsInDDGrid}
          className="flex w-full items-center justify-between gap-2 rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-2 text-left transition-colors hover:bg-[var(--bg-elevated-soft)]"
        >
          <span className="text-xs font-medium text-[var(--text-primary)]">
            {t("overviewPanels.resultsWidget.goToAllResults")}
          </span>
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-[var(--text-muted)]" />
        </button>
      )}
    </div>
  );
};

export default AnalysisResultsWidget;



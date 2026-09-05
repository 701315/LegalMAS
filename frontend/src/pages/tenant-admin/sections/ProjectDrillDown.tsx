// =============================================================
// src/pages/tenant-admin/sections/ProjectDrillDown.tsx
//
// Orchestrator for the per-project drill-down view. Manages:
// - Sub-tabs (overview | members | logs)
// - Project insights fetching
// - Project logs fetching (enabled only when subTab === "logs")
// - Shared correlation state (for navigation from Overview to Logs)
// - Shared logs mode + since (inherited between sub-tabs)
//
// Sub-sections:
// - ProjectOverviewSection — document metrics, runs, errors
// - ProjectMembersSection — project participants
// - ProjectLogsSection — Loki logs with correlation
//
// Design contract:
// - Sub-header with "Back to list" button + project name + sub-tabs + "Open full project"
// - Loading/error states for insights
// - On dealId change, logs correlation is intentionally NOT reset
//   (the user may have just navigated to another project and wants the same context)
//
// State ownership:
// - subTab, logsMode, projectLogsSince, correlation — here (needed
//   for tools shared between sub-tabs)
// - errorFilter, expandedErrorKey — inside ProjectOverviewSection
// - selectedLogIdx, copied — inside ProjectLogsSection
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, ExternalLink, Loader2 } from "lucide-react";
import type {
  LogsMode,
  ProjectErrorItem,
} from "../../../api/tenantAdmin";
import {
  useProjectInsights,
  useTenantLogs,
} from "../../../api/tenantAdmin";
import Button from "../../../components/ui/Button";
import type { ProjectDrillTab } from "../types";
import {
  SECTION_HEADER_WRAP,
  SECTION_HEADER_INNER,
  SECTION_DIVIDER,
} from "../constants";
import { formatDate, formatDateTime } from "../utils";
import TabButton from "../components/TabButton";
import ProjectOverviewSection from "./project-drilldown/ProjectOverviewSection";
import ProjectMembersSection from "./project-drilldown/ProjectMembersSection";
import ProjectLogsSection from "./project-drilldown/ProjectLogsSection";

export interface ProjectDrillDownProps {
  /** Project ID for drill down */
  dealId: string;
  /** Callback on "Back to list" click — parent resets selectedProjectId */
  onBack: () => void;
  /** Callback on "Open full project" click — navigates to /projects/:id */
  onOpenProject: (dealId: string) => void;
}

const ProjectDrillDown: React.FC<ProjectDrillDownProps> = ({
  dealId,
  onBack,
  onOpenProject,
}) => {
  const { t, i18n } = useTranslation("tenantAdmin");
  const insightsQ = useProjectInsights(dealId);
  const [subTab, setSubTab] = React.useState<ProjectDrillTab>("overview");

  // Shared logs state (needed for Overview → Logs transitions)
  const [logsMode, setLogsMode] = React.useState<LogsMode>("operational");
  const [projectLogsSince, setProjectLogsSince] =
    React.useState<number>(1440);
  const [correlationRunId, setCorrelationRunId] = React.useState<string | null>(
    null,
  );
  const [correlationDocId, setCorrelationDocId] = React.useState<string | null>(
    null,
  );
  const [correlationTaskId, setCorrelationTaskId] = React.useState<
    string | null
  >(null);

  const projectLogsQ = useTenantLogs(
    {
      deal_id: dealId,
      run_id: correlationRunId ?? undefined,
      document_id: correlationDocId ?? undefined,
      task_id: correlationTaskId ?? undefined,
      mode: logsMode,
      limit: 100,
      since_minutes: projectLogsSince,
      group_similar: true,
    },
    { enabled: subTab === "logs" },
  );

  const insights = insightsQ.data;
  const logs = projectLogsQ.data?.entries ?? [];
  const members = insights?.members ?? [];
  const membersCount = insights?.members_count ?? members.length;
  const dealName = insights?.deal_name ?? t("drillDown.projectFallback");

  const handleCorrelationChange = React.useCallback(
    (
      runId: string | null,
      docId: string | null,
      taskId: string | null,
    ) => {
      setCorrelationRunId(runId);
      setCorrelationDocId(docId);
      setCorrelationTaskId(taskId);
    },
    [],
  );

  // Handler for the "Logs" button in a run row (Overview section)
  const handleOpenLogsForRun = React.useCallback((runId: string) => {
    setSubTab("logs");
    setCorrelationRunId(runId);
    setCorrelationDocId(null);
    setCorrelationTaskId(null);
    setLogsMode("debug");
    setProjectLogsSince(0);
  }, []);

  // Handler for the "Logs" button in an error row (Overview section)
  const handleOpenLogsForError = React.useCallback(
    (item: ProjectErrorItem) => {
      setSubTab("logs");
      setLogsMode("debug");
      setProjectLogsSince(0);
      setCorrelationRunId(item.run_id ?? null);
      setCorrelationDocId(item.document_id ?? null);
      setCorrelationTaskId(null);
    },
    [],
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Sub-header */}
      <div className={SECTION_HEADER_WRAP}>
        <div
          className={`flex flex-wrap items-center justify-between gap-3 ${SECTION_HEADER_INNER}`}
        >
          <div className="flex min-w-0 items-center gap-3">
            <Button
              size="sm"
              variant="ghost"
              onClick={onBack}
              leftIcon={<ArrowLeft size={14} />}
            >
              {t("drillDown.backToList")}
            </Button>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-[var(--text-primary)]">
                {dealName}
              </p>
              {insights?.created_at && (
                <p className="text-[10px] text-[var(--text-muted)]">
                  {t("drillDown.created", {
                    date: formatDate(insights.created_at, i18n.language) ?? "—",
                  })}
                  {insights.last_activity_at
                    ? t("drillDown.lastActivity", {
                        date: formatDateTime(insights.last_activity_at, i18n.language),
                      })
                    : ""}
                </p>
              )}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <TabButton
              active={subTab === "overview"}
              onClick={() => setSubTab("overview")}
            >
              {t("drillDown.tabs.overview")}
            </TabButton>
            <TabButton
              active={subTab === "members"}
              onClick={() => setSubTab("members")}
              badge={membersCount}
            >
              {t("drillDown.tabs.members")}
            </TabButton>
            <TabButton
              active={subTab === "logs"}
              onClick={() => setSubTab("logs")}
              badge={logs.length}
            >
              {t("drillDown.tabs.logs")}
            </TabButton>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => onOpenProject(dealId)}
              leftIcon={<ExternalLink size={14} />}
            >
              {t("drillDown.openFullProject")}
            </Button>
          </div>
        </div>
        <div className={SECTION_DIVIDER} />
      </div>

      {/* Body */}
      <div
        className={`min-h-0 flex-1 ${
          subTab === "logs" ? "overflow-hidden" : "overflow-auto"
        }`}
      >    
        {insightsQ.isLoading && !insights ? (
          <div className="flex h-full items-center justify-center text-[var(--text-muted)]">
            <Loader2 size={20} className="animate-spin" />
            <span className="ml-3 text-sm">{t("drillDown.loading")}</span>
          </div>
        ) : insightsQ.error && !insights ? (
          <div className="flex h-full items-center justify-center p-5 text-center">
            <div>
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {t("drillDown.loadError")}
              </p>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => insightsQ.refetch()}
                className="mt-3"
              >
                {t("actions.retry", { ns: "common" })}
              </Button>
            </div>
          </div>
        ) : (
          <>
            {subTab === "overview" && (
              <ProjectOverviewSection
                insights={insights}
                onOpenLogsForRun={handleOpenLogsForRun}
                onOpenLogsForError={handleOpenLogsForError}
              />
            )}

            {subTab === "members" && (
              <ProjectMembersSection dealId={dealId} />
            )}

            {subTab === "logs" && (
              <ProjectLogsSection
                logsQ={projectLogsQ}
                logsMode={logsMode}
                onLogsModeChange={setLogsMode}
                projectLogsSince={projectLogsSince}
                onProjectLogsSinceChange={setProjectLogsSince}
                correlationRunId={correlationRunId}
                correlationDocId={correlationDocId}
                correlationTaskId={correlationTaskId}
                onCorrelationChange={handleCorrelationChange}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default ProjectDrillDown;



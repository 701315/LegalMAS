// =============================================================
// src/pages/tenant-admin/sections/ProjectDrillDown.tsx
//
// Orchestrator для drill-down view конкретного проекта. Управляет:
// - Sub-tabs (overview | members | logs)
// - Загрузка project insights
// - Загрузка project logs (enabled только когда subTab === "logs")
// - Shared correlation state (для перехода из Overview в Logs)
// - Shared logs mode + since (для inheritance между sub-tabs)
//
// Sub-sections:
// - ProjectOverviewSection — метрики документов, runs, errors
// - ProjectMembersSection — участники проекта
// - ProjectLogsSection — логи из Loki с correlation
//
// Design contract:
// - Sub-header с "К списку" back button + название + sub-tabs + "Открыть проект"
// - Loading/error states для insights
// - При смене dealId — logs correlation НЕ сбрасывается (осознанно —
//   пользователь мог только что перейти в другой проект и хочет тот же контекст)
//
// State ownership:
// - subTab, logsMode, projectLogsSince, correlation — здесь (нужно
//   для инструментов shared между sub-tabs)
// - errorFilter, expandedErrorKey — внутри ProjectOverviewSection
// - selectedLogIdx, copied — внутри ProjectLogsSection
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
  /** ID проекта для drill down */
  dealId: string;
  /** Callback при клике "К списку" — parent сбрасывает selectedProjectId */
  onBack: () => void;
  /** Callback при клике "Открыть проект целиком" — переход на /projects/:id */
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

  // Shared logs state (нужен между Overview → Logs переходами)
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

  // Handler для "Логи" button в run row (Overview section)
  const handleOpenLogsForRun = React.useCallback((runId: string) => {
    setSubTab("logs");
    setCorrelationRunId(runId);
    setCorrelationDocId(null);
    setCorrelationTaskId(null);
    setLogsMode("debug");
    setProjectLogsSince(0);
  }, []);

  // Handler для "Логи" button в error row (Overview section)
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



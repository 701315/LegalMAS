// frontend/src/pages/TenantAdminPage.tsx
//
// Main admin panel — orchestrator для tenant_admin dashboard.
//
// Structure:
// - Layout: 2-column grid (image left + content right)
// - Image: fixed height (100vh), не скроллится
// - Content: scroll container — только правая колонка скроллится
// - Header: title + ExternalToolsBar + Refresh button
// - Problem projects banner (only when not in drill-down)
// - Section card with tab switcher + conditional tab content

import React from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, Loader2, RefreshCw, XCircle } from "lucide-react";

import {
  usePlatformMetrics,
  useTenantDashboard,
  useTenantLogs,
  type LogsMode,
} from "../api/tenantAdmin";
import Button from "../components/ui/Button";
import { ExternalToolsBar } from "../components/admin/ExternalToolsBar";
import { useAuth } from "../hooks/useAuth";

// Types
import type { AdminTab } from "./tenant-admin/types";

// Constants
import {
  SECTION_CARD,
  SECTION_HEADER_WRAP,
  SECTION_HEADER_INNER,
  SECTION_DIVIDER,
  FOCUS_RING,
} from "./tenant-admin/constants";

// UI components
import TabButton from "./tenant-admin/components/TabButton";

// Tabs
import AlertsTab from "./tenant-admin/tabs/AlertsTab";
import UsersTab from "./tenant-admin/tabs/UsersTab";
import ProjectsTab from "./tenant-admin/tabs/ProjectsTab";
import MonitoringTab from "./tenant-admin/tabs/MonitoringTab";
import LogsTab, {
  type AppliedLogsFilters,
} from "./tenant-admin/tabs/LogsTab";

// Project drill-down orchestrator
import ProjectDrillDown from "./tenant-admin/sections/ProjectDrillDown";

// ─── Main Page ───────────────────────────────────────────────────────────

const TenantAdminPage: React.FC = () => {
  const { t } = useTranslation("tenantAdmin");
  const navigate = useNavigate();
  const { globalRole } = useAuth();

  // ─── UI state ──────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = React.useState<AdminTab>("projects");
  const [selectedProjectId, setSelectedProjectId] = React.useState<
    string | null
  >(null);
  const [expandedUserIds, setExpandedUserIds] = React.useState<Set<string>>(
    new Set(),
  );

  // ─── Server state ──────────────────────────────────────────────────
  const dashQ = useTenantDashboard();
  const metricsQ = usePlatformMetrics(undefined, {
    enabled: activeTab === "monitoring",
  });

  // ─── Logs state (shared with LogsTab) ──────────────────────────────
  const [logsMode, setLogsMode] = React.useState<LogsMode>("operational");
  const [correlationRunId, setCorrelationRunId] = React.useState<string | null>(
    null,
  );
  const [correlationDocId, setCorrelationDocId] = React.useState<string | null>(
    null,
  );
  const [correlationTaskId, setCorrelationTaskId] = React.useState<
    string | null
  >(null);
  const [applied, setApplied] = React.useState<AppliedLogsFilters>({
    deal_id: "",
    level: "",
    stage: "",
    queue: "",
    since_minutes: 60,
    limit: 50,
  });

  const logsQ = useTenantLogs(
    {
      deal_id: applied.deal_id || undefined,
      run_id: correlationRunId ?? undefined,
      document_id: correlationDocId ?? undefined,
      task_id: correlationTaskId ?? undefined,
      level: applied.level || undefined,
      stage: applied.stage || undefined,
      queue: applied.queue || undefined,
      mode: logsMode,
      since_minutes: applied.since_minutes,
      limit: applied.limit,
      group_similar: true,
    },
    { enabled: activeTab === "logs" },
  );

  // ─── Derived data ──────────────────────────────────────────────────
  const projects = dashQ.data?.projects ?? [];
  const users = dashQ.data?.users ?? [];

  const problemProjects = projects.filter(
    (p) =>
      p.failed_documents > 0 ||
      p.quarantine_documents > 0 ||
      p.last_run?.status === "failed",
  );

  // ─── Handlers ──────────────────────────────────────────────────────
  const handleRefresh = () => {
    dashQ.refetch();
    if (activeTab === "monitoring") metricsQ.refetch();
    if (activeTab === "logs") logsQ.refetch();
  };

  const isRefreshing =
    dashQ.isFetching ||
    (activeTab === "monitoring" && metricsQ.isFetching) ||
    (activeTab === "logs" && logsQ.isFetching);

  const openProjectDrillDown = (dealId: string) => {
    setActiveTab("projects");
    setSelectedProjectId(dealId);
  };

  const toggleUserExpanded = (userId: string) => {
    setExpandedUserIds((prev) => {
      const next = new Set(prev);
      if (next.has(userId)) next.delete(userId);
      else next.add(userId);
      return next;
    });
  };

  const handleCorrelationChange = (
    runId: string | null,
    docId: string | null,
    taskId: string | null,
  ) => {
    setCorrelationRunId(runId);
    setCorrelationDocId(docId);
    setCorrelationTaskId(taskId);
  };

  // ─── Loading / error states ────────────────────────────────────────
  if (dashQ.isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex items-center gap-3 text-[var(--text-muted)]">
          <Loader2 size={20} className="animate-spin" />
          <span className="text-sm">{t("loading")}</span>
        </div>
      </div>
    );
  }

  if (dashQ.error) {
    return (
      <div className="flex h-full items-center justify-center px-4">
        <div
          className={`${SECTION_CARD} w-full max-w-sm px-6 py-6 text-center`}
        >
          <XCircle
            size={24}
            className="mx-auto mb-3 text-[var(--color-error-text)]"
          />
          <p className="text-sm font-semibold text-[var(--color-error-text)]">
            {t("error.loadFailed")}
          </p>
          <p className="mt-1 text-[10px] text-[var(--text-muted)]">
            {t("error.checkPermissions")}
          </p>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => dashQ.refetch()}
            className="mt-4"
          >
            {t("error.retry")}
          </Button>
        </div>
      </div>
    );
  }

  if (!dashQ.data) return null;

  // ─── Main render ───────────────────────────────────────────────────
  return (
    <div className="grid h-screen grid-cols-1 xl:grid-cols-[minmax(0,1fr)_minmax(0,3fr)]">
      
      {/* ── LEFT COLUMN — Decorative Image (fixed height, no scroll) ──── */}
      <div className="hidden xl:block">
        <div className="relative h-screen w-full overflow-hidden">
          <img
            src="/adminpicture.png"
            alt=""
            aria-hidden="true"
            className="h-full w-full object-cover"
          />
          {/* subtle gradient overlay (pointer-events-none чтобы не блокировать клики) */}
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-[var(--bg-base)]/10 to-transparent" />
        </div>
      </div>

      {/* ── RIGHT COLUMN — Scrollable Content ─────────────────────────── */}
      <div className="h-screen overflow-y-auto overscroll-contain">
        <div className="flex min-h-full flex-col gap-4 p-4 md:p-5">
          {/* Header */}
          <header className="shrink-0 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0">
                <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
                  {t("header.title")}
                </h1>
                <p className="mt-2 text-sm text-[var(--text-secondary)]">
                  {t("header.subtitle")}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <ExternalToolsBar />
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={handleRefresh}
                  isLoading={isRefreshing}
                  leftIcon={<RefreshCw size={14} />}
                >
                  {t("header.refresh")}
                </Button>
              </div>
            </div>
          </header>

          {/* Problem projects banner (only when not in drill-down) */}
          {problemProjects.length > 0 && !selectedProjectId && (
            <div className="shrink-0 rounded-2xl border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] px-5 py-4 shadow-sm">
              <div className="flex items-start gap-3">
                <AlertTriangle
                  size={16}
                  className="mt-0.5 shrink-0 text-[var(--color-warning-text)]"
                />
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-[var(--color-warning-text)]">
                    {t("problems.banner", { count: problemProjects.length })}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {problemProjects.map((p) => (
                      <button
                        key={p.deal_id}
                        type="button"
                        onClick={() => openProjectDrillDown(p.deal_id)}
                        className={`rounded-lg border border-[var(--color-warning-border)] bg-[var(--bg-card)] px-2.5 py-1 text-[10px] font-medium text-[var(--color-warning-text)] transition hover:bg-[var(--color-warning-bg)] ${FOCUS_RING}`}
                      >
                        {p.deal_name}
                        {p.failed_documents > 0 && (
                          <span className="ml-1.5 text-[var(--color-error-text)]">
                            {t("problems.errorsCount", { count: p.failed_documents })}
                          </span>
                        )}
                        {p.quarantine_documents > 0 && (
                          <span className="ml-1.5 text-[var(--color-warning-text)]">
                            {t("problems.quarantineCount", { count: p.quarantine_documents })}
                          </span>
                        )}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Section card: tabs + content */}
          <section
            className={`${SECTION_CARD} flex min-h-0 flex-1 flex-col overflow-hidden`}
          >
            {/* Tab switcher (скрывается при drill-down) */}
            {!selectedProjectId && (
              <div className={`${SECTION_HEADER_WRAP} shrink-0`}>
                <div
                  className={`flex flex-wrap gap-1.5 ${SECTION_HEADER_INNER}`}
                >
                  <TabButton
                    active={activeTab === "projects"}
                    onClick={() => setActiveTab("projects")}
                    badge={projects.length}
                  >
                    {t("tabs.projects")}
                  </TabButton>
                  <TabButton
                    active={activeTab === "users"}
                    onClick={() => setActiveTab("users")}
                    badge={users.length}
                  >
                    {t("tabs.users")}
                  </TabButton>
                  <TabButton
                    active={activeTab === "monitoring"}
                    onClick={() => setActiveTab("monitoring")}
                  >
                    {t("tabs.monitoring")}
                  </TabButton>
                  <TabButton
                    active={activeTab === "logs"}
                    onClick={() => setActiveTab("logs")}
                  >
                    {t("tabs.logs")}
                  </TabButton>
                  <TabButton
                    active={activeTab === "alerts"}
                    onClick={() => setActiveTab("alerts")}
                  >
                    {t("tabs.alerts")}
                  </TabButton>
                </div>
                <div className={SECTION_DIVIDER} />
              </div>
            )}

            {/* Projects: list или drill-down */}
            {activeTab === "projects" && (
              <>
                {selectedProjectId ? (
                  <ProjectDrillDown
                    dealId={selectedProjectId}
                    onBack={() => setSelectedProjectId(null)}
                    onOpenProject={(id) => navigate(`/projects/${id}`)}
                  />
                ) : (
                  <ProjectsTab
                    projects={projects}
                    onOpenProject={openProjectDrillDown}
                  />
                )}
              </>
            )}

            {/* Users */}
            {activeTab === "users" && (
              <UsersTab
                users={users}
                expandedUserIds={expandedUserIds}
                onToggleUser={toggleUserExpanded}
                onOpenProject={openProjectDrillDown}
              />
            )}

            {/* Monitoring */}
            {activeTab === "monitoring" && (
              <MonitoringTab metricsQ={metricsQ} globalRole={globalRole} />
            )}

            {/* Logs */}
            {activeTab === "logs" && (
              <LogsTab
                logsQ={logsQ}
                logsMode={logsMode}
                onLogsModeChange={setLogsMode}
                appliedFilters={applied}
                onApplyFilters={setApplied}
                projects={projects}
                correlationRunId={correlationRunId}
                correlationDocId={correlationDocId}
                correlationTaskId={correlationTaskId}
                onCorrelationChange={handleCorrelationChange}
              />
            )}

            {/* Alerts */}
            {activeTab === "alerts" && <AlertsTab />}
          </section>
        </div>
      </div>
    </div>
  );
};

export default TenantAdminPage;



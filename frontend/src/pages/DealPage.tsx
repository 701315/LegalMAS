// =============================================================
// src/pages/DealPage.tsx
// Страница сделки / проекта.
// Внутри страницы зафиксированы:
// 1) верхний хедер проекта,
// 2) левая панель вкладок проекта.
// Прокрутка происходит только в правой контентной области.
// =============================================================

import React from "react";
import { useLocation, useNavigate } from "react-router-dom";

import type { Deal, OpenViewerAtPayload } from "../types";

import OverviewTab from "./tabs/OverviewTab";
import GridTab from "./tabs/GridTab";
import DocumentsTab from "./tabs/DocumentsTab";
import { RequestsTab } from "./tabs/RequestsTab";
import { ReportTab } from "./tabs/ReportTab";
import { AuditTab } from "./tabs/AuditTab";
import SettingsTab from "./tabs/SettingsTab";

import { useDealPermissions } from "../hooks/usePermissions";
import Button from "../components/ui/Button";

interface DealPageProps {
  deal: Deal;
}

type TabKey =
  | "overview"
  | "documents"
  | "dd_grid"
  | "requests"
  | "report"
  | "audit"
  | "settings";

const TAB_KEYS: TabKey[] = [
  "overview",
  "documents",
  "dd_grid",
  "requests",
  "report",
  "audit",
  "settings",
];

const TAB_LABELS: Record<TabKey, string> = {
  overview: "Обзор",
  documents: "Документы",
  dd_grid: "DD Grid",
  requests: "Запросы",
  report: "Отчёт",
  audit: "Аудит",
  settings: "Настройки",
};

const sidebarItemBaseClassName =
  "w-full rounded-xl px-3 py-2 text-left font-medium transition-colors " +
  "text-[length:var(--font-size-ui-sm)] leading-[var(--line-height-ui-sm)]";

const mobileTabBaseClassName =
  "shrink-0 border-b-2 px-3 py-2 font-medium transition-colors " +
  "text-[length:var(--font-size-ui-xs)] leading-[var(--line-height-ui-xs)]";

function isTabKey(value: string | null): value is TabKey {
  return !!value && TAB_KEYS.includes(value as TabKey);
}

function getTabId(tabKey: TabKey) {
  return `deal-tab-${tabKey}`;
}

function getTabPanelId(tabKey: TabKey) {
  return `deal-tabpanel-${tabKey}`;
}

const DealPage: React.FC<DealPageProps> = ({ deal }) => {
  const navigate = useNavigate();
  const location = useLocation();

  const latestRunId = deal.last_run_id ?? null;
  const hasLatestRun = !!latestRunId;

  const { canManageRequests, canUploadDocuments } =
    useDealPermissions(deal.id);

  const canManageProject = canUploadDocuments || canManageRequests;

  const searchParams = React.useMemo(
    () => new URLSearchParams(location.search),
    [location.search],
  );

  const tabFromUrl = searchParams.get("tab");
  const initialTab: TabKey = isTabKey(tabFromUrl) ? tabFromUrl : "overview";

  const [activeTab, setActiveTab] = React.useState<TabKey>(initialTab);
  const [viewerLocation, setViewerLocation] =
    React.useState<OpenViewerAtPayload | null>(null);

  React.useEffect(() => {
    setActiveTab(isTabKey(tabFromUrl) ? tabFromUrl : "overview");
  }, [tabFromUrl]);

  const handleSetTab = React.useCallback(
    (tab: TabKey) => {
      setActiveTab(tab);

      const params = new URLSearchParams(location.search);
      if (tab === "overview") {
        params.delete("tab");
      } else {
        params.set("tab", tab);
      }

      navigate(
        {
          pathname: location.pathname,
          search: params.toString(),
        },
        { replace: true },
      );
    },
    [location.pathname, location.search, navigate],
  );

  const handleOpenViewerAt = React.useCallback(
    (payload: OpenViewerAtPayload) => {
      setViewerLocation(payload);
      handleSetTab("documents");
    },
    [handleSetTab],
  );

  const handleViewerLocationConsumed = React.useCallback(() => {
    setViewerLocation(null);
  }, []);

  const handleBackToProjects = React.useCallback(() => {
    navigate("/dashboard");
  }, [navigate]);

  const handleMobileTabKeyDown = React.useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      const currentIndex = TAB_KEYS.indexOf(activeTab);
      if (currentIndex < 0) return;

      let nextIndex = currentIndex;

      if (event.key === "ArrowRight") {
        event.preventDefault();
        nextIndex = (currentIndex + 1) % TAB_KEYS.length;
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        nextIndex = (currentIndex - 1 + TAB_KEYS.length) % TAB_KEYS.length;
      } else if (event.key === "Home") {
        event.preventDefault();
        nextIndex = 0;
      } else if (event.key === "End") {
        event.preventDefault();
        nextIndex = TAB_KEYS.length - 1;
      } else {
        return;
      }

      const nextTab = TAB_KEYS[nextIndex];
      if (nextTab === "settings" && !canManageProject) {
        return;
      }

      handleSetTab(nextTab);

      window.requestAnimationFrame(() => {
        const nextElement = document.getElementById(getTabId(nextTab));
        nextElement?.focus();
      });
    },
    [activeTab, canManageProject, handleSetTab],
  );

  const renderRunRequiredState = (title: string, description: string) => (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5">
      <p className="text-sm font-medium text-[var(--text-primary)]">{title}</p>
      <p className="mt-1.5 text-sm text-[var(--text-secondary)]">
        {description}
      </p>
    </div>
  );

  const activeTabLabel = TAB_LABELS[activeTab];

  const renderActiveTabPanel = () => {
    if (activeTab === "overview") {
      return <OverviewTab deal={deal} latestRunId={latestRunId} />;
    }

    if (activeTab === "documents") {
      return hasLatestRun ? (
        <DocumentsTab
          deal={deal}
          runId={latestRunId}
          openViewerAt={viewerLocation}
          onViewerLocationConsumed={handleViewerLocationConsumed}
        />
      ) : (
        renderRunRequiredState(
          "Список документов пока недоступен",
          "Карточки документов в режиме review появятся после первого анализа проекта.",
        )
      );
    }

    if (activeTab === "dd_grid") {
      return hasLatestRun ? (
        <GridTab dealId={deal.id} runId={latestRunId} />
      ) : (
        renderRunRequiredState(
          "DD Grid пока недоступен",
          "Для этого проекта ещё не запускался анализ. Запустите первый анализ, чтобы открыть матрицу проверок.",
        )
      );
    }

    if (activeTab === "requests") {
      return hasLatestRun ? (
        <RequestsTab
          dealId={deal.id}
          runId={latestRunId}
          onOpenViewerAt={handleOpenViewerAt}
        />
      ) : (
        renderRunRequiredState(
          "Запросы пока недоступны",
          "Сначала нужен хотя бы один анализ, чтобы система сформировала follow-up запросы по найденным рискам.",
        )
      );
    }

    if (activeTab === "report") {
      return <ReportTab dealId={deal.id} />;
    }

    if (activeTab === "audit") {
      return <AuditTab dealId={deal.id} />;
    }

    return (
      <SettingsTab
        dealId={deal.id}
        canManageProject={canManageProject}
      />
    );
  };

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden rounded-[20px] bg-[var(--bg-card)]">
      <header className="hidden shrink-0 border-b border-[var(--border)] bg-[var(--bg-card)] md:block">
        <div className="px-6 py-5">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h1 className="truncate text-lg font-semibold tracking-tight text-[var(--text-primary)]">
                {deal.name}
              </h1>
            </div>

            <div className="shrink-0">
              <Button
                variant="secondary"
                size="sm"
                onClick={handleBackToProjects}
              >
                Вернуться к списку проектов
              </Button>
            </div>
          </div>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 overflow-hidden">
        <aside className="hidden min-h-0 shrink-0 md:flex md:w-60 md:flex-col md:border-r md:border-[var(--border)] md:bg-[var(--bg-card)]">
          <nav
            className="flex h-full flex-col overflow-y-auto px-3 py-4"
            aria-label="Навигация по проекту"
          >
            <div className="space-y-1">
              <SidebarItem
                label={TAB_LABELS.overview}
                tabKey="overview"
                activeTab={activeTab}
                onSelect={handleSetTab}
              />
              <SidebarItem
                label={TAB_LABELS.documents}
                tabKey="documents"
                activeTab={activeTab}
                onSelect={handleSetTab}
              />
              <SidebarItem
                label={TAB_LABELS.dd_grid}
                tabKey="dd_grid"
                activeTab={activeTab}
                onSelect={handleSetTab}
              />
              <SidebarItem
                label={TAB_LABELS.requests}
                tabKey="requests"
                activeTab={activeTab}
                onSelect={handleSetTab}
              />
              <SidebarItem
                label={TAB_LABELS.report}
                tabKey="report"
                activeTab={activeTab}
                onSelect={handleSetTab}
              />
              <SidebarItem
                label={TAB_LABELS.audit}
                tabKey="audit"
                activeTab={activeTab}
                onSelect={handleSetTab}
              />
            </div>

            <div className="mt-5 border-t border-[var(--border)] pt-4">
              <SidebarItem
                label={TAB_LABELS.settings}
                tabKey="settings"
                activeTab={activeTab}
                onSelect={handleSetTab}
                disabled={!canManageProject}
              />
            </div>
          </nav>
        </aside>

        <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          <header className="shrink-0 border-b border-[var(--border)] bg-[var(--bg-card)] md:hidden">
            <div className="px-4 py-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <span className="text-[length:var(--font-size-ui-xs)] leading-[var(--line-height-ui-xs)] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">
                    {activeTabLabel}
                  </span>
                  <h1 className="mt-2 truncate text-base font-semibold text-[var(--text-primary)]">
                    {deal.name}
                  </h1>
                </div>

                <div className="shrink-0">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={handleBackToProjects}
                  >
                    Назад
                  </Button>
                </div>
              </div>

              <div className="mt-4">
                <div
                  className="flex overflow-x-auto border-t border-[var(--border)] pt-3"
                  role="tablist"
                  aria-label="Разделы проекта"
                  onKeyDown={handleMobileTabKeyDown}
                >
                  <MobileTab
                    label={TAB_LABELS.overview}
                    tabKey="overview"
                    activeTab={activeTab}
                    onSelect={handleSetTab}
                  />
                  <MobileTab
                    label={TAB_LABELS.documents}
                    tabKey="documents"
                    activeTab={activeTab}
                    onSelect={handleSetTab}
                  />
                  <MobileTab
                    label={TAB_LABELS.dd_grid}
                    tabKey="dd_grid"
                    activeTab={activeTab}
                    onSelect={handleSetTab}
                  />
                  <MobileTab
                    label={TAB_LABELS.requests}
                    tabKey="requests"
                    activeTab={activeTab}
                    onSelect={handleSetTab}
                  />
                  <MobileTab
                    label={TAB_LABELS.report}
                    tabKey="report"
                    activeTab={activeTab}
                    onSelect={handleSetTab}
                  />
                  <MobileTab
                    label={TAB_LABELS.audit}
                    tabKey="audit"
                    activeTab={activeTab}
                    onSelect={handleSetTab}
                  />
                  <MobileTab
                    label={TAB_LABELS.settings}
                    tabKey="settings"
                    activeTab={activeTab}
                    onSelect={handleSetTab}
                    disabled={!canManageProject}
                  />
                </div>
              </div>
            </div>
          </header>

          <section
            id={getTabPanelId(activeTab)}
            role="tabpanel"
            aria-labelledby={getTabId(activeTab)}
            className="min-h-0 min-w-0 flex-1 overflow-y-auto px-4 py-4 md:px-6 md:py-6"
            tabIndex={0}
          >
            <div className="flex min-h-full flex-col">
              {renderActiveTabPanel()}
            </div>
          </section>
        </main>
      </div>
    </div>
  );
};

interface SidebarItemProps {
  label: string;
  tabKey: TabKey;
  activeTab: TabKey;
  onSelect: (tab: TabKey) => void;
  disabled?: boolean;
}

const SidebarItem: React.FC<SidebarItemProps> = ({
  label,
  tabKey,
  activeTab,
  onSelect,
  disabled = false,
}) => {
  const isActive = activeTab === tabKey;

  return (
    <button
      type="button"
      onClick={() => {
        if (!disabled) onSelect(tabKey);
      }}
      disabled={disabled}
      aria-current={isActive ? "page" : undefined}
      className={[
        sidebarItemBaseClassName,
        disabled
          ? "cursor-not-allowed text-[var(--text-muted)] opacity-50"
          : isActive
            ? "bg-[var(--bg-elevated-soft)] text-[var(--text-primary)]"
            : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)]",
      ].join(" ")}
    >
      {label}
    </button>
  );
};

interface MobileTabProps {
  label: string;
  tabKey: TabKey;
  activeTab: TabKey;
  onSelect: (tab: TabKey) => void;
  disabled?: boolean;
}

const MobileTab: React.FC<MobileTabProps> = ({
  label,
  tabKey,
  activeTab,
  onSelect,
  disabled = false,
}) => {
  const isActive = activeTab === tabKey;

  return (
    <button
      id={getTabId(tabKey)}
      type="button"
      onClick={() => {
        if (!disabled) onSelect(tabKey);
      }}
      disabled={disabled}
      role="tab"
      aria-selected={isActive}
      aria-controls={getTabPanelId(tabKey)}
      tabIndex={isActive ? 0 : -1}
      className={[
        mobileTabBaseClassName,
        disabled
          ? "cursor-not-allowed border-transparent text-[var(--text-muted)] opacity-50"
          : isActive
            ? "border-[var(--accent-primary)] text-[var(--accent-primary)]"
            : "border-transparent text-[var(--text-muted)] hover:border-[var(--border)] hover:text-[var(--text-secondary)]",
      ].join(" ")}
    >
      {label}
    </button>
  );
};

export default DealPage;





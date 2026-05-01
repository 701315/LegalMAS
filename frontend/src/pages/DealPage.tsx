// =============================================================
// src/pages/DealPage.tsx
// Страница сделки / проекта.
// Legal workspace shell: full-width layout, left sidebar,
// project header, tabs for Overview / Documents / DD Grid / etc.
// Логика запуска анализа перенесена в OverviewTab.
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

function isTabKey(value: string | null): value is TabKey {
  return !!value && TAB_KEYS.includes(value as TabKey);
}

function getReadableDealStatus(status: Deal["status"]): string {
  if (status === "active") return "Активная";
  if (status === "archived") return "В архиве";
  if (status === "draft") return "Черновик";
  return status;
}

function getReadableChecksMode(
  mode?: Deal["last_run_checks_mode"] | null,
): string | null {
  if (!mode) return null;
  if (mode === "global_and_doc_type") return "Плейбук и типы документов";
  if (mode === "global_only") return "Только плейбук";
  if (mode === "doc_type_only") return "Только типы документов";
  return mode;
}

const DealPage: React.FC<DealPageProps> = ({ deal }) => {
  const navigate = useNavigate();
  const location = useLocation();

  const latestRunId = deal.last_run_id ?? null;
  const hasLatestRun = !!latestRunId;

  const {
    canViewOverview,
    canManageRequests,
    canUploadDocuments,
    canStartRun,
  } = useDealPermissions(deal.id);

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

  const [showMobileRunHint, setShowMobileRunHint] = React.useState(false);

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

  const handleOpenMembers = () => {
    if (!canManageProject) return;
    navigate(`/projects/${deal.id}/members`);
  };

  const handleOpenPlaybook = () => {
    if (!canViewOverview) return;
    navigate(`/projects/${deal.id}/playbook`);
  };

  const handleOpenPlaybookTemplates = () => {
    if (!canViewOverview) return;
    navigate(`/projects/${deal.id}/playbooks/admin`);
  };

  const handleOpenModelConfig = () => {
    const params = new URLSearchParams();
    params.set("dealId", deal.id);

    if (deal.playbook_version_id) {
      params.set("playbookVersionId", deal.playbook_version_id);
    }

    navigate(`/admin/model-configs?${params.toString()}`);
  };

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

  const renderRunRequiredState = (title: string, description: string) => (
    <div className="rounded-lg border border-gray-200 bg-gray-50 px-5 py-5">
      <p className="text-sm font-medium text-gray-900">{title}</p>
      <p className="mt-1.5 text-sm text-gray-600">{description}</p>
    </div>
  );

  const renderSettingsTab = () => {
    if (!canManageProject) {
      return (
        <div className="rounded-lg border border-gray-200 bg-gray-50 px-5 py-5">
          <p className="text-sm font-medium text-gray-900">
            Настройки проекта недоступны
          </p>
          <p className="mt-1.5 text-sm text-gray-600">
            У вас нет прав на изменение участников, playbook или шаблонов
            проекта.
          </p>
        </div>
      );
    }

    return (
      <div className="space-y-4">
        <div className="rounded-lg border border-gray-200 bg-white p-5">
          <h2 className="text-base font-semibold text-gray-900">
            Настройки проекта
          </h2>
          <p className="mt-1 max-w-2xl text-sm text-gray-600">
            Управление участниками и конфигурацией проекта вынесено отдельно от
            рабочего review-потока.
          </p>
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-gray-200 bg-white p-5">
            <h3 className="text-sm font-semibold text-gray-900">
              Участники проекта
            </h3>
            <p className="mt-1 text-sm text-gray-600">
              Управление составом команды проекта и доступами.
            </p>
            <div className="mt-4">
              <Button
                variant="secondary"
                size="sm"
                onClick={handleOpenMembers}
              >
                Открыть участников проекта
              </Button>
            </div>
          </div>

          <div className="rounded-lg border border-gray-200 bg-white p-5">
            <h3 className="text-sm font-semibold text-gray-900">
              Playbook проекта
            </h3>
            <p className="mt-1 text-sm text-gray-600">
              Выбор и настройка playbook, используемого для анализа документов.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={handleOpenPlaybook}
              >
                Открыть playbook проекта
              </Button>

              <Button
                variant="secondary"
                size="sm"
                onClick={handleOpenPlaybookTemplates}
              >
                Конструктор шаблонов
              </Button>
            </div>
          </div>
        </div>
      </div>
    );
  };

  const activeTabLabel = React.useMemo(() => {
    const labels: Record<TabKey, string> = {
      overview: "Обзор",
      documents: "Документы",
      dd_grid: "DD Grid",
      requests: "Запросы",
      report: "Отчёт",
      audit: "Аудит",
      settings: "Настройки",
    };

    return labels[activeTab];
  }, [activeTab]);

  const showRestartHint = deal.has_pending_manual_reclassifications;

  return (
    <div className="min-h-screen w-full bg-gray-50">
      {/* Desktop header */}
      <header className="hidden border-b border-gray-200 bg-white md:grid md:grid-cols-[16rem_minmax(0,1fr)]">
        <div className="border-r border-gray-200 p-4">
          <div className="flex h-full min-h-[140px] items-start justify-center rounded-md border border-gray-300 bg-gray-50 px-4 py-4 text-sm font-medium text-gray-600">
            Лого
          </div>
        </div>

        <div className="px-6 py-5">
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-semibold text-gray-900">
              {deal.name}
            </h1>
          </div>
        </div>
      </header>

      <div className="flex min-h-[calc(100vh-0px)] w-full">
        {/* Desktop sidebar */}
        <aside className="hidden md:flex md:w-64 md:flex-col md:border-r md:border-gray-200 md:bg-white">
          <nav
            className="flex h-full flex-col px-3 py-4"
            aria-label="Навигация по проекту"
          >
            <div className="space-y-1">
              <SidebarItem
                label="Обзор"
                tabKey="overview"
                activeTab={activeTab}
                onSelect={handleSetTab}
              />
              <SidebarItem
                label="Документы"
                tabKey="documents"
                activeTab={activeTab}
                onSelect={handleSetTab}
              />
              <SidebarItem
                label="DD Grid"
                tabKey="dd_grid"
                activeTab={activeTab}
                onSelect={handleSetTab}
              />
              <SidebarItem
                label="Запросы"
                tabKey="requests"
                activeTab={activeTab}
                onSelect={handleSetTab}
              />
              <SidebarItem
                label="Отчёты"
                tabKey="report"
                activeTab={activeTab}
                onSelect={handleSetTab}
              />
              <SidebarItem
                label="Аудит"
                tabKey="audit"
                activeTab={activeTab}
                onSelect={handleSetTab}
              />
            </div>

            <div className="mt-5 border-t border-gray-200 pt-4">
              <SidebarItem
                label="Настройки"
                tabKey="settings"
                activeTab={activeTab}
                onSelect={handleSetTab}
                disabled={!canManageProject}
              />
            </div>
          </nav>
        </aside>

        {/* Main workspace */}
        <main className="flex min-w-0 flex-1 flex-col">
          {/* Mobile header + tabs */}
          <header className="border-b border-gray-200 bg-white md:hidden">
            <div className="px-4 py-4">
              <div className="flex justify-end">
                <span className="text-xs text-gray-500">
                  {activeTabLabel}
                </span>
              </div>

              <div className="mt-3">
                <h1 className="text-xl font-semibold text-gray-900">
                  {deal.name}
                </h1>

                <div className="mt-2 flex flex-col gap-1 text-sm text-gray-600">
                  <span>Статус: {getReadableDealStatus(deal.status)}</span>

                  {deal.metadata_?.contact_person && (
                    <span>
                      Контактное лицо: {deal.metadata_.contact_person}
                    </span>
                  )}

                  {getReadableChecksMode(deal.last_run_checks_mode) && (
                    <span>
                      Режим анализа:{" "}
                      {getReadableChecksMode(deal.last_run_checks_mode)}
                    </span>
                  )}
                </div>

                {showRestartHint && (
                  <p className="mt-2 text-xs text-red-600">
                    После ручной переклассификации требуется повторный запуск
                    анализа.
                  </p>
                )}

                <div className="mt-4">
                  <Button
                    variant="primary"
                    size="sm"
                    disabled={!canStartRun}
                    onClick={() => setShowMobileRunHint(true)}
                  >
                    Запустить анализ документов
                  </Button>
                  {showMobileRunHint && (
                    <p className="mt-2 text-[11px] text-gray-500">
                      Параметры запуска доступны на вкладке «Обзор» в правом
                      блоке «Анализ документов». На мобильных устройствах панели
                      запуска открываются из этого раздела, чтобы сохранить
                      единый сценарий работы.
                    </p>
                  )}
                </div>
              </div>

              <div className="mt-4">
                <div
                  className="flex overflow-x-auto border-t border-gray-200 pt-3 text-xs"
                  role="tablist"
                  aria-label="Разделы проекта"
                >
                  <MobileTab
                    label="Обзор"
                    tabKey="overview"
                    activeTab={activeTab}
                    onSelect={handleSetTab}
                  />
                  <MobileTab
                    label="Документы"
                    tabKey="documents"
                    activeTab={activeTab}
                    onSelect={handleSetTab}
                  />
                  <MobileTab
                    label="DD Grid"
                    tabKey="dd_grid"
                    activeTab={activeTab}
                    onSelect={handleSetTab}
                  />
                  <MobileTab
                    label="Запросы"
                    tabKey="requests"
                    activeTab={activeTab}
                    onSelect={handleSetTab}
                  />
                  <MobileTab
                    label="Отчёты"
                    tabKey="report"
                    activeTab={activeTab}
                    onSelect={handleSetTab}
                  />
                  <MobileTab
                    label="Аудит"
                    tabKey="audit"
                    activeTab={activeTab}
                    onSelect={handleSetTab}
                  />
                  <MobileTab
                    label="Настройки"
                    tabKey="settings"
                    activeTab={activeTab}
                    onSelect={handleSetTab}
                    disabled={!canManageProject}
                  />
                </div>
              </div>
            </div>
          </header>

          {/* Content area */}
          <section className="min-w-0 flex-1 px-4 py-4 md:px-6 md:py-6">
            {activeTab === "overview" && (
              <OverviewTab
                deal={deal}
                latestRunId={latestRunId}
                onOpenModelConfig={handleOpenModelConfig}
              />
            )}

            {activeTab === "documents" &&
              (hasLatestRun ? (
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
              ))}

            {activeTab === "dd_grid" &&
              (hasLatestRun ? (
                <GridTab dealId={deal.id} runId={latestRunId} />
              ) : (
                renderRunRequiredState(
                  "DD Grid пока недоступен",
                  "Для этого проекта ещё не запускался анализ. Запустите первый анализ, чтобы открыть матрицу проверок.",
                )
              ))}

            {activeTab === "requests" &&
              (hasLatestRun ? (
                <RequestsTab
                  dealId={deal.id}
                  runId={latestRunId}
                  onOpenViewerAt={handleOpenViewerAt}
                />
              ) : (
                renderRunRequiredState(
                  "Запросы пока недоступны",
                  "Сначала нужен хотя бы один анализ, чтобы система сформировала follow‑up запросы по найденным рискам.",
                )
              ))}

            {activeTab === "report" && <ReportTab dealId={deal.id} />}

            {activeTab === "audit" && <AuditTab dealId={deal.id} />}

            {activeTab === "settings" && renderSettingsTab()}
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
      className={`w-full rounded-md px-3 py-2 text-left text-sm font-medium transition ${
        disabled
          ? "cursor-not-allowed text-gray-300"
          : isActive
          ? "bg-blue-50 text-blue-700"
          : "text-gray-700 hover:bg-gray-50 hover:text-gray-900"
      }`}
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
      type="button"
      onClick={() => {
        if (!disabled) onSelect(tabKey);
      }}
      disabled={disabled}
      role="tab"
      aria-selected={isActive}
      className={`shrink-0 border-b-2 px-3 py-2 text-xs font-medium ${
        disabled
          ? "cursor-not-allowed border-transparent text-gray-300"
          : isActive
          ? "border-blue-600 text-blue-600"
          : "border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700"
      }`}
    >
      {label}
    </button>
  );
};

export default DealPage;






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
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5">
      <p className="text-sm font-medium text-[var(--text-primary)]">{title}</p>
      <p className="mt-1.5 text-sm text-[var(--text-secondary)]">
        {description}
      </p>
    </div>
  );

  const renderSettingsTab = () => {
    if (!canManageProject) {
      return (
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5">
          <p className="text-sm font-medium text-[var(--text-primary)]">
            Настройки проекта недоступны
          </p>
          <p className="mt-1.5 text-sm text-[var(--text-secondary)]">
            У вас нет прав на изменение участников, playbook или шаблонов
            проекта.
          </p>
        </div>
      );
    }

    return (
      <div className="space-y-4">
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5">
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">
            Настройки проекта
          </h2>
          <p className="mt-1 max-w-2xl text-xs text-[var(--text-secondary)]">
            Управление участниками и конфигурацией проекта вынесено отдельно от
            рабочего review‑потока.
          </p>
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5">
            <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              Участники проекта
            </h3>
            <p className="mt-1 text-xs text-[var(--text-secondary)]">
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

          <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5">
            <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
              Playbook проекта
            </h3>
            <p className="mt-1 text-xs text-[var(--text-secondary)]">
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
    <div className="min-h-screen w-full bg-[var(--bg-base)]">
      {/* Desktop header */}
      <header className="hidden border-b border-[var(--border)] bg-[var(--bg-card)] md:grid md:grid-cols-[15rem_minmax(0,1fr)]">
        <div className="border-r border-[var(--border)] p-4">
          <div className="flex h-full min-h-[140px] items-center justify-center rounded-2xl border border-dashed border-[var(--border)] bg-[var(--bg-base)] px-4 py-4 text-[11px] font-medium uppercase tracking-[0.18em] text-[var(--text-muted)]">
            Project workspace
          </div>
        </div>

        <div className="px-6 py-5">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0 space-y-1">
              <h1 className="truncate text-lg font-semibold tracking-tight text-[var(--text-primary)]">
                {deal.name}
              </h1>
              <div className="flex flex-wrap gap-2 text-[11px] text-[var(--text-muted)]">
                <span className="rounded-full bg-white/5 px-2 py-0.5 font-mono uppercase tracking-[0.18em]">
                  {getReadableDealStatus(deal.status)}
                </span>
                {deal.metadata_?.contact_person && (
                  <span className="rounded-full bg-white/5 px-2 py-0.5">
                    Контакт: {deal.metadata_.contact_person}
                  </span>
                )}
                {getReadableChecksMode(deal.last_run_checks_mode) && (
                  <span className="rounded-full bg-white/5 px-2 py-0.5">
                    Режим анализа:{" "}
                    {getReadableChecksMode(deal.last_run_checks_mode)}
                  </span>
                )}
              </div>
              {showRestartHint && (
                <p className="text-[11px] text-amber-300">
                  После ручной переклассификации требуется повторный запуск
                  анализа.
                </p>
              )}
            </div>

            <div className="hidden md:flex items-center gap-2">
              <Button
                variant="primary"
                size="sm"
                disabled={!canStartRun}
                onClick={() => handleSetTab("overview")}
              >
                Запустить анализ
              </Button>
            </div>
          </div>
        </div>
      </header>

      <div className="flex min-h-[calc(100vh-0px)] w-full">
        {/* Desktop sidebar */}
        <aside className="hidden md:flex md:w-60 md:flex-col md:border-r md:border-[var(--border)] md:bg-[var(--bg-card)]">
          <nav
            className="flex h-full flex-col px-3 py-4"
            aria-label="Навигация по проекту"
          >
            <div className="space-y-1 text-xs">
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
                label="Отчёт"
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

            <div className="mt-5 border-t border-[var(--border)] pt-4">
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
          <header className="border-b border-[var(--border)] bg-[var(--bg-card)] md:hidden">
            <div className="px-4 py-4">
              <div className="flex justify-between items-center">
                <span className="text-[11px] uppercase tracking-[0.16em] text-[var(--text-muted)]">
                  {activeTabLabel}
                </span>
              </div>

              <div className="mt-3">
                <h1 className="text-base font-semibold text-[var(--text-primary)]">
                  {deal.name}
                </h1>

                <div className="mt-2 flex flex-col gap-1 text-xs text-[var(--text-secondary)]">
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
                  <p className="mt-2 text-[11px] text-amber-300">
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
                    <p className="mt-2 text-[11px] text-[var(--text-muted)]">
                      Параметры запуска доступны на вкладке «Обзор» в блоке
                      «Анализ документов». На мобильных устройствах панели
                      запуска открываются из этого раздела.
                    </p>
                  )}
                </div>
              </div>

              <div className="mt-4">
                <div
                  className="flex overflow-x-auto border-t border-[var(--border)] pt-3 text-xs"
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
                    label="Отчёт"
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
      className={[
        "w-full rounded-lg px-3 py-2 text-left text-xs font-medium transition-colors",
        disabled
          ? "cursor-not-allowed text-[var(--text-muted)]/40"
          : isActive
          ? "bg-white/5 text-[var(--text-primary)]"
          : "text-[var(--text-secondary)] hover:bg-white/3 hover:text-[var(--text-primary)]",
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
      type="button"
      onClick={() => {
        if (!disabled) onSelect(tabKey);
      }}
      disabled={disabled}
      role="tab"
      aria-selected={isActive}
      className={[
        "shrink-0 border-b-2 px-3 py-2 text-[11px] font-medium transition-colors",
        disabled
          ? "cursor-not-allowed border-transparent text-[var(--text-muted)]/40"
          : isActive
          ? "border-[var(--accent)] text-[var(--accent)]"
          : "border-transparent text-[var(--text-muted)] hover:border-[var(--border)] hover:text-[var(--text-secondary)]",
      ].join(" ")}
    >
      {label}
    </button>
  );
};

export default DealPage;






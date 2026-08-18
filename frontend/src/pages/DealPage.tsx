// =============================================================
// src/pages/DealPage.tsx
// Страница сделки / проекта.
//
// Архитектурный принцип:
// - current run для сделки определяется только через deal.last_run_id;
// - DealPage не вычисляет "последний run" самостоятельно;
// - DealPage лишь маршрутизирует current run id в нужные вкладки.
// =============================================================

import React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import type { Deal, OpenViewerAtPayload } from "../types";
import OverviewTab from "./tabs/OverviewTab";
import GridTab from "./tabs/GridTab";
import DocumentsTab from "./tabs/DocumentsTab";
import { RequestsTab } from "./tabs/RequestsTab";
import { ReportTab } from "./tabs/ReportTab";
import { AuditTab } from "./tabs/AuditTab";
import CounterpartiesTab from "./tabs/CounterpartiesTab";
import RealEstateTab from "./tabs/RealEstateTab";
import { useEnsureProjectRole } from "../hooks/useEnsureProjectRole";
import Button from "../components/ui/Button";
import { useIsMobile } from "../hooks/useIsMobile";
import { runKeys, useStartRun } from "../api/runs";
import { useSetPrimaryLanguage, useUpdateDeal } from "../api/deals";
import { useDocuments } from "../api/documents";
import { useDealPermissions } from "../hooks/usePermissions";
import LaunchWideOverlay from "./tabs/overview/LaunchWideOverlay";
import {
  normalizeDiscoveryStatus,
  normalizeLang,
} from "../utils/languageDiscovery";
import type { ChecksMode } from "./tabs/OverviewTab";


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
  | "counterparties"
  | "real_estate";

const TAB_KEYS: TabKey[] = [
  "overview",
  "documents",
  "dd_grid",
  "requests",
  "report",
  "audit",
  "counterparties",
  "real_estate",
];

const TAB_LABELS: Record<TabKey, string> = {
  overview: "Обзор",
  documents: "Документы",
  dd_grid: "DD Grid",
  requests: "Запросы",
  report: "Отчёт",
  audit: "Аудит",
  counterparties: "Контрагенты",
  real_estate: "Имущество",
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
  const isMobile = useIsMobile();
  const navigate = useNavigate();
  const location = useLocation();

  const currentRunId = deal.last_run_id ?? null;
  const hasCurrentRun = currentRunId !== null;

  useEnsureProjectRole(deal.id);

  // ────────────────────────────────────────────────────────────────────
  // Page mode: "normal" (вкладки) или "relaunch" (панель перезапуска).
  //
  // Паттерн аналогичен CounterpartiesTab (IntroScreen ↔ DemoScreen):
  // сайдбар остаётся видимым, меняется только контент main-области.
  // ────────────────────────────────────────────────────────────────────
  type PageMode = "normal" | "relaunch";
  const [pageMode, setPageMode] = React.useState<PageMode>("normal");

  const handleOpenLaunchPanel = React.useCallback(() => {
    setPageMode("relaunch");
  }, []);

  const handleCloseLaunchPanel = React.useCallback(() => {
    setPageMode("normal");
  }, []);

  const searchParams = React.useMemo(
    () => new URLSearchParams(location.search),
    [location.search],
  );

  const tabFromUrl = searchParams.get("tab");
  const initialTab: TabKey = isTabKey(tabFromUrl) ? tabFromUrl : "overview";

  const [activeTab, setActiveTab] = React.useState<TabKey>(initialTab);
  const [viewerLocation, setViewerLocation] =
    React.useState<OpenViewerAtPayload | null>(null);

  // Когда открыта панель перезапуска, ни одна вкладка не активна —
  // активным подсвечивается пункт "Перезапустить проект" в сайдбаре.
  const sidebarActiveTab: TabKey | null =
    pageMode === "relaunch" ? null : activeTab;

  React.useEffect(() => {
    setActiveTab(isTabKey(tabFromUrl) ? tabFromUrl : "overview");
  }, [tabFromUrl]);

  const handleSetTab = React.useCallback(
    (tab: TabKey) => {
      // При навигации по вкладкам закрываем relaunch-режим,
      // чтобы переключение вкладок работало независимо от того,
      // открыта ли сейчас панель перезапуска.
      setPageMode("normal");
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
      if (currentIndex < 0) {
        return;
      }

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

      handleSetTab(nextTab);

      window.requestAnimationFrame(() => {
        const nextElement = document.getElementById(getTabId(nextTab));
        nextElement?.focus();
      });
    },
    [activeTab, handleSetTab],
  );

  const renderRunRequiredState = React.useCallback(
    (title: string, description: string) => (
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5">
        <p className="text-sm font-medium text-[var(--text-primary)]">{title}</p>
        <p className="mt-1.5 text-sm text-[var(--text-secondary)]">
          {description}
        </p>
      </div>
    ),
    [],
  );

  const activeTabLabel = TAB_LABELS[activeTab];

  const renderActiveTabPanel = () => {
    if (activeTab === "overview") {
      return <OverviewTab deal={deal} currentRunId={currentRunId} />;
    }

    if (activeTab === "documents") {
      return hasCurrentRun ? (
        <DocumentsTab
          deal={deal}
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
      return hasCurrentRun ? (
        <GridTab dealId={deal.id} runId={currentRunId} />
      ) : (
        renderRunRequiredState(
          "DD Grid пока недоступен",
          "Для этого проекта ещё не запускался анализ. Запустите первый анализ, чтобы открыть матрицу проверок.",
        )
      );
    }

    if (activeTab === "requests") {
      return hasCurrentRun ? (
        <RequestsTab
          dealId={deal.id}
          runId={currentRunId}
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
      return <ReportTab runId={currentRunId} />;
    }

    if (activeTab === "audit") {
      return <AuditTab dealId={deal.id} />;
    }

    if (activeTab === "counterparties") {
      return (
        <CounterpartiesTab dealId={deal.id} currentRunId={currentRunId} />
      );
    }

    if (activeTab === "real_estate") {
      return (
        <RealEstateTab dealId={deal.id} currentRunId={currentRunId} />
      );
    }

    return null;

  };

    return (
      <div className="flex h-full min-h-0 w-full flex-col overflow-hidden bg-[var(--bg-card)]">
        <header
          className="hidden shrink-0 border-b border-[var(--border)] lg:block"
          style={{
            backgroundImage:
              "linear-gradient(rgba(15, 23, 42, 0.45), rgba(15, 23, 42, 0.45)), url('/projectpicture.png')",
            backgroundSize: "cover",
            backgroundPosition: "center",
            backgroundRepeat: "no-repeat",
          }}
        >
          <div className="px-6 py-5">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h1 className="truncate text-lg font-semibold tracking-tight text-white">
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
        <aside className="hidden min-h-0 shrink-0 lg:flex lg:w-60 lg:flex-col lg:border-r lg:border-[var(--border)] lg:bg-[var(--bg-card)]">
          <nav
            className="flex h-full flex-col overflow-y-auto overscroll-contain px-3 py-4"
            aria-label="Навигация по проекту"
          >
            {/* ── Обзор — отдельно вверху ── */}
            <div className="mb-3">
              <SidebarItem
                label={TAB_LABELS.overview}
                tabKey="overview"
                activeTab={sidebarActiveTab}
                onSelect={handleSetTab}
              />
            </div>

            {/* ── Группа: Анализ документов по сделке ── */}
            <div className="border-t border-[var(--border)] pt-4">
              <div className="mb-1.5 px-3">
                <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
                  Анализ документов по сделке
                </span>
              </div>
              <div className="space-y-1">
                <SidebarItem
                  label={TAB_LABELS.documents}
                  tabKey="documents"
               activeTab={sidebarActiveTab}
                  onSelect={handleSetTab}
                />
                <SidebarItem
                  label={TAB_LABELS.dd_grid}
                  tabKey="dd_grid"
               activeTab={sidebarActiveTab}
                  onSelect={handleSetTab}
                />
                <SidebarItem
                  label={TAB_LABELS.requests}
                  tabKey="requests"
               activeTab={sidebarActiveTab}
                  onSelect={handleSetTab}
                />
                <SidebarItem
                  label={TAB_LABELS.report}
                  tabKey="report"
               activeTab={sidebarActiveTab}
                  onSelect={handleSetTab}
                />
                <SidebarItem
                  label={TAB_LABELS.audit}
                  tabKey="audit"
               activeTab={sidebarActiveTab}
                  onSelect={handleSetTab}
                />
              </div>
            </div>

            {/* ── Группа: Анализ выявленных контрагентов ── */}
            <div className="mt-5 border-t border-[var(--border)] pt-4">
              <div className="mb-1.5 px-3">
                <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
                  Анализ выявленных контрагентов
                </span>
              </div>
              <SidebarItem
                label="Контрагенты"
                tabKey="counterparties"
             activeTab={sidebarActiveTab}
                onSelect={handleSetTab}
                badge="Скоро"
              />
            </div>

            {/* ── Группа: Анализ выявленного недвижимого имущества ── */}
            <div className="mt-5 border-t border-[var(--border)] pt-4">
              <div className="mb-1.5 px-3">
                <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
                  Анализ выявленного недвижимого имущества
                </span>
              </div>
              <SidebarItem
                label="Имущество"
                tabKey="real_estate"
             activeTab={sidebarActiveTab}
                onSelect={handleSetTab}
                badge="Скоро"
              />
            </div>

            {/* ── Группа: Дополнительные действия ─────────────────────
                Отдельная секция в сайдбаре для действий над проектом,
                не являющихся навигацией по вкладкам. Ссылка "Перезапустить
                проект" переводит на отдельную страницу /relaunch с
                полным layout AppShell. Работает с любой активной вкладки. */}
            <div className="mt-5 border-t border-[var(--border)] pt-4">
              <div className="mb-1.5 px-3">
                <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
                  Дополнительные действия
                </span>
              </div>
              <button
                type="button"
                onClick={handleOpenLaunchPanel}
                aria-current={pageMode === "relaunch" ? "page" : undefined}
                className={[
                  sidebarItemBaseClassName,
                  "flex items-center justify-between gap-2",
                  pageMode === "relaunch"
                    ? "bg-[var(--bg-elevated-soft)] text-[var(--text-primary)]"
                    : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)]",
                ].join(" ")}
              >
                <span className="truncate">Перезапустить проект</span>
              </button>
            </div>

          </nav>
        </aside>

        <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          <header className="shrink-0 border-b border-[var(--border)] bg-[var(--accent-subtle)] lg:hidden">
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

                <div className="flex shrink-0 items-center gap-2">
                  {pageMode === "relaunch" ? (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={handleCloseLaunchPanel}
                    >
                      Отмена
                    </Button>
                  ) : (
                    <>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={handleOpenLaunchPanel}
                      >
                        Перезапустить
                      </Button>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={handleBackToProjects}
                      >
                        Назад
                      </Button>
                    </>
                  )}
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
                 activeTab={sidebarActiveTab}
                    onSelect={handleSetTab}
                  />
                  <MobileTab
                    label={TAB_LABELS.documents}
                    tabKey="documents"
                 activeTab={sidebarActiveTab}
                    onSelect={handleSetTab}
                  />
                  <MobileTab
                    label={TAB_LABELS.dd_grid}
                    tabKey="dd_grid"
                 activeTab={sidebarActiveTab}
                    onSelect={handleSetTab}
                  />
                  <MobileTab
                    label={TAB_LABELS.requests}
                    tabKey="requests"
                 activeTab={sidebarActiveTab}
                    onSelect={handleSetTab}
                  />
                  <MobileTab
                    label={TAB_LABELS.report}
                    tabKey="report"
                 activeTab={sidebarActiveTab}
                    onSelect={handleSetTab}
                  />
                  <MobileTab
                    label={TAB_LABELS.audit}
                    tabKey="audit"
                 activeTab={sidebarActiveTab}
                    onSelect={handleSetTab}
                  />
                  <MobileTab
                    label={TAB_LABELS.counterparties}
                    tabKey="counterparties"
                 activeTab={sidebarActiveTab}
                    onSelect={handleSetTab}
                  />
                  <MobileTab
                    label={TAB_LABELS.real_estate}
                    tabKey="real_estate"
                 activeTab={sidebarActiveTab}
                    onSelect={handleSetTab}
                  />
                </div>
              </div>
            </div>
          </header>

          {pageMode === "relaunch" ? (
            <section
              className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto overscroll-contain p-4 lg:p-6"
              aria-label="Панель перезапуска проекта"
            >
              <RelaunchContent
                deal={deal}
                onClose={handleCloseLaunchPanel}
              />
            </section>
          ) : (
            <section
              id={getTabPanelId(activeTab)}
              role="tabpanel"
              aria-labelledby={getTabId(activeTab)}
              className={`flex min-h-0 min-w-0 flex-1 flex-col ${
                isMobile ? "overflow-y-auto" : "overflow-hidden"
              } p-4 lg:p-6`}
              tabIndex={0}
            >
              {renderActiveTabPanel()}
              {/* Bottom spacer (mobile only). */}
              <div
                aria-hidden="true"
                className="shrink-0 lg:hidden"
                style={{ height: "var(--app-safe-bottom)" }}
              />
            </section>
          )}
        </main>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// SidebarItem
// ---------------------------------------------------------------------------

interface SidebarItemProps {
  label: string;
  tabKey: TabKey;
  activeTab: TabKey | null;
  onSelect: (tab: TabKey) => void;
  disabled?: boolean;
  badge?: string;
}

const SidebarItem: React.FC<SidebarItemProps> = ({
  label,
  tabKey,
  activeTab,
  onSelect,
  disabled = false,
  badge,
}) => {
  const isActive = activeTab === tabKey;

  return (
    <button
      type="button"
      onClick={() => {
        if (!disabled) {
          onSelect(tabKey);
        }
      }}
      disabled={disabled}
      aria-current={isActive ? "page" : undefined}
      className={[
        sidebarItemBaseClassName,
        "flex items-center justify-between gap-2",
        disabled
          ? "cursor-not-allowed text-[var(--text-muted)] opacity-50"
          : isActive
            ? "bg-[var(--bg-elevated-soft)] text-[var(--text-primary)]"
            : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-primary)]",
      ].join(" ")}
    >
      <span className="truncate">{label}</span>
      {badge && (
        <span className="shrink-0 rounded-full bg-[var(--accent-primary)]/10 px-1.5 py-0.5 text-[10px] font-semibold leading-none text-[var(--accent-primary)]">
          {badge}
        </span>
      )}
    </button>
  );
};

// ---------------------------------------------------------------------------
// MobileTab
// ---------------------------------------------------------------------------

interface MobileTabProps {
  label: string;
  tabKey: TabKey;
  activeTab: TabKey | null;
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
        if (!disabled) {
          onSelect(tabKey);
        }
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

// ---------------------------------------------------------------------------
// RelaunchContent
// ---------------------------------------------------------------------------

interface RelaunchContentProps {
  deal: Deal;
  onClose: () => void;
}

const RelaunchContent: React.FC<RelaunchContentProps> = ({ deal, onClose }) => {
  const qc = useQueryClient();

  const { data: documentsPage } = useDocuments(deal.id, 1);
  const documentsCount = documentsPage?.total ?? 0;
  const { canStartRun, canUploadDocuments } = useDealPermissions(deal.id);

  const startRun = useStartRun(deal.id);
  const updateDealForLaunch = useUpdateDeal(deal.id);
  const setPrimaryLanguage = useSetPrimaryLanguage(deal.id);

  const [checksMode, setChecksMode] =
    React.useState<ChecksMode>("global_and_doc_type");
  const [forceReclassify, setForceReclassify] = React.useState(false);
  const [launchDealPatch, setLaunchDealPatch] = React.useState<Partial<Deal>>(
    {},
  );

  const currentRunId = deal.last_run_id ?? null;
  const hasCurrentRun = currentRunId !== null;

  const dealLanguagesKey = JSON.stringify(deal.languages ?? []);

  React.useEffect(() => {
    setLaunchDealPatch({});
  }, [
    deal.id,
    deal.playbook_version_id,
    deal.primary_language,
    deal.language_discovery_status,
    dealLanguagesKey,
  ]);

  const effectiveDeal: Deal = { ...deal, ...launchDealPatch };

  const hasDocuments = documentsCount > 0;

  const discoveryStatus = normalizeDiscoveryStatus(
    effectiveDeal.language_discovery_status,
  );

  const isLanguageDiscoveryBlocking =
    discoveryStatus === "pending" || discoveryStatus === "processing";

  const canLaunchRun =
    canStartRun &&
    hasDocuments &&
    !!effectiveDeal.playbook_version_id &&
    !!effectiveDeal.primary_language &&
    !isLanguageDiscoveryBlocking &&
    !startRun.isPending &&
    !updateDealForLaunch.isPending &&
    !setPrimaryLanguage.isPending;

  const isSubmitting =
    startRun.isPending ||
    updateDealForLaunch.isPending ||
    setPrimaryLanguage.isPending;

  const handlePrimaryLanguageChange = React.useCallback(
    (value: string) => {
      const normalizedValue = normalizeLang(value) || null;
      setLaunchDealPatch((prev) => ({
        ...prev,
        primary_language: normalizedValue,
      }));
      setPrimaryLanguage.mutate(
        { primary_language: normalizedValue },
        {
          onError: () => {
            setLaunchDealPatch((prev) => ({
              ...prev,
              primary_language: deal.primary_language ?? null,
            }));
          },
        },
      );
    },
    [deal.primary_language, setPrimaryLanguage],
  );

  const handleStartRun = React.useCallback(() => {
    if (!canLaunchRun) return;
    startRun.mutate(
      {
        profile: "core",
        checks_mode: checksMode,
        force_reclassify: forceReclassify,
      },
      {
        onSuccess: async (run) => {
          setForceReclassify(false);
          await Promise.all([
            qc.invalidateQueries({ queryKey: runKeys.detail(run.id, true) }),
            qc.invalidateQueries({ queryKey: runKeys.detail(run.id, false) }),
            qc.invalidateQueries({
              queryKey: runKeys.classificationReport(run.id),
            }),
            qc.invalidateQueries({ queryKey: ["deal", deal.id] }),
            qc.invalidateQueries({ queryKey: runKeys.history(deal.id, false) }),
            qc.invalidateQueries({ queryKey: runKeys.history(deal.id, true) }),
          ]);
          onClose();
        },
      },
    );
  }, [canLaunchRun, checksMode, deal.id, forceReclassify, qc, startRun, onClose]);

  const handleDealPatched = React.useCallback(
    async (patch?: Partial<Deal>) => {
      if (patch && Object.keys(patch).length > 0) {
        setLaunchDealPatch((prev) => ({ ...prev, ...patch }));
      }
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["deal", deal.id] }),
      ]);
    },
    [deal.id, qc],
  );

  return (
    <section
      className="flex flex-col lg:h-full lg:min-h-0"
      aria-labelledby="relaunch-content-title"
    >
      <div className="relative flex flex-col text-[var(--text-primary)] lg:min-h-0 lg:flex-1">
        <div className="grid gap-4 lg:min-h-0 lg:flex-1 grid-cols-1">
          {/* ── Карточка перезапуска (паттерн DocumentsTab) ─── */}
          <section className="flex flex-col rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm lg:min-h-0 lg:overflow-hidden">
            {/* Header — паттерн DocumentsTab */}
            <div className="px-5">
              <div className="py-3">
                <h2
                  id="relaunch-content-title"
                  className="text-sm font-semibold text-[var(--text-primary)]"
                >
                  {hasCurrentRun ? "Перезапуск анализа" : "Запуск анализа"}
                </h2>
                <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
                  {hasCurrentRun
                    ? "Проверьте документы и текущие настройки проекта перед новым прогоном."
                    : "Проверьте документы и настройки проекта перед первым запуском."}
                </p>
              </div>

              <div className="border-t border-[var(--border-subtle)]" />

              {/* Toolbar — паттерн DocumentsTab */}
              <div className="flex min-h-10 flex-wrap items-center gap-2 py-3">
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  onClick={onClose}
                >
                  Отмена
                </Button>
                {/* primary = терракотовый accent; ml-auto = правый край */}
                <Button
                  type="button"
                  size="sm"
                  variant="primary"
                  onClick={handleStartRun}
                  disabled={!canLaunchRun || isSubmitting}
                  isLoading={isSubmitting}
                  className="ml-auto"
                >
                  {hasCurrentRun ? "Перезапустить анализ" : "Запустить анализ"}
                </Button>
              </div>

              <div className="border-t border-[var(--border-subtle)]" />
            </div>

            {/* Content — LaunchWideOverlay с variant="page".
                Внешний контейнер имеет overflow-auto для прокрутки
                всего блока (включая раскрытые collapsible секции).
                Grid внутри также имеет min-h-0 для правильной работы
                с flex-родителем. */}
            <div className="bg-[var(--bg-card)] px-5 pb-5 pt-4 lg:flex-1 lg:overflow-y-auto lg:overscroll-contain">
              <div className="min-h-0">
                <LaunchWideOverlay
                  variant="page"
                  open={true}
                  deal={effectiveDeal}
                  hasCurrentRun={hasCurrentRun}
                  documentsCount={documentsCount}
                  checksMode={checksMode}
                  onChecksModeChange={setChecksMode}
                  forceReclassify={forceReclassify}
                  onForceReclassifyChange={setForceReclassify}
                  canStartRun={canLaunchRun}
                  canUploadDocuments={canUploadDocuments}
                  isSubmitting={isSubmitting}
                  onPrimaryLanguageChange={handlePrimaryLanguageChange}
                  onSubmit={handleStartRun}
                  onClose={onClose}
                  onDealPatched={handleDealPatched}
                />
              </div>
            </div>
          </section>
        </div>
      </div>
    </section>
  );
};

export default DealPage;




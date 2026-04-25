// =============================================================
// src/pages/DealPage.tsx
// Страница сделки: обзор, DD Grid, документы, запросы, отчёт, аудит.
// Единая точка orchestration для run-scoped review tabs.
// =============================================================

import React from "react";
import { useNavigate, useLocation } from "react-router-dom";
import type { Deal } from "../types";
import OverviewTab from "./tabs/OverviewTab";
import GridTab from "./tabs/GridTab";
import DocumentsTab from "./tabs/DocumentsTab";
import { RequestsTab } from "./tabs/RequestsTab";
import { ReportTab } from "./tabs/ReportTab";
import { AuditTab } from "./tabs/AuditTab";
import { useDealPermissions } from "../hooks/usePermissions";

interface DealPageProps {
  deal: Deal;
}

type TabKey =
  | "overview"
  | "dd_grid"
  | "documents"
  | "requests"
  | "report"
  | "audit";

const TAB_KEYS: TabKey[] = [
  "overview",
  "dd_grid",
  "documents",
  "requests",
  "report",
  "audit",
];

function isTabKey(value: string | null): value is TabKey {
  return !!value && TAB_KEYS.includes(value as TabKey);
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
  } = useDealPermissions(deal.id);

  const canManageProject = canUploadDocuments || canManageRequests;

  const searchParams = React.useMemo(
    () => new URLSearchParams(location.search),
    [location.search],
  );

  const tabFromUrl = searchParams.get("tab");

  const initialTab: TabKey = isTabKey(tabFromUrl) ? tabFromUrl : "overview";

  const [activeTab, setActiveTab] = React.useState<TabKey>(initialTab);

  React.useEffect(() => {
    setActiveTab(isTabKey(tabFromUrl) ? tabFromUrl : "overview");
  }, [tabFromUrl]);

  const handleOpenMembers = () => {
    if (!canManageProject) return;
    navigate(`/projects/${deal.id}/members`);
  };

  const handleOpenUpload = () => {
    if (!canUploadDocuments) return;
    navigate(`/projects/${deal.id}/upload`);
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

  const handleSetTab = (tab: TabKey) => {
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
  };

  const renderLastRunMode = () => {
    const mode = deal.last_run_checks_mode;
    if (!mode) return null;

    if (mode === "global_and_doc_type") return "Плейбук + типы документов";
    if (mode === "global_only") return "Только плейбук";
    if (mode === "doc_type_only") return "Только типы документов";
    return mode;
  };

  const renderRunRequiredState = (title: string, description: string) => (
    <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-4">
      <p className="text-sm font-medium text-amber-900">{title}</p>
      <p className="mt-1 text-sm text-amber-800">{description}</p>
    </div>
  );

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-4">
      <header className="bg-white rounded-lg p-5 border flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{deal.name}</h1>

          <p className="text-sm text-gray-500">
            Сделка #{deal.id} · статус: {deal.status}
          </p>

          {hasLatestRun && (
            <div className="mt-1 text-xs text-gray-500 space-y-0.5">
              <p>Последний анализ: run {deal.last_run_id}</p>

              {renderLastRunMode() && (
                <p>
                  Режим проверок:{" "}
                  <span className="font-medium text-gray-700">
                    {renderLastRunMode()}
                  </span>
                </p>
              )}

              {deal.last_run_pipeline_strategy && (
                <p>
                  Стратегия пайплайна:{" "}
                  <span className="font-medium text-gray-700">
                    {deal.last_run_pipeline_strategy}
                  </span>
                </p>
              )}
            </div>
          )}

          {deal.metadata_?.contact_person && (
            <p className="text-sm text-gray-600 mt-2">
              Контактное лицо: {deal.metadata_.contact_person}
            </p>
          )}
        </div>

        {canManageProject && (
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={handleOpenMembers}
              className="px-3 py-1.5 text-xs md:text-sm rounded border border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
            >
              Участники проекта
            </button>

            {canUploadDocuments && (
              <button
                type="button"
                onClick={handleOpenUpload}
                className="px-3 py-1.5 text-xs md:text-sm rounded border border-blue-600 bg-blue-600 text-white hover:bg-blue-700"
              >
                Загрузить новые документы
              </button>
            )}

            <button
              type="button"
              onClick={handleOpenPlaybook}
              className="px-3 py-1.5 text-xs md:text-sm rounded border border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
            >
              Playbook проекта
            </button>

            <button
              type="button"
              onClick={handleOpenPlaybookTemplates}
              className="px-3 py-1.5 text-xs md:text-sm rounded border border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
            >
              Конструктор шаблонов
            </button>
          </div>
        )}
      </header>

      <div>
        <div
          className="border-b flex gap-4 text-sm overflow-x-auto"
          role="tablist"
          aria-label="Вкладки сделки"
        >
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "overview"}
            onClick={() => handleSetTab("overview")}
            className={`px-3 py-2 font-medium border-b-2 transition-all duration-200 ${
              activeTab === "overview"
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
            }`}
          >
            Обзор
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "dd_grid"}
            onClick={() => handleSetTab("dd_grid")}
            className={`px-3 py-2 font-medium border-b-2 transition-all duration-200 ${
              activeTab === "dd_grid"
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
            }`}
          >
            DD Grid
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "documents"}
            onClick={() => handleSetTab("documents")}
            className={`px-3 py-2 font-medium border-b-2 transition-all duration-200 ${
              activeTab === "documents"
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
            }`}
          >
            Документы
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "requests"}
            onClick={() => handleSetTab("requests")}
            className={`px-3 py-2 font-medium border-b-2 transition-all duration-200 ${
              activeTab === "requests"
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
            }`}
          >
            Запросы
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "report"}
            onClick={() => handleSetTab("report")}
            className={`px-3 py-2 font-medium border-b-2 transition-all duration-200 ${
              activeTab === "report"
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
            }`}
          >
            Отчёт
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "audit"}
            onClick={() => handleSetTab("audit")}
            className={`px-3 py-2 font-medium border-b-2 transition-all duration-200 ${
              activeTab === "audit"
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
            }`}
          >
            Аудит
          </button>
        </div>

        <div className="mt-6">
          {activeTab === "overview" && (
            <div className="transition-opacity duration-200 opacity-100" role="tabpanel">
              <OverviewTab
                deal={deal}
                latestRunId={latestRunId}
                onOpenModelConfig={handleOpenModelConfig}
              />
            </div>
          )}

          {activeTab === "dd_grid" && (
            <div className="transition-opacity duration-200 opacity-100" role="tabpanel">
              {hasLatestRun ? (
                <GridTab dealId={deal.id} runId={latestRunId} />
              ) : (
                renderRunRequiredState(
                  "DD Grid пока недоступен",
                  "Для этой сделки ещё не запускался анализ. Запустите первый run, чтобы открыть матрицу проверок.",
                )
              )}
            </div>
          )}

          {activeTab === "documents" && (
            <div className="transition-opacity duration-200 opacity-100" role="tabpanel">
              {hasLatestRun ? (
                <DocumentsTab deal={deal} runId={latestRunId} />
              ) : (
                renderRunRequiredState(
                  "Список review-документов пока недоступен",
                  "Карточки документов в review-режиме появляются после первого анализа сделки.",
                )
              )}
            </div>
          )}

          {activeTab === "requests" && (
            <div className="transition-opacity duration-200 opacity-100" role="tabpanel">
              {hasLatestRun ? (
                <RequestsTab dealId={deal.id} runId={latestRunId} />
              ) : (
                renderRunRequiredState(
                  "DD-запросы пока недоступны",
                  "Сначала нужен хотя бы один run, чтобы система сформировала запросы по найденным рискам.",
                )
              )}
            </div>
          )}

          {activeTab === "report" && (
            <div className="transition-opacity duration-200 opacity-100" role="tabpanel">
              <ReportTab dealId={deal.id} />
            </div>
          )}

          {activeTab === "audit" && (
            <div className="transition-opacity duration-200 opacity-100" role="tabpanel">
              <AuditTab dealId={deal.id} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default DealPage;



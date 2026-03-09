// =============================================================
// src/pages/DealPage.tsx
// Страница сделки: обзор, DD Grid, документы, запросы, отчёт, аудит.
// Добавлены кнопки администратора/редактора проекта.
// =============================================================

import React from "react";
import { useNavigate } from "react-router-dom";
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

/**
 * Простая реализация Tabs без сторонних библиотек.
 */
type TabKey =
  | "overview"
  | "dd_grid"
  | "documents"
  | "requests"
  | "report"
  | "audit";

const DealPage: React.FC<DealPageProps> = ({ deal }) => {
  const [activeTab, setActiveTab] = React.useState<TabKey>("overview");

  const latestRunId = deal.last_run_id ?? null;

  const navigate = useNavigate();

  // Права пользователя в контексте этой сделки
  const {
    canViewOverview,
    canManageRequests,
    canUploadDocuments,
  } = useDealPermissions(deal.id);

  const canManageProject = canUploadDocuments || canManageRequests;

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

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-4">
      {/* Заголовок сделки + кнопки администратора/редактора */}
      <header className="bg-white rounded-lg p-5 border flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            {deal.name}
          </h1>
          <p className="text-sm text-gray-500">
            Сделка #{deal.id} · статус: {deal.status}
          </p>

          {deal.metadata_?.contact_person && (
            <p className="text-sm text-gray-600 mt-1">
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
          </div>
        )}
      </header>

      {/* Вкладки */}
      <div>
        <div className="border-b flex gap-4 text-sm overflow-x-auto">
          <button
            type="button"
            onClick={() => setActiveTab("overview")}
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
            onClick={() => setActiveTab("dd_grid")}
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
            onClick={() => setActiveTab("documents")}
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
            onClick={() => setActiveTab("requests")}
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
            onClick={() => setActiveTab("report")}
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
            onClick={() => setActiveTab("audit")}
            className={`px-3 py-2 font-medium border-b-2 transition-all duration-200 ${
              activeTab === "audit"
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
            }`}
          >
            Аудит
          </button>
        </div>

        {/* Контент вкладок */}
        <div className="mt-6">
          {activeTab === "overview" && (
            <div className="transition-opacity duration-200 opacity-100">
              <OverviewTab deal={deal} latestRunId={latestRunId} />
            </div>
          )}

          {activeTab === "dd_grid" && (
            <div className="transition-opacity duration-200 opacity-100">
              <GridTab dealId={deal.id} runId={latestRunId} />
            </div>
          )}

          {activeTab === "documents" && (
            <div className="transition-opacity duration-200 opacity-100">
              <DocumentsTab deal={deal} />
            </div>
          )}

          {activeTab === "requests" && (
            <div className="transition-opacity duration-200 opacity-100">
              <RequestsTab dealId={deal.id} />
            </div>
          )}

          {activeTab === "report" && (
            <div className="transition-opacity duration-200 opacity-100">
              <ReportTab dealId={deal.id} />
            </div>
          )}

          {activeTab === "audit" && (
            <div className="transition-opacity duration-200 opacity-100">
              <AuditTab dealId={deal.id} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default DealPage;

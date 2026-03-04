// =============================================================
// src/pages/DealPage.tsx
// Страница сделки: вкладки Overview + DD Grid + Classification (заглушка).
// =============================================================

import React from "react";
import type { Deal } from "../types";
import OverviewTab from "./tabs/OverviewTab";
import GridTab from "./tabs/GridTab";

// Временный тип пропсов:
// в реальном приложении dealId будет из роутера (например, useParams).
interface DealPageProps {
  deal: Deal;
}

/**
 * Простая реализация Tabs без сторонних библиотек.
 * Позже можно заменить на готовый UI-компонент (Radix/Tailwind Tabs).
 */
type TabKey = "overview" | "dd_grid" | "classification";

const DealPage: React.FC<DealPageProps> = ({ deal }) => {
  const [activeTab, setActiveTab] = React.useState<TabKey>("overview");

  // latestRunId берём из поля deal.last_run_id (пришло с бэкенда)
  const latestRunId = deal.last_run_id ?? null;

  // Пока просто флаг-заглушка: есть ли проблемы с классификацией.
  // В реальной версии можно вычислять по classReport.low_confidence_count.
  const classificationWarning = false;

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-4">
      {/* Заголовок сделки */}
      <header className="bg-white rounded-lg p-5 border flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            {deal.name}
          </h1>
          <p className="text-sm text-gray-500">
            Сделка #{deal.id} · статус: {deal.status}
          </p>
        </div>
      </header>

      {/* Вкладки */}
      <div>
        <div className="border-b flex gap-4 text-sm">
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
            onClick={() => setActiveTab("classification")}
            className={`px-3 py-2 font-medium border-b-2 flex items-center gap-1 transition-all duration-200 ${
              activeTab === "classification"
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
            }`}
          >
            Классификация
            {classificationWarning && (
              <span className="ml-1.5 bg-yellow-400 text-black text-xs px-1 rounded">
                !
              </span>
            )}
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

          {activeTab === "classification" && (
            <div className="bg-gray-100 rounded-lg py-16 text-center text-gray-400">
              Классификация документов — будет реализована на отдельном этапе.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default DealPage;

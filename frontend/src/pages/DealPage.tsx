// =============================================================
// src/pages/DealPage.tsx
// Страница сделки: вкладки Overview + Classification (заглушка).
// =============================================================

import React from "react";
import type { Deal } from "../types";
import OverviewTab from "./tabs/OverviewTab";

// Временный тип пропсов:
// в реальном приложении dealId будет из роутера (например, useParams).
interface DealPageProps {
  deal: Deal;
}

/**
 * Простая реализация Tabs без сторонних библиотек.
 * Позже можно заменить на готовый UI-компонент (Radix/Tailwind Tabs).
 */
type TabKey = "overview" | "classification";

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
        <div className="border-b flex gap-4">
          <button
            type="button"
            onClick={() => setActiveTab("overview")}
            className={
              activeTab === "overview"
                ? "px-3 py-2 text-sm font-medium border-b-2 border-blue-600 text-blue-600"
                : "px-3 py-2 text-sm font-medium text-gray-500 hover:text-gray-700"
            }
          >
            Обзор
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("classification")}
            className={
              activeTab === "classification"
                ? "px-3 py-2 text-sm font-medium border-b-2 border-blue-600 text-blue-600 flex items-center gap-1"
                : "px-3 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 flex items-center gap-1"
            }
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
            <OverviewTab deal={deal} latestRunId={latestRunId} />
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

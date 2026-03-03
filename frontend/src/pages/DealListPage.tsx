// =============================================================
// src/pages/DealListPage.tsx
// Страница списка сделок.
// =============================================================

import React from "react";
import { useDeals } from "../api/deals";
import DealCard from "../components/DealCard";

interface DealListPageProps {
  /** Колбэк, вызывается при выборе сделки */
  onSelectDeal?: (dealId: string) => void;
}

const DealListPage: React.FC<DealListPageProps> = ({ onSelectDeal }) => {
  const { data, isLoading, error } = useDeals(1);

  if (isLoading) {
    return (
      <div className="p-6 text-center text-gray-500">
        Загружаем список сделок…
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 text-center text-red-500">
        Не удалось загрузить сделки.
      </div>
    );
  }

  const deals = data?.items ?? [];

  return (
    <div className="min-height-screen bg-gray-50 px-4 py-6">
      <div className="max-w-5xl mx-auto">
        <header className="flex items-center justify-between mb-4">
          <h1 className="text-2xl font-bold text-gray-900">
            Сделки
          </h1>
          <p className="text-sm text-gray-500">
            Найдено: {deals.length}
          </p>
        </header>

        {deals.length === 0 ? (
          <div className="bg-white rounded-lg border p-6 text-center text-gray-500">
            Пока нет сделок.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {deals.map((deal) => (
              <DealCard
                key={deal.id}
                deal={deal}
                onClick={() => onSelectDeal && onSelectDeal(deal.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default DealListPage;

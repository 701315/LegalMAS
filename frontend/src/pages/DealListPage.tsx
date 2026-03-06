// =============================================================
// src/pages/DealListPage.tsx
// Страница списка сделок.
// =============================================================

import React from "react";
import { Link, useParams } from "react-router-dom";
import { useDeals } from "../api/deals";
import DealCard from "../components/DealCard";

interface DealListPageProps {
  /** Колбэк, вызывается при выборе сделки (опционально, для master-detail) */
  onSelectDeal?: (dealId: string) => void;
}

const DealListPage: React.FC<DealListPageProps> = ({ onSelectDeal }) => {
  // Текущая страница (начинаем с 1)
  const [page, setPage] = React.useState(1);
  // Фильтр по статусу (undefined = все)
  const [status, setStatus] = React.useState<string | undefined>(undefined);
  // Фильтр по tenant_id (undefined = все)
  const [tenantId, setTenantId] = React.useState<string | undefined>(undefined);

  // Активная сделка берётся из URL /deals/:dealId
  const params = useParams<{ dealId?: string }>();
  const activeDealId = params.dealId;

  // Загружаем сделки с учетом страницы, статуса и tenantId
  const { data, isLoading, error } = useDeals(page, status, tenantId);

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
  const total = data?.total ?? deals.length;
  const totalPages = data?.total_pages ?? 1;
  const hasNext = data?.has_next ?? false;
  const hasPrevious = data?.has_previous ?? false;

  const handlePrev = () => {
    if (hasPrevious && page > 1) {
      setPage((p) => p - 1);
    }
  };

  const handleNext = () => {
    if (hasNext && page < totalPages) {
      setPage((p) => p + 1);
    }
  };

  const handleStatusChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value || undefined;
    setStatus(value);
    setPage(1); // при смене фильтра возвращаемся на первую страницу
  };

  const handleTenantChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value || undefined;
    setTenantId(value);
    setPage(1);
  };

  return (
    <div className="min-height-screen bg-gray-50 px-4 py-6">
      <div className="max-w-5xl mx-auto">
        <header className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              Сделки
            </h1>
            <p className="text-sm text-gray-500">
              Найдено: {total} (статус: {status ?? "все"})
            </p>
          </div>

          <div className="flex items-center gap-4 text-sm">
            <label className="flex items-center gap-2">
              <span className="text-gray-600">Статус:</span>
              <select
                value={status ?? ""}
                onChange={handleStatusChange}
                className="border rounded px-2 py-1 text-sm"
              >
                <option value="">Все</option>
                <option value="created">created</option>
                <option value="draft">draft</option>
                <option value="in_progress">in_progress</option>
                <option value="completed">completed</option>
              </select>
            </label>

            <label className="flex items-center gap-2">
              <span className="text-gray-600">Tenant ID:</span>
              <input
                type="text"
                value={tenantId ?? ""}
                onChange={handleTenantChange}
                className="border rounded px-2 py-1 text-sm"
                placeholder="UUID"
              />
            </label>

            <div className="text-right text-gray-500">
              <p>
                Страница {page} из {totalPages}
              </p>
            </div>
          </div>
        </header>

        {deals.length === 0 ? (
          <div className="bg-white rounded-lg border p-6 text-center text-gray-500">
            Пока нет сделок.
          </div>
        ) : (
          <>
            {/* Сетка плиток-сделок */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              {deals.map((deal) => (
                <Link
                  key={deal.id}
                  to={`/deals/${deal.id}`}
                  onClick={() => onSelectDeal && onSelectDeal(deal.id)}
                  className="block no-underline text-inherit"
                >
                  <DealCard
                    deal={deal}
                    isActive={activeDealId === deal.id}
                  />
                </Link>
              ))}
            </div>

            {/* Пагинация */}
            <div className="flex items-center justify-between text-sm text-gray-600">
              <button
                type="button"
                onClick={handlePrev}
                disabled={!hasPrevious}
                className={`px-3 py-1 rounded border ${
                  hasPrevious
                    ? "bg-white hover:bg-gray-50"
                    : "bg-gray-100 text-gray-400 cursor-not-allowed"
                }`}
              >
                ← Назад
              </button>

              <span>
                Страница {page} из {totalPages}
              </span>

              <button
                type="button"
                onClick={handleNext}
                disabled={!hasNext}
                className={`px-3 py-1 rounded border ${
                  hasNext
                    ? "bg-white hover:bg-gray-50"
                    : "bg-gray-100 text-gray-400 cursor-not-allowed"
                }`}
              >
                Вперёд →
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default DealListPage;

// =============================================================
// src/pages/DealListPage.tsx
// Страница списка сделок.
// Рендерится внутри AppShell — использует всю ширину рабочей области.
// =============================================================

import React from "react";
import { Link, useParams } from "react-router-dom";
import { useDeals } from "../api/deals";
import DealCard from "../components/DealCard";
import Button from "../components/ui/Button";

interface DealListPageProps {
  /** Колбэк, вызывается при выборе сделки (опционально, для master-detail) */
  onSelectDeal?: (dealId: string) => void;
}

const filterInputClassName =
  "rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none transition focus:border-[var(--accent-primary)] focus:bg-[var(--bg-card)] placeholder:text-[var(--text-muted)]";

const DealListPage: React.FC<DealListPageProps> = ({ onSelectDeal }) => {
  const [page, setPage] = React.useState(1);
  const [status, setStatus] = React.useState<string | undefined>(undefined);
  const [tenantId, setTenantId] = React.useState<string | undefined>(undefined);

  const params = useParams<{ dealId?: string }>();
  const activeDealId = params.dealId;

  const { data, isLoading, error } = useDeals(page, status, tenantId);

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-6 py-5 text-center text-sm text-[var(--text-secondary)] shadow-sm">
          Загружаем список сделок…
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="rounded-2xl border border-[var(--color-error-border)] bg-[var(--color-error-bg)] px-6 py-5 text-center text-sm text-[var(--color-error-text)] shadow-sm">
          Не удалось загрузить сделки.
        </div>
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
    setPage(1);
  };

  const handleTenantChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value || undefined;
    setTenantId(value);
    setPage(1);
  };

  return (
    <div className="h-full overflow-y-auto overscroll-contain">
      <div className="space-y-4 px-4 py-5 md:px-6">
        {/* Header */}
        <header className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div className="min-w-0">
              <div className="inline-flex items-center rounded-full border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">
                Projects
              </div>

              <h1 className="mt-3 text-xl font-semibold tracking-tight text-[var(--text-primary)]">
                Сделки
              </h1>

              <p className="mt-2 text-sm text-[var(--text-secondary)]">
                Найдено: {total}
                {" · "}
                Статус: {status ?? "все"}
              </p>
            </div>

            <div className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-4 py-3 text-sm text-[var(--text-secondary)]">
              Страница{" "}
              <span className="font-semibold text-[var(--text-primary)]">
                {page}
              </span>
              {totalPages > 1 && (
                <>
                  {" "}из{" "}
                  <span className="font-semibold text-[var(--text-primary)]">
                    {totalPages}
                  </span>
                </>
              )}
            </div>
          </div>

          {/* Filters */}
          <div className="mt-5 grid gap-3 border-t border-[var(--border-soft)] pt-4 md:grid-cols-3">
            <label className="block">
              <span className="mb-2 block text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
                Статус
              </span>
              <select
                value={status ?? ""}
                onChange={handleStatusChange}
                className={`${filterInputClassName} w-full`}
              >
                <option value="">Все</option>
                <option value="created">created</option>
                <option value="draft">draft</option>
                <option value="in_progress">in_progress</option>
                <option value="completed">completed</option>
              </select>
            </label>

            <label className="block md:col-span-2">
              <span className="mb-2 block text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
                Tenant ID
              </span>
              <input
                type="text"
                value={tenantId ?? ""}
                onChange={handleTenantChange}
                className={`${filterInputClassName} w-full`}
                placeholder="UUID"
              />
            </label>
          </div>
        </header>

        {/* Content */}
        {deals.length === 0 ? (
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-6 py-10 text-center shadow-sm">
            <div className="mx-auto max-w-md">
              <div className="text-base font-semibold text-[var(--text-primary)]">
                Сделки не найдены
              </div>
              <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                Для текущих фильтров список пуст. Измените статус или tenant,
                чтобы увидеть другие проекты.
              </p>
            </div>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
              {deals.map((deal) => (
                <Link
                  key={deal.id}
                  to={`/deals/${deal.id}`}
                  onClick={() => onSelectDeal?.(deal.id)}
                  className="block rounded-[24px] text-inherit no-underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]"
                >
                  <DealCard
                    deal={deal}
                    isActive={activeDealId === deal.id}
                  />
                </Link>
              ))}
            </div>

            {/* Pagination */}
            <div className="flex flex-col gap-3 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={handlePrev}
                disabled={!hasPrevious}
              >
                ← Назад
              </Button>

              <div className="text-sm text-[var(--text-secondary)]">
                Страница{" "}
                <span className="font-semibold text-[var(--text-primary)]">
                  {page}
                </span>{" "}
                из{" "}
                <span className="font-semibold text-[var(--text-primary)]">
                  {totalPages}
                </span>
              </div>

              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={handleNext}
                disabled={!hasNext}
              >
                Вперёд →
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default DealListPage;



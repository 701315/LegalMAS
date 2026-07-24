// frontend/src/pages/tenant-instructions/TenantBaseGlobalChecksPage.tsx

import React, { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Shield } from "lucide-react";

import { useBaseGlobalChecksCatalog } from "../../api/baseInstructions";
import LoadingBlock from "../../components/ui/LoadingBlock";
import EmptyState from "../../components/ui/EmptyState";
import Button from "../../components/ui/Button";
import VersionStatusBadge from "../../components/instructions/VersionStatusBadge";
import type { GlobalInstructionCatalogItem } from "../../types/instructions";

const sectionTitleCls =
  "text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]";

const CheckCard: React.FC<{
  item: GlobalInstructionCatalogItem;
  onClick: () => void;
}> = ({ item, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    className="group w-full rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 text-left shadow-sm transition-all duration-200 hover:border-[var(--border-strong)] hover:shadow-md"
  >
    <div className="flex items-start gap-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-muted)]">
        <Shield
          className="h-4 w-4 text-[var(--accent-primary)]"
          aria-hidden="true"
        />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            {item.name}
          </p>
          {item.latest_version_status && (
            <VersionStatusBadge
              status={item.latest_version_status}
              size="xs"
            />
          )}
        </div>

        <p className="mt-1 font-mono text-[10px] text-[var(--text-muted)]">
          {item.instruction_code}
        </p>

        <p className="mt-2 text-[10px] text-[var(--text-muted)]">
          Версий:{" "}
          <span className="font-semibold text-[var(--text-primary)]">
            {item.total_versions_count}
          </span>
          {item.latest_published_at && (
            <>
              <span className="mx-1.5">·</span>
              Опубликована:{" "}
              {new Date(item.latest_published_at).toLocaleDateString(
                "ru-RU",
              )}
            </>
          )}
        </p>
      </div>
    </div>
  </button>
);

const TenantBaseGlobalChecksPage: React.FC = () => {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");

  const { data, isLoading, isError, refetch } =
    useBaseGlobalChecksCatalog();
  const items = data?.items ?? [];

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (item) =>
        item.instruction_code.toLowerCase().includes(q) ||
        item.name.toLowerCase().includes(q) ||
        (item.group?.toLowerCase().includes(q) ?? false),
    );
  }, [items, search]);

  const grouped = useMemo(() => {
    const map = new Map<string, GlobalInstructionCatalogItem[]>();
    for (const item of filtered) {
      const key = item.group ?? "Без группы";
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(item);
    }
    return Array.from(map.entries()).sort(([a], [b]) =>
      a.localeCompare(b, "ru"),
    );
  }, [filtered]);

  const publishedCount = items.filter((i) => i.has_published).length;

  return (
    <div className="h-full overflow-y-auto px-6 py-6 md:px-8 md:py-8">
      <div className="animate-fadein space-y-6">
        <button
          type="button"
          onClick={() => navigate("/tenant-admin/instructions")}
          className="flex shrink-0 items-center gap-1.5 text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)]"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Инструкции
        </button>

        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
              Базовые Global Instructions
            </h1>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              Read-only каталог базовых глобальных проверок платформы
            </p>
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void refetch()}
          >
            Обновить
          </Button>
        </header>

        {!isLoading && !isError && items.length > 0 && (
          <p className="text-sm text-[var(--text-muted)]">
            Всего:{" "}
            <span className="font-semibold text-[var(--text-primary)]">
              {items.length}
            </span>
            <span className="mx-1.5">·</span>
            Published:{" "}
            <span className="font-semibold text-[var(--text-primary)]">
              {publishedCount}
            </span>
            <span className="mx-1.5">·</span>
            Групп:{" "}
            <span className="font-semibold text-[var(--text-primary)]">
              {grouped.length}
            </span>
          </p>
        )}

        <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
          <p className="text-xs leading-5 text-[var(--text-secondary)]">
            Управляются superadmin. Нажмите на инструкцию, чтобы
            просмотреть её содержимое и версии. Для создания
            переопределений перейдите в{" "}
            <button
              type="button"
              onClick={() =>
                navigate(
                  "/tenant-admin/instructions/overrides?tab=global",
                )
              }
              className="font-semibold text-[var(--accent-primary)] hover:underline"
            >
              Global Overrides
            </button>
            .
          </p>
        </section>

        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Поиск по коду, названию, группе…"
          className="h-9 w-full rounded-xl border border-[var(--border)] bg-[var(--bg-input)] px-3 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none focus:ring-1 focus:ring-[var(--accent-primary)]"
        />

        {isLoading && (
          <LoadingBlock
            text="Загружаем базовые global instructions…"
            rows={6}
          />
        )}

        {isError && (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">
            Не удалось загрузить базовые global instructions.
          </div>
        )}

        {!isLoading && !isError && items.length === 0 && (
          <EmptyState
            title="Global instructions не найдены"
            description="Каталог базовых global instructions пока недоступен."
          />
        )}

        {!isLoading &&
          !isError &&
          items.length > 0 &&
          filtered.length === 0 && (
            <EmptyState
              title="Ничего не найдено"
              description="Попробуйте изменить поисковый запрос."
            />
          )}

        {!isLoading && !isError && filtered.length > 0 && (
          <div className="space-y-6">
            {grouped.map(([groupName, groupItems]) => (
              <div key={groupName}>
                <h2 className={`mb-3 ${sectionTitleCls}`}>
                  {groupName}{" "}
                  <span className="font-normal normal-case tracking-normal">
                    ({groupItems.length})
                  </span>
                </h2>
                <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                  {groupItems.map((item) => (
                    <CheckCard
                      key={item.instruction_code}
                      item={item}
                      onClick={() =>
                        navigate(
                          `/tenant-admin/instructions/base-global-checks/${item.instruction_code}`,
                        )
                      }
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default TenantBaseGlobalChecksPage;



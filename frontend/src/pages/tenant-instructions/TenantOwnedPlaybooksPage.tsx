// frontend/src/pages/tenant-instructions/TenantOwnedPlaybooksPage.tsx
//
// Каталог tenant-owned playbooks организации.
// Read-only listing — детальная работа с playbook происходит в Playbook Studio.

import React, { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, Layers, Plus } from "lucide-react";

import { useAuth } from "../../hooks/useAuth";
import {
  useTenantOwnedPlaybooks,
  type TenantPlaybookItem,
} from "../../api/tenantPlaybooks";
import LoadingBlock from "../../components/ui/LoadingBlock";
import EmptyState from "../../components/ui/EmptyState";
import InlineAlert from "../../components/InlineAlert";
import Button from "../../components/ui/Button";

const PlaybookCard: React.FC<{
  item: TenantPlaybookItem;
  onOpen: () => void;
}> = ({ item, onOpen }) => (
  <button
    type="button"
    onClick={onOpen}
    className="group w-full rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 text-left shadow-sm transition-all duration-200 hover:border-[var(--border-strong)] hover:shadow-md"
  >
    <div className="flex items-start gap-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-muted)]">
        <Layers
          className="h-4 w-4 text-[var(--accent-primary)]"
          aria-hidden="true"
        />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-[var(--text-primary)]">
          {item.title}
        </p>
        <p className="mt-0.5 font-mono text-[10px] text-[var(--text-muted)]">
          {item.code}
        </p>
        {item.description && (
          <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">
            {item.description}
          </p>
        )}
        <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-[var(--text-muted)]">
          {item.deal_type && <span>deal: {item.deal_type}</span>}
          {item.jurisdiction && <span>jurisdiction: {item.jurisdiction}</span>}
          {item.language && <span>language: {item.language}</span>}
          {item.risk_profile && <span>risk: {item.risk_profile}</span>}
        </div>
      </div>
    </div>
  </button>
);

const TenantOwnedPlaybooksPage: React.FC = () => {
  const navigate = useNavigate();
  const { tenantId } = useAuth();
  const [search, setSearch] = useState("");

  const { data, isLoading, isError, refetch } =
    useTenantOwnedPlaybooks(tenantId ?? null);

  const playbooks = data ?? [];

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return playbooks;
    return playbooks.filter(
      (p) =>
        p.title.toLowerCase().includes(q) ||
        p.code.toLowerCase().includes(q) ||
        (p.description?.toLowerCase().includes(q) ?? false) ||
        (p.deal_type?.toLowerCase().includes(q) ?? false),
    );
  }, [playbooks, search]);

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
              Playbooks организации
            </h1>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              Собственные playbooks вашего tenant. Видны только вам, не
              доступны другим клиентам платформы.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void refetch()}
            >
              Обновить
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() =>
                navigate("/tenant-admin/instructions/playbook-studio")
              }
              leftIcon={<Plus className="h-3.5 w-3.5" />}
            >
              Создать в Playbook Studio
            </Button>
          </div>
        </header>

        {!isLoading && !isError && playbooks.length > 0 && (
          <p className="text-sm text-[var(--text-muted)]">
            Всего:{" "}
            <span className="font-semibold text-[var(--text-primary)]">
              {playbooks.length}
            </span>
          </p>
        )}

        <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
          <p className="text-xs leading-5 text-[var(--text-secondary)]">
            Создание и редактирование playbooks выполняется в{" "}
            <button
              type="button"
              onClick={() =>
                navigate("/tenant-admin/instructions/playbook-studio")
              }
              className="font-semibold text-[var(--accent-primary)] hover:underline"
            >
              Playbook Studio
            </button>
            . Эта страница показывает готовый каталог только tenant-owned
            playbooks — глобальные шаблоны платформы здесь не отображаются.
          </p>
        </section>

        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Поиск по названию, коду, описанию…"
          className="h-9 w-full rounded-xl border border-[var(--border)] bg-[var(--bg-input)] px-3 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none focus:ring-1 focus:ring-[var(--accent-primary)]"
        />

        {isLoading && (
          <LoadingBlock text="Загружаем playbooks организации…" rows={6} />
        )}

        {isError && (
          <InlineAlert
            tone="error"
            message="Не удалось загрузить playbooks организации."
          />
        )}

        {!isLoading && !isError && playbooks.length === 0 && (
          <EmptyState
            title="Playbooks организации ещё не создан"
            description="Создайте первый playbook в Playbook Studio. Он будет виден только вашей организации."
            action={
              <Button
                variant="primary"
                size="sm"
                onClick={() =>
                  navigate("/tenant-admin/instructions/playbook-studio")
                }
                leftIcon={<Plus className="h-3.5 w-3.5" />}
              >
                Создать в Playbook Studio
              </Button>
            }
          />
        )}

        {!isLoading &&
          !isError &&
          playbooks.length > 0 &&
          filtered.length === 0 && (
            <EmptyState
              title="Ничего не найдено"
              description="Попробуйте изменить поисковый запрос."
            />
          )}

        {!isLoading && !isError && filtered.length > 0 && (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {filtered.map((item) => (
              <PlaybookCard
                key={item.id}
                item={item}
                onOpen={() =>
                  navigate(
                    `/tenant-admin/instructions/playbook-studio?playbook=${item.id}`,
                  )
                }
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default TenantOwnedPlaybooksPage;




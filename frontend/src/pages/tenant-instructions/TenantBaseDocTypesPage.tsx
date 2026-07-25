// frontend/src/pages/tenant-instructions/TenantBaseDocTypesPage.tsx

import React, { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  ChevronsDownUp,
  ChevronsUpDown,
  FileText,
  Minus,
  Plus,
} from "lucide-react";

import { useBaseDocTypeCatalog } from "../../api/baseInstructions";
import LoadingBlock from "../../components/ui/LoadingBlock";
import EmptyState from "../../components/ui/EmptyState";
import Button from "../../components/ui/Button";
import VersionStatusBadge from "../../components/instructions/VersionStatusBadge";
import type { InstructionCatalogItem } from "../../types/instructions";

// ─────────────────────────────────────────────────────────────
// Константы
// ─────────────────────────────────────────────────────────────

const UNGROUPED_KEY = "__ungrouped__";

function groupKeyOf(parent: string | null): string {
  return parent ?? UNGROUPED_KEY;
}

// ─────────────────────────────────────────────────────────────
// DocTypeCard
// ─────────────────────────────────────────────────────────────

const DocTypeCard: React.FC<{
  item: InstructionCatalogItem;
  onClick: () => void;
}> = ({ item, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    className="group w-full rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 text-left shadow-sm transition-all duration-200 hover:border-[var(--border-strong)] hover:shadow-md"
  >
    <div className="flex items-start gap-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-muted)]">
        <FileText
          className="h-4 w-4 text-[var(--accent-primary)]"
          aria-hidden="true"
        />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            {item.name}
          </p>
          {item.risk_level && (
            <span className="rounded-full border border-[var(--border)] bg-[var(--bg-elevated-soft)] px-1.5 py-0.5 text-[10px] text-[var(--text-muted)]">
              {item.risk_level}
            </span>
          )}
          {item.latest_version_status && (
            <VersionStatusBadge
              status={item.latest_version_status}
              size="xs"
            />
          )}
        </div>

        <p className="mt-1 font-mono text-[10px] text-[var(--text-muted)]">
          {item.doc_type_code}
        </p>

        <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-[var(--text-muted)]">
          {item.category && <span>category: {item.category}</span>}
          {item.language && <span>language: {item.language}</span>}
          {item.jurisdiction && (
            <span>jurisdiction: {item.jurisdiction}</span>
          )}
        </div>

        <p className="mt-2 text-[10px] text-[var(--text-muted)]">
          Версий:{" "}
          <span className="font-semibold text-[var(--text-primary)]">
            {item.total_versions_count}
          </span>
          {item.latest_published_at && (
            <>
              <span className="mx-1.5">·</span>
              Опубликована:{" "}
              {new Date(item.latest_published_at).toLocaleDateString("ru-RU")}
            </>
          )}
        </p>
      </div>
    </div>
  </button>
);

// ─────────────────────────────────────────────────────────────
// GroupSection
// ─────────────────────────────────────────────────────────────

interface GroupSectionProps {
  parent: string | null;
  items: InstructionCatalogItem[];
  isCollapsed: boolean;
  onToggle: () => void;
  onItemClick: (code: string) => void;
}

const GroupSection: React.FC<GroupSectionProps> = ({
  parent,
  items,
  isCollapsed,
  onToggle,
  onItemClick,
}) => {
  const displayName = parent ?? "Без группы";
  const groupId = `group-${groupKeyOf(parent)}`;

  return (
    <section className="space-y-3">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={!isCollapsed}
        aria-controls={groupId}
        className="group flex w-full items-center gap-2 border-b border-[var(--border-soft)] pb-2 text-left transition-colors hover:border-[var(--border)]"
      >
        <span
          className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-[var(--text-muted)] transition-colors group-hover:bg-[var(--bg-elevated-soft)] group-hover:text-[var(--text-primary)]"
          aria-hidden="true"
        >
          {isCollapsed ? (
            <Plus className="h-3.5 w-3.5" />
          ) : (
            <Minus className="h-3.5 w-3.5" />
          )}
        </span>

        <h2 className="flex-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)] transition-colors group-hover:text-[var(--text-primary)]">
          {displayName}
          <span className="ml-1.5 normal-case tracking-normal text-[var(--text-faint)]">
            · {items.length}
          </span>
        </h2>
      </button>

      {!isCollapsed && (
        <div id={groupId} className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {items.map((item) => (
            <DocTypeCard
              key={item.doc_type_code}
              item={item}
              onClick={() => onItemClick(item.doc_type_code)}
            />
          ))}
        </div>
      )}
    </section>
  );
};

// ─────────────────────────────────────────────────────────────
// TenantBaseDocTypesPage
// ─────────────────────────────────────────────────────────────

const TenantBaseDocTypesPage: React.FC = () => {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(
    () => new Set(),
  );

  const { data, isLoading, isError, refetch } = useBaseDocTypeCatalog();
  const items = data?.items ?? [];

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (item) =>
        item.doc_type_code.toLowerCase().includes(q) ||
        item.name.toLowerCase().includes(q) ||
        (item.parent?.toLowerCase().includes(q) ?? false) ||
        (item.category?.toLowerCase().includes(q) ?? false),
    );
  }, [items, search]);

  const grouped = useMemo(() => {
    const map = new Map<string | null, InstructionCatalogItem[]>();
    for (const item of filtered) {
      const key = item.parent ?? null;
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(item);
    }
    return Array.from(map.entries()).sort(([a], [b]) => {
      if (a === null) return 1;
      if (b === null) return -1;
      return a.localeCompare(b, "ru");
    });
  }, [filtered]);

  const handleItemClick = useCallback(
    (code: string) => {
      navigate(
        `/tenant-admin/instructions/base-doc-types/${code}`,
      );
    },
    [navigate],
  );

  const toggleGroup = useCallback((parent: string | null) => {
    const key = groupKeyOf(parent);
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }, []);

  const collapseAll = useCallback(() => {
    setCollapsedGroups(
      new Set(grouped.map(([parent]) => groupKeyOf(parent))),
    );
  }, [grouped]);

  const expandAll = useCallback(() => {
    setCollapsedGroups(new Set());
  }, []);

  const currentGroupKeys = useMemo(
    () => grouped.map(([parent]) => groupKeyOf(parent)),
    [grouped],
  );

  const allCollapsed =
    currentGroupKeys.length > 0 &&
    currentGroupKeys.every((key) => collapsedGroups.has(key));

  const hasMultipleGroups = grouped.length > 1;
  const publishedCount = items.filter((i) => i.has_published).length;
  const isSearching = search.trim().length > 0;

  return (
    <div className="h-full overflow-y-auto px-6 py-6 md:px-8 md:py-8">
      <div className="animate-fadein space-y-6">
        {/* Back */}
        <button
          type="button"
          onClick={() => navigate("/tenant-admin/instructions")}
          className="flex shrink-0 items-center gap-1.5 text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)]"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Инструкции
        </button>

        {/* Header */}
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
              Базовые Doc-Type Instructions
            </h1>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              Read-only каталог базовых инструкций по типам документов
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

        {/* Stats */}
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

        {/* Info */}
        <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
          <p className="text-xs leading-5 text-[var(--text-secondary)]">
            Управляются superadmin. Нажмите на инструкцию, чтобы просмотреть
            её содержимое и версии. Для создания переопределений перейдите в{" "}
            <button
              type="button"
              onClick={() =>
                navigate(
                  "/tenant-admin/instructions/overrides?tab=doc-type",
                )
              }
              className="font-semibold text-[var(--accent-primary)] hover:underline"
            >
              Doc-Type Overrides
            </button>
            .
          </p>
        </section>

        {/* Toolbar: поиск + свернуть/развернуть */}
        {!isLoading && !isError && items.length > 0 && (
          <div
            className={[
              "sticky -top-6 z-10 -mx-6 md:-top-8 md:-mx-8",
              "border-b border-[var(--border-soft)] bg-[var(--bg-surface)]/95",
              "px-6 py-3 backdrop-blur-sm md:px-8",
            ].join(" ")}
          >
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex flex-1 items-center gap-3">
                <input
                  type="search"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Поиск по коду, названию, parent, category…"
                  className="h-9 w-full rounded-xl border border-[var(--border)] bg-[var(--bg-input)] px-3 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none focus:ring-1 focus:ring-[var(--accent-primary)] sm:w-96"
                />

                {isSearching && (
                  <p className="hidden text-xs text-[var(--text-muted)] sm:block">
                    Найдено: {filtered.length} из {items.length}
                  </p>
                )}
              </div>

              {hasMultipleGroups && (
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  onClick={allCollapsed ? expandAll : collapseAll}
                  leftIcon={
                    allCollapsed ? (
                      <ChevronsUpDown className="h-3.5 w-3.5" />
                    ) : (
                      <ChevronsDownUp className="h-3.5 w-3.5" />
                    )
                  }
                >
                  {allCollapsed ? "Развернуть все" : "Свернуть все"}
                </Button>
              )}
            </div>

            {isSearching && (
              <p className="mt-2 text-xs text-[var(--text-muted)] sm:hidden">
                Найдено: {filtered.length} из {items.length}
              </p>
            )}
          </div>
        )}

        {/* States */}
        {isLoading && (
          <LoadingBlock
            text="Загружаем базовые doc-type instructions…"
            rows={6}
          />
        )}

        {isError && (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">
            Не удалось загрузить каталог doc-type instructions.
          </div>
        )}

        {!isLoading && !isError && items.length === 0 && (
          <EmptyState
            title="Doc-type instructions не найдены"
            description="Каталог базовых doc-type instructions пока недоступен."
          />
        )}

        {!isLoading && !isError && items.length > 0 && filtered.length === 0 && (
          <EmptyState
            title="Ничего не найдено"
            description="Попробуйте изменить поисковый запрос."
            action={
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setSearch("")}
              >
                Очистить поиск
              </Button>
            }
          />
        )}

        {/* Grouped list */}
        {!isLoading && !isError && filtered.length > 0 && (
          <div className="space-y-6">
            {grouped.map(([parent, groupItems]) => {
              const key = groupKeyOf(parent);
              return (
                <GroupSection
                  key={key}
                  parent={parent}
                  items={groupItems}
                  isCollapsed={collapsedGroups.has(key)}
                  onToggle={() => toggleGroup(parent)}
                  onItemClick={handleItemClick}
                />
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default TenantBaseDocTypesPage;



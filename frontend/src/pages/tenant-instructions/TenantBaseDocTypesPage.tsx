// frontend/src/pages/tenant-instructions/TenantBaseDocTypesPage.tsx

import React, { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  CheckCircle,
  ChevronsDownUp,
  ChevronsUpDown,
  Circle,
  FileText,
  Minus,
  Plus,
  RefreshCw,
  Search,
  X,
} from "lucide-react";

import { useBaseDocTypeCatalog } from "../../api/baseInstructions";
import LoadingBlock from "../../components/ui/LoadingBlock";
import EmptyState from "../../components/ui/EmptyState";
import Button from "../../components/ui/Button";
import VersionStatusBadge from "../../components/instructions/VersionStatusBadge";
import InlineAlert from "../../components/InlineAlert";
import type { InstructionCatalogItem } from "../../types/instructions";

// ─────────────────────────────────────────────────────────────
// Константы / утилиты
// ─────────────────────────────────────────────────────────────

const UNGROUPED_KEY = "__ungrouped__";

function groupKeyOf(parent: string | null): string {
  return parent ?? UNGROUPED_KEY;
}

function formatParentLabel(parent: string | null): string {
  if (parent === null) return "Без группы";
  return parent.replace(/_/g, " ");
}

function formatDate(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    return new Date(value).toLocaleDateString("ru-RU");
  } catch {
    return null;
  }
}

// ─────────────────────────────────────────────────────────────
// SearchInput
// ─────────────────────────────────────────────────────────────

interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

const SearchInput: React.FC<SearchInputProps> = ({
  value,
  onChange,
  placeholder = "Поиск…",
}) => (
  <div className="relative w-full sm:w-96">
    <Search
      className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]"
      aria-hidden="true"
    />
    <input
      type="search"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      autoComplete="off"
      className="w-full rounded-xl border border-[var(--border)] bg-[var(--bg-card)] py-2 pl-9 pr-9 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none transition-colors focus:border-[var(--accent-primary)] focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
    />
    {value.length > 0 && (
      <button
        type="button"
        onClick={() => onChange("")}
        aria-label="Очистить поиск"
        className="absolute right-2 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    )}
  </div>
);

// ─────────────────────────────────────────────────────────────
// DocTypeCard
// ─────────────────────────────────────────────────────────────

const DocTypeCard: React.FC<{
  item: InstructionCatalogItem;
  onClick: () => void;
}> = ({ item, onClick }) => {
  const publishedAt = formatDate(item.latest_published_at);

  return (
    <button
      type="button"
      onClick={onClick}
      className="group w-full rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 text-left shadow-sm transition-all duration-200 hover:border-[var(--border-strong)] hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)] transition-colors group-hover:bg-[var(--accent-muted)] group-hover:text-[var(--accent-primary)]">
            <FileText className="h-4 w-4" aria-hidden="true" />
          </div>

          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold text-[var(--text-primary)] transition-colors group-hover:text-[var(--accent-primary)]">
                {item.name}
              </span>

              {item.risk_level && (
                <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-1.5 py-0.5 text-[10px] text-[var(--text-muted)]">
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

            <div className="mt-0.5 font-mono text-[11px] text-[var(--text-muted)]">
              {item.doc_type_code}
            </div>

            {(item.category || item.language || item.jurisdiction) && (
              <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-[var(--text-muted)]">
                {item.category && <span>category: {item.category}</span>}
                {item.language && <span>language: {item.language}</span>}
                {item.jurisdiction && (
                  <span>jurisdiction: {item.jurisdiction}</span>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="flex shrink-0 flex-col items-end gap-1.5 text-[11px] text-[var(--text-muted)]">
          <span>
            {item.total_versions_count}{" "}
            {item.total_versions_count === 1 ? "версия" : "версий"}
          </span>

          <div className="flex items-center gap-1">
            {item.has_published ? (
              <CheckCircle
                className="h-3.5 w-3.5 text-[var(--color-success)]"
                aria-hidden="true"
              />
            ) : (
              <Circle
                className="h-3.5 w-3.5 text-[var(--text-muted)]"
                aria-hidden="true"
              />
            )}
            <span>{item.has_published ? "Published" : "Нет published"}</span>
          </div>

          {publishedAt && <span>{publishedAt}</span>}
        </div>
      </div>
    </button>
  );
};

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
  const displayName = formatParentLabel(parent);
  const groupId = `group-${groupKeyOf(parent)}`;

  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={!isCollapsed}
        aria-controls={groupId}
        className="group flex w-full items-start gap-3 rounded-xl text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
      >
        <span
          className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-[var(--text-muted)] transition-colors group-hover:bg-[var(--bg-elevated-soft)] group-hover:text-[var(--text-primary)]"
          aria-hidden="true"
        >
          {isCollapsed ? (
            <Plus className="h-3.5 w-3.5" />
          ) : (
            <Minus className="h-3.5 w-3.5" />
          )}
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)] transition-colors group-hover:text-[var(--text-primary)]">
              {displayName}
            </h2>
            <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-muted)]">
              {items.length}
            </span>
          </div>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">
            {isCollapsed
              ? "Раздел свёрнут"
              : "Нажмите на инструкцию, чтобы просмотреть её содержимое и версии."}
          </p>
        </div>
      </button>

      {!isCollapsed && (
        <div id={groupId} className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-2">
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
      navigate(`/tenant-admin/instructions/base-doc-types/${code}`);
    },
    [navigate],
  );

  const toggleGroup = useCallback((parent: string | null) => {
    const key = groupKeyOf(parent);
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const collapseAll = useCallback(() => {
    setCollapsedGroups(new Set(grouped.map(([parent]) => groupKeyOf(parent))));
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
    <div className="h-full overflow-y-auto overscroll-contain">
      <div className="animate-fadein space-y-4 p-4 md:p-5">

        {/* ── Шапка ───────────────────────────────────────────── */}
        <header className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <button
                type="button"
                onClick={() => navigate("/tenant-admin/instructions")}
                className="mb-3 inline-flex items-center gap-1.5 rounded-lg px-1 py-0.5 text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                Инструкции
              </button>

              <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
                Базовые Doc-Type Instructions
              </h1>
              <p className="mt-2 text-sm text-[var(--text-secondary)]">
                Read-only каталог базовых инструкций по типам документов.
              </p>

              {!isLoading && !isError && items.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2 text-[12px]">
                  <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-1 text-[var(--text-secondary)]">
                    Всего: {items.length}
                  </span>
                  <span className="rounded-full border border-[var(--color-success-border)] bg-[var(--color-success-bg)] px-3 py-1 text-[var(--color-success-text)]">
                    Published: {publishedCount}
                  </span>
                  <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-1 text-[var(--text-secondary)]">
                    Групп: {grouped.length}
                  </span>
                </div>
              )}
            </div>

            <Button
              variant="secondary"
              size="sm"
              onClick={() => void refetch()}
              leftIcon={<RefreshCw className="h-3.5 w-3.5" />}
            >
              Обновить
            </Button>
          </div>
        </header>

        {/* ── Инфо ────────────────────────────────────────────── */}
        <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 shadow-sm">
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
            Как использовать
          </div>
          <div className="mt-4 rounded-xl border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-4 py-3">
            <p className="text-sm leading-6 text-[var(--text-secondary)]">
              Базовые инструкции управляются superadmin. Нажмите на инструкцию,
              чтобы просмотреть её содержимое и версии. Для создания
              переопределений перейдите в{" "}
              <button
                type="button"
                onClick={() =>
                  navigate("/tenant-admin/instructions/overrides?tab=doc-type")
                }
                className="font-semibold text-[var(--accent-primary)] underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 rounded"
              >
                Doc-Type Overrides
              </button>
              .
            </p>
          </div>
        </section>

        {/* ── Toolbar ─────────────────────────────────────────── */}
        {!isLoading && !isError && items.length > 0 && (
          <div
            className={[
              "sticky -top-4 z-10 -mx-4 md:-top-5 md:-mx-5",
              "border-b border-[var(--border-soft)] bg-[var(--bg-surface)]/95",
              "px-4 py-3 backdrop-blur-sm md:px-5",
            ].join(" ")}
          >
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex flex-1 items-center gap-3">
                <SearchInput
                  value={search}
                  onChange={setSearch}
                  placeholder="Поиск по коду, названию, parent, category…"
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

        {/* ── States ──────────────────────────────────────────── */}
        {isLoading && (
          <LoadingBlock
            text="Загружаем базовые doc-type instructions…"
            rows={6}
          />
        )}

        {isError && (
          <InlineAlert
            tone="error"
            message="Не удалось загрузить каталог doc-type instructions."
          />
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

        {/* ── Grouped list ────────────────────────────────────── */}
        {!isLoading && !isError && filtered.length > 0 && (
          <div className="space-y-4">
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



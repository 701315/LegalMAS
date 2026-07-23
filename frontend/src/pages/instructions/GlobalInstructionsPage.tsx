// src/pages/instructions/GlobalInstructionsPage.tsx
// Каталог global instructions с группировкой по group.
// Зеркало DocTypeInstructionsPage.

import React, { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Shield,
  RefreshCw,
  AlertTriangle,
  CheckCircle,
  Circle,
  Search,
  X,
  ArrowLeft,
  Plus,
  Minus,
  ChevronsDownUp,
  ChevronsUpDown,
} from "lucide-react";

import { useGlobalInstructionCatalog } from "../../hooks/instructions/useGlobalInstructions";
import InstructionPageHeader from "../../components/instructions/InstructionPageHeader";
import VersionStatusBadge from "../../components/instructions/VersionStatusBadge";
import LoadingBlock from "../../components/ui/LoadingBlock";
import EmptyState from "../../components/ui/EmptyState";
import InlineAlert from "../../components/InlineAlert";
import Button from "../../components/ui/Button";
import type { GlobalInstructionCatalogItem } from "../../types/instructions";

// ─────────────────────────────────────────────────────────────
// Группировка
// ─────────────────────────────────────────────────────────────

const UNGROUPED_KEY = "__ungrouped__";

function groupKeyOf(groupName: string | null): string {
  return groupName ?? UNGROUPED_KEY;
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
      spellCheck={false}
      className={[
        "w-full rounded-xl border border-[var(--border)] bg-[var(--bg-card)]",
        "py-2 pl-9 pr-9 text-sm text-[var(--text-primary)]",
        "outline-none transition-colors",
        "placeholder:text-[var(--text-muted)]",
        "focus:border-[var(--accent-primary)]",
      ].join(" ")}
    />
    {value.length > 0 && (
      <button
        type="button"
        onClick={() => onChange("")}
        aria-label="Очистить поиск"
        className="absolute right-2 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--text-secondary)]"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    )}
  </div>
);

// ─────────────────────────────────────────────────────────────
// GlobalCatalogItemCard
// ─────────────────────────────────────────────────────────────

interface GlobalCatalogItemCardProps {
  item: GlobalInstructionCatalogItem;
  onClick: () => void;
}

const GlobalCatalogItemCard: React.FC<GlobalCatalogItemCardProps> = ({
  item,
  onClick,
}) => {
  const hasPublished = item.has_published;
  const hasDraft = item.latest_draft_version_id !== null;
  const draftIsInvalid = hasDraft && item.latest_draft_is_valid === false;
  const latestStatus = item.latest_version_status;

  return (
    <button
      type="button"
      onClick={onClick}
      className="group w-full rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 text-left shadow-sm transition-all duration-200 hover:border-[var(--border-strong)] hover:shadow-md"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)] transition-colors group-hover:bg-[var(--accent-muted)] group-hover:text-[var(--accent-primary)]">
            <Shield className="h-4 w-4" aria-hidden="true" />
          </div>

          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold text-[var(--text-primary)] transition-colors group-hover:text-[var(--accent-primary)]">
                {item.name}
              </span>
              {latestStatus && (
                <VersionStatusBadge status={latestStatus} size="xs" />
              )}
            </div>

            <div className="mt-0.5 font-mono text-[11px] text-[var(--text-muted)]">
              {item.instruction_code}
            </div>
          </div>
        </div>

        <div className="flex shrink-0 flex-col items-end gap-1.5 text-[11px] text-[var(--text-muted)]">
          <span>
            {item.total_versions_count}{" "}
            {item.total_versions_count === 1 ? "версия" : "версий"}
          </span>

          <div className="flex items-center gap-1">
            {hasPublished ? (
              <CheckCircle
                className="h-3.5 w-3.5 text-[color:var(--color-success-text)]"
                aria-hidden="true"
              />
            ) : (
              <Circle
                className="h-3.5 w-3.5 text-[var(--text-muted)]"
                aria-hidden="true"
              />
            )}
            <span>{hasPublished ? "Published" : "Нет published"}</span>
          </div>

          {hasDraft && (
            <div className="flex items-center gap-1">
              {draftIsInvalid ? (
                <AlertTriangle
                  className="h-3.5 w-3.5 text-[color:var(--color-warning-text,#92400e)]"
                  aria-hidden="true"
                />
              ) : (
                <Circle
                  className="h-3.5 w-3.5 text-[color:var(--color-warning-text,#92400e)]"
                  aria-hidden="true"
                />
              )}
              <span>{draftIsInvalid ? "Черновик (invalid)" : "Черновик"}</span>
            </div>
          )}
        </div>
      </div>
    </button>
  );
};

// ─────────────────────────────────────────────────────────────
// GroupSection
// ─────────────────────────────────────────────────────────────

interface GroupSectionProps {
  groupName: string | null;
  items: GlobalInstructionCatalogItem[];
  isCollapsed: boolean;
  onToggle: () => void;
  onItemClick: (instructionCode: string) => void;
}

const GroupSection: React.FC<GroupSectionProps> = ({
  groupName,
  items,
  isCollapsed,
  onToggle,
  onItemClick,
}) => {
  const displayName = groupName ?? "Без группы";
  const groupId = `group-${groupKeyOf(groupName)}`;

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
        <div id={groupId} className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          {items.map((item) => (
            <GlobalCatalogItemCard
              key={item.instruction_code}
              item={item}
              onClick={() => onItemClick(item.instruction_code)}
            />
          ))}
        </div>
      )}
    </section>
  );
};

// ─────────────────────────────────────────────────────────────
// GlobalInstructionsPage
// ─────────────────────────────────────────────────────────────

const GlobalInstructionsPage: React.FC = () => {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");

  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(
    () => new Set(),
  );

  const {
    data: catalog,
    isLoading,
    isError,
    refetch,
  } = useGlobalInstructionCatalog();

  const items = catalog?.items ?? [];

  const filteredItems = useMemo(() => {
    if (!search.trim()) {
      return items;
    }

    const q = search.trim().toLowerCase();

    return items.filter(
      (item) =>
        item.instruction_code.toLowerCase().includes(q) ||
        item.name.toLowerCase().includes(q) ||
        (item.group?.toLowerCase().includes(q) ?? false),
    );
  }, [items, search]);

  const groupedItems = useMemo(() => {
    const groups = new Map<string | null, GlobalInstructionCatalogItem[]>();

    for (const item of filteredItems) {
      const key = item.group ?? null;
      if (!groups.has(key)) {
        groups.set(key, []);
      }
      groups.get(key)!.push(item);
    }

    return Array.from(groups.entries()).sort(([a], [b]) => {
      if (a === null) return 1;
      if (b === null) return -1;
      return a.localeCompare(b, "ru");
    });
  }, [filteredItems]);

  const handleOpen = useCallback(
    (instructionCode: string) => {
      navigate(`/admin/instructions/global-checks/${instructionCode}`);
    },
    [navigate],
  );

  const toggleGroup = useCallback((groupName: string | null) => {
    const key = groupKeyOf(groupName);
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
    const allKeys = groupedItems.map(([groupName]) => groupKeyOf(groupName));
    setCollapsedGroups(new Set(allKeys));
  }, [groupedItems]);

  const expandAll = useCallback(() => {
    setCollapsedGroups(new Set());
  }, []);

  const totalCount = items.length;
  const publishedCount = items.filter((i) => i.has_published).length;
  const draftCount = items.filter(
    (i) => i.latest_draft_version_id !== null,
  ).length;

  const isSearching = search.trim().length > 0;
  const filteredCount = filteredItems.length;
  const hasMultipleGroups = groupedItems.length > 1;

  const currentGroupKeys = useMemo(
    () => groupedItems.map(([groupName]) => groupKeyOf(groupName)),
    [groupedItems],
  );

  const allCollapsed =
    currentGroupKeys.length > 0 &&
    currentGroupKeys.every((key) => collapsedGroups.has(key));

  return (
    <div className="h-full overflow-y-auto px-6 py-6 md:px-8 md:py-8">
      <div className="animate-fadein space-y-6">
        <button
          type="button"
          onClick={() => navigate("/admin/instructions")}
          className="flex shrink-0 items-center gap-1.5 text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)]"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Инструкции
        </button>

        <InstructionPageHeader
          breadcrumbs={[
            { label: "Admin", to: "/admin" },
            { label: "Инструкции", to: "/admin/instructions" },
            { label: "Global Instructions" },
          ]}
          title="Global Instructions"
          subtitle="Универсальные проверки, применимые к любому типу документа. Выберите инструкцию для управления версиями."
          rightSlot={
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void refetch()}
              leftIcon={<RefreshCw className="h-3.5 w-3.5" />}
            >
              Обновить
            </Button>
          }
        />

        {!isLoading && !isError && totalCount > 0 && (
          <p className="text-sm text-[var(--text-muted)]">
            Всего:{" "}
            <span className="font-semibold text-[var(--text-primary)]">
              {totalCount}
            </span>
            <span className="mx-1.5">·</span>
            Published:{" "}
            <span className="font-semibold text-[color:var(--color-success-text)]">
              {publishedCount}
            </span>
            <span className="mx-1.5">·</span>
            С черновиком:{" "}
            <span className="font-semibold text-[var(--text-primary)]">
              {draftCount}
            </span>
          </p>
        )}

        {!isLoading && !isError && totalCount > 0 && (
          <div
            className={[
              "sticky -top-6 z-10 -mx-6 md:-top-8 md:-mx-8",
              "border-b border-[var(--border-soft)] bg-[var(--bg-surface)]/95",
              "px-6 py-3 backdrop-blur-sm md:px-8",
            ].join(" ")}
          >
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex flex-1 items-center gap-3">
                <SearchInput
                  value={search}
                  onChange={setSearch}
                  placeholder="Поиск по коду, названию или группе…"
                />

                {isSearching && (
                  <p className="hidden text-xs text-[var(--text-muted)] sm:block">
                    Найдено: {filteredCount} из {totalCount}
                  </p>
                )}
              </div>

              {hasMultipleGroups && (
                <div className="flex items-center">
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
                </div>
              )}
            </div>

            {isSearching && (
              <p className="mt-2 text-xs text-[var(--text-muted)] sm:hidden">
                Найдено: {filteredCount} из {totalCount}
              </p>
            )}
          </div>
        )}

        {isLoading && (
          <LoadingBlock
            text="Загружаем каталог global instructions…"
            rows={6}
          />
        )}

        {isError && (
          <InlineAlert
            tone="error"
            message="Не удалось загрузить каталог global instructions."
          />
        )}

        {!isLoading && !isError && items.length === 0 && (
          <EmptyState
            title="Global instructions не найдены"
            description="Каталог пуст. Создайте первую global instruction или обратитесь к администратору."
          />
        )}

        {!isLoading &&
          !isError &&
          items.length > 0 &&
          filteredItems.length === 0 && (
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

        {!isLoading && !isError && filteredItems.length > 0 && (
          <div className="space-y-6">
            {groupedItems.map(([groupName, groupItems]) => {
              const key = groupKeyOf(groupName);

              return (
                <GroupSection
                  key={key}
                  groupName={groupName}
                  items={groupItems}
                  isCollapsed={collapsedGroups.has(key)}
                  onToggle={() => toggleGroup(groupName)}
                  onItemClick={handleOpen}
                />
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default GlobalInstructionsPage;



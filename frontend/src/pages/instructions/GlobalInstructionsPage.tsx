// src/pages/instructions/GlobalInstructionsPage.tsx
// Каталог global instructions с группировкой по group.
// Зеркало DocTypeInstructionsPage.

import React, { useCallback, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Shield,
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

import {
  useGlobalInstructionCatalog,
  useCreateGlobalInstructionDraft,
} from "../../hooks/instructions/useGlobalInstructions";
import VersionStatusBadge from "../../components/instructions/VersionStatusBadge";
import LoadingBlock from "../../components/ui/LoadingBlock";
import EmptyState from "../../components/ui/EmptyState";
import InlineAlert from "../../components/InlineAlert";
import Button from "../../components/ui/Button";
import ImportYamlDialog, {
  type ImportYamlSubmitPayload,
} from "../../components/instructions/ImportYamlDialog";
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
        "focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35",
        "focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]",
      ].join(" ")}
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
      className="group w-full rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-5 text-left shadow-sm transition-all duration-200 hover:border-[var(--border-strong)] hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
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
                className="h-3.5 w-3.5 text-[var(--color-success)]"
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
                  className="h-3.5 w-3.5 text-[var(--color-warning-text)]"
                  aria-hidden="true"
                />
              ) : (
                <Circle
                  className="h-3.5 w-3.5 text-[var(--color-warning-text)]"
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
              : "Выберите инструкцию для просмотра версий и управления черновиками."}
          </p>
        </div>
      </button>

      {!isCollapsed && (
        <div
          id={groupId}
          className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-2"
        >
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

  const [isImportOpen, setIsImportOpen] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const createDraft = useCreateGlobalInstructionDraft();

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

  const handleImportOpen = useCallback(() => {
    setImportError(null);
    setIsImportOpen(true);
  }, []);

  const handleImportCancel = useCallback(() => {
    setIsImportOpen(false);
    setImportError(null);
  }, []);

  const handleImportSubmit = useCallback(
    async (payload: ImportYamlSubmitPayload) => {
      setImportError(null);
      try {
        const newDraft = await createDraft.mutateAsync({
          instructionCode: payload.code,
          body: {
            source_yaml: payload.sourceYaml,
            name: payload.name,
            change_summary: "Импорт из YAML",
          },
        });
        setIsImportOpen(false);
        await refetch();
        navigate(
          `/admin/instructions/global-checks/${payload.code}?version=${encodeURIComponent(newDraft.id)}`,
        );
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Не удалось импортировать YAML.";
        setImportError(message);
      }
    },
    [createDraft, navigate, refetch],
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
    <div className="h-full overflow-y-auto overscroll-contain">
      <div className="animate-fadein space-y-4 p-4 md:p-5">
        <header className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-5 py-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <button
                type="button"
                onClick={() => navigate("/admin/instructions")}
                className="mb-3 inline-flex items-center gap-1.5 rounded-lg px-1 py-0.5 text-xs text-[var(--text-muted)] transition-colors hover:text-[var(--text-secondary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                Инструкции
              </button>

              <h1 className="text-xl font-semibold tracking-tight text-[var(--text-primary)]">
                Global Instructions
              </h1>
              <p className="mt-2 text-sm text-[var(--text-secondary)]">
                Универсальные проверки, применимые к любому типу документа.
                Выберите инструкцию для управления версиями.
              </p>

              {!isLoading && !isError && totalCount > 0 && (
                <div className="mt-3 flex flex-wrap gap-2 text-[12px]">
                  <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-1 text-[var(--text-secondary)]">
                    Всего: {totalCount}
                  </span>
                  <span className="rounded-full border border-[var(--color-success-border)] bg-[var(--color-success-bg)] px-3 py-1 text-[var(--color-success-text)]">
                    Published: {publishedCount}
                  </span>
                  <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-1 text-[var(--text-secondary)]">
                    С черновиком: {draftCount}
                  </span>
                </div>
              )}
            </div>

            <Button
              variant="primary"
              size="sm"
              onClick={handleImportOpen}
              leftIcon={<Plus className="h-3.5 w-3.5" />}
            >
              Добавить инструкцию
            </Button>
          </div>
        </header>

        {!isLoading && !isError && totalCount > 0 && (
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
          <div className="space-y-4">
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

      <ImportYamlDialog
        open={isImportOpen}
        kind="global"
        isSubmitting={createDraft.isPending}
        submitError={importError}
        onCancel={handleImportCancel}
        onSubmit={handleImportSubmit}
      />
    </div>
  );
};

export default GlobalInstructionsPage;



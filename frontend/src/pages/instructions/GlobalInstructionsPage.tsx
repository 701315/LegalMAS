// src/pages/instructions/GlobalInstructionsPage.tsx
// Каталог global instructions с группировкой по group.
// Зеркало DocTypeInstructionsPage.

import React, { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Shield,
  RefreshCw,
  AlertTriangle,
  CheckCircle,
  Circle,
} from "lucide-react";

import { useGlobalInstructionCatalog } from "../../hooks/instructions/useGlobalInstructions";
import InstructionPageHeader from "../../components/instructions/InstructionPageHeader";
import VersionStatusBadge from "../../components/instructions/VersionStatusBadge";
import LoadingBlock from "../../components/ui/LoadingBlock";
import EmptyState from "../../components/ui/EmptyState";
import InlineAlert from "../../components/InlineAlert";
import Button from "../../components/ui/Button";
import type { GlobalInstructionCatalogItem } from "../../types/instructions";

type FilterMode = "all" | "has_draft" | "no_published";

const FILTER_LABELS: Record<FilterMode, string> = {
  all: "Все",
  has_draft: "Есть черновик",
  no_published: "Нет published",
};

// ── Карточка одного global instruction ────────────────────────

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
  const draftIsValid = item.latest_draft_is_valid;
  const latestStatus = item.latest_version_status;

  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3 text-left text-xs transition-colors hover:border-[var(--accent-primary)]/30 hover:bg-[var(--bg-elevated-soft)]"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-1 items-start gap-2.5">
          <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-muted)]">
            <Shield
              className="h-4 w-4 text-[var(--accent-primary)]"
              aria-hidden="true"
            />
          </div>

          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-semibold text-[var(--text-primary)]">
                {item.name}
              </span>
              {latestStatus && (
                <VersionStatusBadge status={latestStatus} size="xs" />
              )}
            </div>

            <div className="mt-0.5 font-mono text-[10px] text-[var(--text-muted)]">
              {item.instruction_code}
            </div>

            {item.group && (
              <div className="mt-1.5">
                <span className="rounded border border-[var(--border)] bg-[var(--bg-elevated-soft)] px-1.5 py-0.5 text-[10px] text-[var(--text-muted)]">
                  {item.group}
                </span>
              </div>
            )}
          </div>
        </div>

        <div className="shrink-0 flex flex-col items-end gap-1.5">
          <span className="text-[11px] text-[var(--text-muted)]">
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
            <span className="text-[10px] text-[var(--text-muted)]">
              {hasPublished ? "Published" : "No published"}
            </span>
          </div>

          {hasDraft && (
            <div className="flex items-center gap-1">
              {draftIsValid === false ? (
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
              <span className="text-[10px] text-[var(--text-muted)]">
                {draftIsValid === false ? "Draft (invalid)" : "Draft"}
              </span>
            </div>
          )}
        </div>
      </div>
    </button>
  );
};

// ── Группа ────────────────────────────────────────────────────

interface GroupSectionProps {
  groupName: string | null;
  items: GlobalInstructionCatalogItem[];
  onItemClick: (instructionCode: string) => void;
}

const GroupSection: React.FC<GroupSectionProps> = ({
  groupName,
  items,
  onItemClick,
}) => (
  <div>
    <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
      {groupName ?? "Без группы"} ({items.length})
    </div>
    <ul className="space-y-1.5">
      {items.map((item) => (
        <li key={item.instruction_code}>
          <GlobalCatalogItemCard
            item={item}
            onClick={() => onItemClick(item.instruction_code)}
          />
        </li>
      ))}
    </ul>
  </div>
);

// ── Главная страница ───────────────────────────────────────────

const GlobalInstructionsPage: React.FC = () => {
  const navigate = useNavigate();
  const [filterMode, setFilterMode] = useState<FilterMode>("all");
  const [search, setSearch] = useState("");

  const {
    data: catalog,
    isLoading,
    isError,
    refetch,
  } = useGlobalInstructionCatalog();

  const items = catalog?.items ?? [];

  const filteredItems = useMemo(() => {
    let result = items;

    if (search.trim()) {
      const q = search.trim().toLowerCase();
      result = result.filter(
        (item) =>
          item.instruction_code.toLowerCase().includes(q) ||
          item.name.toLowerCase().includes(q) ||
          (item.group?.toLowerCase().includes(q) ?? false),
      );
    }

    if (filterMode === "has_draft") {
      result = result.filter((item) => item.latest_draft_version_id !== null);
    } else if (filterMode === "no_published") {
      result = result.filter((item) => !item.has_published);
    }

    return result;
  }, [items, search, filterMode]);

  // Группируем по group для отображения
  const groupedItems = useMemo(() => {
    const groups = new Map<string | null, GlobalInstructionCatalogItem[]>();
    for (const item of filteredItems) {
      const key = item.group ?? null;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(item);
    }
    // Сортировка: named groups сначала (алфавит), null last
    return Array.from(groups.entries()).sort(([a], [b]) => {
      if (a === null) return 1;
      if (b === null) return -1;
      return a.localeCompare(b);
    });
  }, [filteredItems]);

  const handleOpen = (instructionCode: string) => {
    navigate(`/admin/instructions/global-checks/${instructionCode}`);
  };

  const totalCount = items.length;
  const publishedCount = items.filter((i) => i.has_published).length;
  const draftCount = items.filter(
    (i) => i.latest_draft_version_id !== null,
  ).length;

  return (
    <div className="h-full overflow-y-auto bg-[var(--bg-base)]">
      <div className="mx-auto max-w-5xl space-y-4 px-4 py-6">
        <InstructionPageHeader
          breadcrumbs={[
            { label: "Admin", to: "/admin" },
            { label: "Инструкции", to: "/admin/instructions" },
            { label: "Global Instructions" },
          ]}
          title="Global Instructions"
          subtitle="Проверки, применимые к любому типу документа. Выберите инструкцию для управления версиями."
          rightSlot={
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void refetch()}
              aria-label="Обновить каталог"
            >
              <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            </Button>
          }
        />

        {!isLoading && !isError && totalCount > 0 && (
          <div className="flex items-center gap-4 rounded-xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-2.5">
            <div className="text-[11px] text-[var(--text-muted)]">
              Всего:{" "}
              <span className="font-semibold text-[var(--text-primary)]">
                {totalCount}
              </span>
            </div>
            <div className="h-3 w-px bg-[var(--border)]" aria-hidden="true" />
            <div className="text-[11px] text-[var(--text-muted)]">
              Published:{" "}
              <span className="font-semibold text-[color:var(--color-success-text)]">
                {publishedCount}
              </span>
            </div>
            <div className="h-3 w-px bg-[var(--border)]" aria-hidden="true" />
            <div className="text-[11px] text-[var(--text-muted)]">
              С черновиком:{" "}
              <span className="font-semibold text-[var(--text-primary)]">
                {draftCount}
              </span>
            </div>
          </div>
        )}

        {!isLoading && !isError && totalCount > 0 && (
          <div className="flex items-center gap-2 flex-wrap">
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Поиск по коду, названию или группе..."
              className="h-8 min-w-[200px] flex-1 rounded-lg border border-[var(--border)] bg-[var(--bg-input)] px-3 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-primary)]"
            />
            <div className="flex items-center gap-1 rounded-lg border border-[var(--border)] bg-[var(--bg-card)] p-0.5">
              {(["all", "has_draft", "no_published"] as FilterMode[]).map(
                (mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => setFilterMode(mode)}
                    className={[
                      "rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors",
                      filterMode === mode
                        ? "bg-[var(--accent-muted)] text-[var(--accent-primary)]"
                        : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
                    ].join(" ")}
                  >
                    {FILTER_LABELS[mode]}
                  </button>
                ),
              )}
            </div>
          </div>
        )}

        {isLoading && (
          <LoadingBlock text="Загружаем каталог global instructions..." rows={6} />
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

        {!isLoading && !isError && items.length > 0 && filteredItems.length === 0 && (
          <EmptyState
            title="Ничего не найдено"
            description="Попробуйте изменить поисковый запрос или сбросить фильтр."
            action={
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  setSearch("");
                  setFilterMode("all");
                }}
              >
                Сбросить фильтр
              </Button>
            }
          />
        )}

        {!isLoading && !isError && filteredItems.length > 0 && (
          <div className="space-y-6">
            {groupedItems.map(([groupName, groupItems]) => (
              <GroupSection
                key={groupName ?? "__ungrouped__"}
                groupName={groupName}
                items={groupItems}
                onItemClick={handleOpen}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default GlobalInstructionsPage;



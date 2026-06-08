// =============================================================
// src/components/requests/RequestsTable.tsx
// Таблица DD-запросов для юриста (legacy CRUD mode).
// Использует adapter для преобразования DDRequest в UI read-model.
// Колонки: Приоритет, Текст, Документы (count), Статус, Источник.
// Поиск, сортировка, кнопки экспорта.
// =============================================================

import React, { useMemo, useState, useRef } from "react";
import type { DDRequest } from "../../types";
import { toRequestTableRowFromLegacy } from "../../viewAdapters/requestPresentation";
import { RequestPriorityBadge } from "./shared/RequestPriorityBadge";
import { Search, Plus, Download, FileText } from "lucide-react";
import Button from "../ui/Button";
import { REQUEST_PRIORITY_ORDER } from "../../types/requestPriority";

interface Props {
  requests: DDRequest[];
  selectedRequestId?: string | null;
  onRowClick: (request: DDRequest, rowElement: HTMLElement | null) => void;
  onCreateClick: () => void;
  onExportWord: () => Promise<void>;
  onExportExcel: () => Promise<void>;
  canManageRequests: boolean;
}

type SortKey = "priority" | "status" | "created";

function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

const statusToneClass = (statusLabel?: string | null): string => {
  if (!statusLabel) {
    return "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-muted)]";
  }

  const value = statusLabel.toLowerCase();

  if (value.includes("open") || value.includes("открыт")) {
    return "border-[color:color-mix(in_oklab,var(--color-blue)_22%,transparent)] bg-[var(--color-blue-highlight)] text-[var(--color-blue)]";
  }

  if (
    value.includes("progress") ||
    value.includes("работ") ||
    value.includes("processing")
  ) {
    return "border-[color:color-mix(in_oklab,var(--color-orange)_22%,transparent)] bg-[var(--color-orange-highlight)] text-[var(--color-orange)]";
  }

  if (
    value.includes("resolved") ||
    value.includes("done") ||
    value.includes("закрыт")
  ) {
    return "border-[color:color-mix(in_oklab,var(--color-success)_22%,transparent)] bg-[var(--color-success-highlight)] text-[var(--color-success)]";
  }

  return "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)]";
};

export const RequestsTable: React.FC<Props> = ({
  requests,
  selectedRequestId,
  onRowClick,
  onCreateClick,
  onExportWord,
  onExportExcel,
  canManageRequests,
}) => {
  const [searchText, setSearchText] = useState("");
  const [sortBy, setSortBy] = useState<SortKey>("priority");

  // Один ref на компонент: Map от id строки к её DOM-элементу.
  // Регистрация/разрегистрация происходит через ref-callback на <tr>.
  const rowRefs = useRef<Map<string, HTMLTableRowElement>>(new Map());

  const viewModels = useMemo(
    () =>
      requests.map((req) => ({
        dto: req,
        view: toRequestTableRowFromLegacy(req),
      })),
    [requests],
  );

  const filtered = useMemo(() => {
    let list = [...viewModels];

    if (searchText.trim()) {
      const lower = searchText.toLowerCase();
      list = list.filter((item) => {
        const { view } = item;
        const text = view.text.toLowerCase();
        const checkLabel = view.checkLabel?.toLowerCase() ?? "";
        return text.includes(lower) || checkLabel.includes(lower);
      });
    }

    list.sort((a, b) => {
      if (sortBy === "priority") {
        return (
          (REQUEST_PRIORITY_ORDER[a.view.priority] ?? 9) -
          (REQUEST_PRIORITY_ORDER[b.view.priority] ?? 9)
        );
      }

      if (sortBy === "status") {
        return (a.view.statusLabel ?? "").localeCompare(
          b.view.statusLabel ?? "",
          "ru",
        );
      }

      return (
        new Date(b.dto.created_at).getTime() -
        new Date(a.dto.created_at).getTime()
      );
    });

    return list;
  }, [viewModels, searchText, sortBy]);

  return (
    <section
      className="flex h-full min-h-0 flex-col gap-3 overflow-hidden"
      aria-labelledby="requests-table-title"
    >
      {/* Шапка */}
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
            Requests
          </p>
          <h2
            id="requests-table-title"
            className="mt-1 text-sm font-semibold text-[var(--text-primary)]"
          >
            Запросы
            <span className="ml-1 text-[var(--text-muted)]">
              ({requests.length})
            </span>
          </h2>
        </div>

        <div className="flex flex-wrap gap-2">
          {canManageRequests && (
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={onCreateClick}
              leftIcon={<Plus className="h-4 w-4" />}
            >
              Новый запрос
            </Button>
          )}

          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={onExportWord}
            leftIcon={<FileText className="h-4 w-4" />}
          >
            Word
          </Button>

          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={onExportExcel}
            leftIcon={<Download className="h-4 w-4" />}
          >
            Excel
          </Button>
        </div>
      </div>

      {/* Поиск */}
      <div className="relative shrink-0">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
          size={16}
          aria-hidden="true"
        />
        <input
          type="text"
          placeholder="Поиск по тексту запроса или ID проверки…"
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          className="mt-1 w-full rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-9 py-2 text-sm text-[var(--text-primary)] outline-none transition placeholder:text-[var(--text-muted)] focus:border-[var(--accent-primary)]"
          aria-label="Поиск по DD-запросам"
        />
      </div>

      {/* Таблица */}
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)]">
        <div className="min-h-0 flex-1 overflow-auto">
          <table className="w-full border-collapse text-left">
            <thead className="border-b border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)]/60">
              <tr>
                {(
                  [
                    ["priority", "Приоритет", "w-28"],
                    ["text", "Текст запроса", ""],
                    ["docs", "Документы", "w-28"],
                    ["status", "Статус", "w-32"],
                    ["source", "Источник", "w-40"],
                  ] as const
                ).map(([key, label, width]) => (
                  <th
                    key={key}
                    scope="col"
                    className={cn(
                      "px-3 py-2.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]",
                      width,
                    )}
                  >
                    {key === "priority" || key === "status" ? (
                      <button
                        type="button"
                        onClick={() => setSortBy(key as SortKey)}
                        className={cn(
                          "inline-flex items-center gap-1 transition-colors hover:text-[var(--text-secondary)]",
                          sortBy === key &&
                            "text-[var(--accent-primary)] underline underline-offset-4",
                        )}
                      >
                        <span>{label}</span>
                      </button>
                    ) : (
                      label
                    )}
                  </th>
                ))}
              </tr>
            </thead>

            <tbody>
              {filtered.map((item) => {
                const { dto, view } = item;
                const isSelected = selectedRequestId === view.id;

                return (
                  <tr
                    key={view.id}
                    ref={(el) => {
                      if (el) {
                        rowRefs.current.set(view.id, el);
                      } else {
                        rowRefs.current.delete(view.id);
                      }
                    }}
                    className={cn(
                      "cursor-pointer border-b border-[var(--border-subtle)] transition-colors last:border-b-0",
                      isSelected
                        ? "bg-[var(--bg-elevated-soft)]"
                        : "hover:bg-[var(--bg-elevated-soft)]/60",
                    )}
                    onClick={() =>
                      onRowClick(dto, rowRefs.current.get(view.id) ?? null)
                    }
                    aria-selected={isSelected}
                  >
                    {/* Приоритет */}
                    <td
                      className={cn(
                        "px-3 py-2.5 align-top",
                        isSelected &&
                          "shadow-[inset_3px_0_0_var(--accent-primary)]",
                      )}
                    >
                      <RequestPriorityBadge priority={view.priority} size="sm" />
                    </td>

                    {/* Текст */}
                    <td className="px-3 py-2.5 align-top">
                      <p className="line-clamp-2 text-sm text-[var(--text-primary)]">
                        {view.text}
                      </p>
                      {view.checkLabel && (
                        <p className="mt-0.5 text-[12px] text-[var(--text-muted)]">
                          Проверка: {view.checkLabel}
                        </p>
                      )}
                    </td>

                    {/* Документы */}
                    <td className="px-3 py-2.5 align-top text-sm text-[var(--text-secondary)]">
                      {view.documentCount} док.
                    </td>

                    {/* Статус */}
                    <td className="px-3 py-2.5 align-top">
                      {view.statusLabel ? (
                        <span
                          className={cn(
                            "inline-flex max-w-full items-center rounded-full border px-2 py-0.5 text-xs font-medium",
                            statusToneClass(view.statusLabel),
                          )}
                        >
                          <span className="truncate">{view.statusLabel}</span>
                        </span>
                      ) : (
                        <span className="text-xs text-[var(--text-muted)]">—</span>
                      )}
                    </td>

                    {/* Источник */}
                    <td className="px-3 py-2.5 align-top">
                      {view.sourceLabel && view.sourceColorClass ? (
                        <span
                          className={cn(
                            "inline-flex max-w-full items-center rounded-full px-2 py-0.5 text-xs font-medium",
                            view.sourceColorClass,
                          )}
                        >
                          <span className="truncate">{view.sourceLabel}</span>
                        </span>
                      ) : (
                        <span className="text-xs text-[var(--text-muted)]">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {filtered.length === 0 && (
          <div className="shrink-0 border-t border-[var(--border-subtle)] px-6 py-10 text-center">
            <p className="mb-1 text-sm text-[var(--text-secondary)]">
              Запросы не найдены
            </p>
            <p className="text-[12px] text-[var(--text-muted)]">
              {requests.length === 0
                ? "Запросы появятся после анализа с найденными проблемами или ручного добавления."
                : "Попробуйте изменить условия поиска или сбросить фильтр."}
            </p>
          </div>
        )}
      </div>
    </section>
  );
};

export default RequestsTable;





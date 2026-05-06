// =============================================================
// src/components/requests/RequestsTable.tsx
// Таблица DD-запросов для юриста (legacy CRUD mode).
// Использует adapter для преобразования DDRequest в UI read-model.
// Колонки: Приоритет, Текст, Документы (count), Статус, Источник.
// Поиск, сортировка, кнопки экспорта.
// =============================================================

import React, { useMemo, useState } from "react";
import type { DDRequest } from "../../types";
import { toRequestTableRowFromLegacy } from "../../viewAdapters/requestPresentation";
import { RequestPriorityBadge } from "./shared/RequestPriorityBadge";
import { Search, Plus, Download, FileText } from "lucide-react";
import Button from "../ui/Button";
import { REQUEST_PRIORITY_ORDER } from "../../types/requestPriority";

interface Props {
  requests: DDRequest[];
  onRowClick: (request: DDRequest) => void;
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
    return "border-[color:color-mix(in_srgb,var(--color-blue)_22%,transparent)] bg-[var(--color-blue-highlight)] text-[var(--color-blue)]";
  }

  if (value.includes("progress") || value.includes("работ") || value.includes("processing")) {
    return "border-[color:color-mix(in_srgb,var(--color-orange)_22%,transparent)] bg-[var(--color-orange-highlight)] text-[var(--color-orange)]";
  }

  if (value.includes("resolved") || value.includes("done") || value.includes("закрыт")) {
    return "border-[color:color-mix(in_srgb,var(--color-success)_22%,transparent)] bg-[var(--color-success-highlight)] text-[var(--color-success)]";
  }

  return "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)]";
};

export const RequestsTable: React.FC<Props> = ({
  requests,
  onRowClick,
  onCreateClick,
  onExportWord,
  onExportExcel,
  canManageRequests,
}) => {
  const [searchText, setSearchText] = useState("");
  const [sortBy, setSortBy] = useState<SortKey>("priority");

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
    <div className="space-y-3">
      {/* Шапка */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-sm font-semibold tracking-tight text-[var(--text-primary)]">
          Запросы{" "}
          <span className="ml-1 text-[var(--text-muted)]">
            ({requests.length})
          </span>
        </h2>

        <div className="flex flex-wrap gap-2">
          {canManageRequests && (
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={onCreateClick}
              className="inline-flex items-center gap-1"
            >
              <Plus size={14} />
              Новый запрос
            </Button>
          )}

          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={onExportWord}
            className="inline-flex items-center gap-1"
          >
            <FileText size={14} />
            Word
          </Button>

          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={onExportExcel}
            className="inline-flex items-center gap-1"
          >
            <Download size={14} />
            Excel
          </Button>
        </div>
      </div>

      {/* Поиск */}
      <div className="relative">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
          size={16}
        />
        <input
          type="text"
          placeholder="Поиск по тексту запроса или ID проверки…"
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          className="input-base !pl-9"
        />
      </div>

      {/* Таблица */}
      <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)]">
        <table className="w-full border-collapse">
          <thead className="border-b border-[var(--border)] bg-[var(--bg-elevated-soft)]/60">
            <tr>
              {(
                [
                  ["priority", "Приоритет", "w-28"],
                  ["text", "Текст запроса", ""],
                  ["docs", "Документы", "w-24"],
                  ["status", "Статус", "w-32"],
                  ["source", "Источник", "w-36"],
                ] as const
              ).map(([key, label, width]) => (
                <th
                  key={key}
                  className={cn(
                    "px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]",
                    width,
                  )}
                >
                  {key === "priority" || key === "status" ? (
                    <button
                      type="button"
                      onClick={() => setSortBy(key as SortKey)}
                      className={cn(
                        "transition-colors hover:text-[var(--text-secondary)]",
                        sortBy === key &&
                          "text-[var(--accent-primary)] underline underline-offset-4",
                      )}
                    >
                      {label}
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

              return (
                <tr
                  key={view.id}
                  className="cursor-pointer border-b border-[var(--border)] transition-colors last:border-b-0 hover:bg-[var(--bg-elevated-soft)]/55"
                  onClick={() => onRowClick(dto)}
                >
                  {/* Приоритет */}
                  <td className="px-3 py-2.5 align-top">
                    <RequestPriorityBadge priority={view.priority} size="sm" />
                  </td>

                  {/* Текст */}
                  <td className="px-3 py-2.5 align-top">
                    <p className="line-clamp-2 text-sm text-[var(--text-primary)]">
                      {view.text}
                    </p>
                    {view.checkLabel && (
                      <p className="mt-0.5 text-xs text-[var(--text-muted)]">
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
                          "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap",
                          statusToneClass(view.statusLabel),
                        )}
                      >
                        {view.statusLabel}
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
                          "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap",
                          view.sourceColorClass,
                        )}
                      >
                        {view.sourceLabel}
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

        {filtered.length === 0 && (
          <div className="border-t border-[var(--border)] py-10 text-center">
            <p className="mb-1 text-sm text-[var(--text-secondary)]">
              Запросы не найдены
            </p>
            <p className="text-xs text-[var(--text-muted)]">
              {requests.length === 0
                ? "Запросы появятся после анализа с найденными проблемами."
                : "Попробуйте изменить поиск."}
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default RequestsTable;




// =============================================================
// src/components/requests/ReviewRequestsTable.tsx
// Read-only таблица DD-запросов в review-режиме.
// Работает ИСКЛЮЧИТЕЛЬНО поверх DDRequestDTO[] из run-scoped API.
// Использует adapter для преобразования DTO в UI read-model.
// =============================================================

import React, { useMemo, useState, useRef } from "react";
import type { DDRequestDTO } from "../../types/dealReview";
import { toRequestTableRowFromReview } from "../../viewAdapters/requestPresentation";
import { RequestPriorityBadge } from "./shared/RequestPriorityBadge";
import { Search } from "lucide-react";
import { REQUEST_PRIORITY_ORDER } from "../../types/requestPriority";

interface Props {
  requests: DDRequestDTO[];
  selectedRequestId?: string | null;
  onRowClick: (request: DDRequestDTO, rowElement: HTMLElement | null) => void;
}

function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

export const ReviewRequestsTable: React.FC<Props> = ({
  requests,
  selectedRequestId,
  onRowClick,
}) => {
  const [searchText, setSearchText] = useState("");

  const viewModels = useMemo(
    () =>
      requests.map((req) => ({
        dto: req,
        view: toRequestTableRowFromReview(req),
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
        const addressee = view.addressee?.toLowerCase() ?? "";
        const docsLabel = view.documentsLabel?.toLowerCase() ?? "";

        return (
          text.includes(lower) ||
          checkLabel.includes(lower) ||
          addressee.includes(lower) ||
          docsLabel.includes(lower)
        );
      });
    }

    list.sort((a, b) => {
      const pa = REQUEST_PRIORITY_ORDER[a.view.priority] ?? 9;
      const pb = REQUEST_PRIORITY_ORDER[b.view.priority] ?? 9;

      if (pa !== pb) return pa - pb;

      return (a.view.checkLabel ?? "").localeCompare(
        b.view.checkLabel ?? "",
        "ru",
      );
    });

    return list;
  }, [viewModels, searchText]);

  return (
    <section className="space-y-2">
      {/* Поиск */}
      <div className="relative">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
          size={16}
          aria-hidden="true"
        />
        <input
          type="text"
          placeholder="Поиск по тексту, проверке или документу…"
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          className="mt-1 w-full rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-9 py-2 text-sm text-[var(--text-primary)] outline-none transition placeholder:text-[var(--text-muted)] focus:border-[var(--accent-primary)]"
          aria-label="Поиск по review-запросам"
        />
      </div>

      {/* Таблица */}
      <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)]">
        <table className="w-full table-fixed border-collapse">
          <thead className="border-b border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)]/60">
            <tr>
              <th
                scope="col"
                className="w-28 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                aria-sort="ascending"
              >
                Приоритет
              </th>
              <th
                scope="col"
                className="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
              >
                Текст запроса
              </th>
              <th
                scope="col"
                className="w-48 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
              >
                Документы
              </th>
              <th
                scope="col"
                className="w-36 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
              >
                Сегмент
              </th>
            </tr>
          </thead>

          <tbody>
            {filtered.map(({ dto, view }) => {
              const isSelected = selectedRequestId === view.id;
              const rowRef = useRef<HTMLTableRowElement | null>(null);

              return (
                <tr
                  key={view.id}
                  ref={rowRef}
                  className={cn(
                    "cursor-pointer border-b border-[var(--border-subtle)] transition-colors last:border-b-0",
                    isSelected
                      ? "bg-[var(--bg-elevated-soft)]"
                      : "hover:bg-[var(--bg-elevated-soft)]/60",
                  )}
                  onClick={() => onRowClick(dto, rowRef.current)}
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
                        {view.checkLabel}
                      </p>
                    )}

                    {view.addressee && (
                      <p className="mt-1 text-[12px] text-[var(--text-secondary)]">
                        Адресат: {view.addressee}
                      </p>
                    )}
                  </td>

                  {/* Документы */}
                  <td className="px-3 py-2.5 align-top">
                    {view.documentsLabel ? (
                      <span className="line-clamp-2 text-[12px] leading-5 text-[var(--text-secondary)]">
                        {view.documentsLabel}
                      </span>
                    ) : (
                      <span className="text-xs text-[var(--text-muted)]">—</span>
                    )}
                  </td>

                  {/* Сегмент */}
                  <td className="px-3 py-2.5 align-top">
                    {view.hasSegmentContext ? (
                      <div className="flex flex-col gap-1">
                        {view.segmentTitle && (
                          <span className="line-clamp-1 text-[12px] text-[var(--text-secondary)]">
                            {view.segmentTitle}
                          </span>
                        )}

                        {view.chunkIndex != null && (
                          <span
                            className={cn(
                              "inline-flex w-fit items-center rounded-full border px-2 py-0.5 text-[10px] font-medium",
                              "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-muted)]",
                            )}
                          >
                            Chunk #{view.chunkIndex}
                          </span>
                        )}
                      </div>
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
          <div className="border-t border-[var(--border-subtle)] px-4 py-10 text-center">
            <p className="mb-1 text-sm text-[var(--text-secondary)]">
              Запросы не найдены
            </p>
            <p className="text-[12px] text-[var(--text-muted)]">
              {requests.length === 0
                ? "Запросы появятся после анализа документов."
                : "Попробуйте изменить условия поиска."}
            </p>
          </div>
        )}
      </div>
    </section>
  );
};

export default ReviewRequestsTable;





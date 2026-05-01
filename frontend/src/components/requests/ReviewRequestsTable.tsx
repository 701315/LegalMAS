// =============================================================
// src/components/requests/ReviewRequestsTable.tsx
// Read-only таблица DD-запросов в review-режиме.
// Работает ИСКЛЮЧИТЕЛЬНО поверх DDRequestDTO[] из run-scoped API.
// Использует adapter для преобразования DTO в UI read-model.
// =============================================================

import React, { useMemo, useState } from "react";
import type { DDRequestDTO } from "../../types/dealReview";
import { toRequestTableRowFromReview } from "../../viewAdapters/requestPresentation";
import { RequestPriorityBadge } from "./shared/RequestPriorityBadge";
import { Search } from "lucide-react";
import { REQUEST_PRIORITY_ORDER } from "../../types/requestPriority";

interface Props {
  requests: DDRequestDTO[];
  onRowClick: (request: DDRequestDTO) => void;
}

/**
 * Read-only таблица запросов.
 *
 * Важно:
 * - Вся бизнес-логика приведения DTO → UI-модель вынесена в adapter
 *   (toRequestTableRowFromReview).
 * - Здесь остаётся только поиск/сортировка и простая разметка.
 */
export const ReviewRequestsTable: React.FC<Props> = ({
  requests,
  onRowClick,
}) => {
  const [searchText, setSearchText] = useState("");

  // Преобразуем все запросы в UI read-model через adapter
  const viewModels = useMemo(
    () =>
      requests.map((req) => ({
        dto: req, // сохраняем исходный DTO для onRowClick
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
        // Для review mode у нас уже есть document names в view.documentsLabel
        const docsLabel = view.documentsLabel?.toLowerCase() ?? "";

        return (
          text.includes(lower) ||
          checkLabel.includes(lower) ||
          addressee.includes(lower) ||
          docsLabel.includes(lower)
        );
      });
    }

    // Сортировка: critical → high → medium → low, внутри — по check_name
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
    <div className="space-y-3">
      {/* Шапка */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-gray-900">
          Запросы — Review ({requests.length})
        </h2>
      </div>

      {/* Поиск */}
      <div className="relative">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
          size={16}
        />
        <input
          type="text"
          placeholder="Поиск по тексту, проверке или документу…"
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          className="w-full rounded-lg border px-9 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {/* Таблица */}
      <div className="overflow-hidden rounded-lg border">
        <table className="w-full table-fixed">
          <thead>
            <tr className="bg-gray-50">
              <th className="w-28 px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                Приоритет
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                Текст запроса
              </th>
              <th className="w-48 px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                Документы
              </th>
              <th className="w-36 px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
                Сегмент
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {filtered.map(({ dto, view }) => (
              <tr
                key={view.id}
                className="cursor-pointer transition hover:bg-gray-50"
                onClick={() => onRowClick(dto)}
              >
                {/* Приоритет — shared component */}
                <td className="px-4 py-3 align-top">
                  <RequestPriorityBadge priority={view.priority} size="sm" />
                </td>

                {/* Текст */}
                <td className="px-4 py-3 align-top">
                  <p className="line-clamp-2 text-sm text-gray-900">
                    {view.text}
                  </p>
                  {view.checkLabel && (
                    <p className="mt-0.5 text-xs text-gray-400">
                      {view.checkLabel}
                    </p>
                  )}
                  {view.addressee && (
                    <p className="mt-0.5 text-xs text-blue-500">
                      → {view.addressee}
                    </p>
                  )}
                </td>

                {/* Документы — используем готовый label из view model */}
                <td className="px-4 py-3 align-top">
                  {view.documentsLabel ? (
                    <span className="line-clamp-2 text-xs text-gray-700">
                      {view.documentsLabel}
                    </span>
                  ) : (
                    <span className="text-xs text-gray-300">—</span>
                  )}
                </td>

                {/* Сегмент — используем готовые поля из view model */}
                <td className="px-4 py-3 align-top">
                  {view.hasSegmentContext ? (
                    <div className="flex flex-col gap-0.5">
                      {view.segmentTitle && (
                        <span className="line-clamp-1 text-xs text-gray-700">
                          {view.segmentTitle}
                        </span>
                      )}
                      {view.chunkIndex != null && (
                        <span className="text-[10px] text-gray-400">
                          Chunk #{view.chunkIndex}
                        </span>
                      )}
                    </div>
                  ) : (
                    <span className="text-xs text-gray-300">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {filtered.length === 0 && (
          <div className="py-16 text-center text-gray-400">
            <p className="mb-1 text-lg">Запросы не найдены</p>
            <p className="text-sm">
              {requests.length === 0
                ? "Запросы появятся после анализа документов"
                : "Попробуйте изменить поиск"}
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default ReviewRequestsTable;



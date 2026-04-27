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

interface Props {
  requests: DDRequestDTO[];
  onRowClick: (request: DDRequestDTO) => void;
}

const PRIORITY_ORDER: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
};

export const ReviewRequestsTable: React.FC<Props> = ({
  requests,
  onRowClick,
}) => {
  const [searchText, setSearchText] = useState("");

  // Преобразуем все запросы в UI read-model через adapter
  const viewModels = useMemo(() => {
    return requests.map((req) => ({
      dto: req, // сохраняем исходный DTO для onRowClick
      view: toRequestTableRowFromReview(req),
    }));
  }, [requests]);

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

    // Сортировка: critical → high → medium, внутри — по check_name
    list.sort((a, b) => {
      const pa = PRIORITY_ORDER[a.view.priority] ?? 9;
      const pb = PRIORITY_ORDER[b.view.priority] ?? 9;
      if (pa !== pb) return pa - pb;
      return (a.view.checkLabel ?? "").localeCompare(b.view.checkLabel ?? "");
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
          className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
          size={16}
        />
        <input
          type="text"
          placeholder="Поиск по тексту, проверке или документу…"
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          className="w-full pl-9 pr-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {/* Таблица */}
      <div className="border rounded-lg overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="bg-gray-50">
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider w-28">
                Приоритет
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Текст запроса
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider w-48">
                Документы
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider w-36">
                Сегмент
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {filtered.map((item) => {
              const { dto, view } = item;

              return (
                <tr
                  key={view.id}
                  className="hover:bg-gray-50 cursor-pointer transition"
                  onClick={() => onRowClick(dto)}
                >
                  {/* Приоритет — shared component */}
                  <td className="px-4 py-3">
                    <RequestPriorityBadge priority={view.priority} size="sm" />
                  </td>

                  {/* Текст */}
                  <td className="px-4 py-3">
                    <p className="text-sm text-gray-900 line-clamp-2">
                      {view.text}
                    </p>
                    {view.checkLabel && (
                      <p className="text-xs text-gray-400 mt-0.5">
                        {view.checkLabel}
                      </p>
                    )}
                    {view.addressee && (
                      <p className="text-xs text-blue-500 mt-0.5">
                        → {view.addressee}
                      </p>
                    )}
                  </td>

                  {/* Документы — используем готовый label из view model */}
                  <td className="px-4 py-3">
                    {view.documentsLabel ? (
                      <span className="text-xs text-gray-700 line-clamp-2">
                        {view.documentsLabel}
                      </span>
                    ) : (
                      <span className="text-xs text-gray-300">—</span>
                    )}
                  </td>

                  {/* Сегмент — используем готовые поля из view model */}
                  <td className="px-4 py-3">
                    {view.hasSegmentContext ? (
                      <div className="flex flex-col gap-0.5">
                        {view.segmentTitle && (
                          <span className="text-xs text-gray-700 line-clamp-1">
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
              );
            })}
          </tbody>
        </table>

        {filtered.length === 0 && (
          <div className="text-center py-16 text-gray-400">
            <p className="text-lg mb-1">Запросы не найдены</p>
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



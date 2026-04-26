// =============================================================
// src/components/requests/ReviewRequestsTable.tsx
// Read-only таблица DD-запросов в review-режиме.
// Работает ИСКЛЮЧИТЕЛЬНО поверх DDRequestDTO[] из run-scoped API.
// Не зависит от legacy DDRequest[].
// =============================================================

import React, { useMemo, useState } from "react";
import type { DDRequestDTO } from "../../types/dealReview";
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

function PriorityBadge({ priority }: { priority: string }) {
  if (priority === "critical") {
    return (
      <span className="px-2 py-0.5 rounded text-xs font-semibold bg-red-100 text-red-800">
        Критичный
      </span>
    );
  }
  if (priority === "high") {
    return (
      <span className="px-2 py-0.5 rounded text-xs font-semibold bg-orange-100 text-orange-800">
        Высокий
      </span>
    );
  }
  return (
    <span className="px-2 py-0.5 rounded text-xs font-semibold bg-yellow-100 text-yellow-800">
      Средний
    </span>
  );
}

export const ReviewRequestsTable: React.FC<Props> = ({
  requests,
  onRowClick,
}) => {
  const [searchText, setSearchText] = useState("");

  const filtered = useMemo(() => {
    let list = [...requests];

    if (searchText.trim()) {
      const lower = searchText.toLowerCase();
      list = list.filter((r) => {
        const text = r.text.toLowerCase();
        const checkName = r.check_name?.toLowerCase() ?? "";
        const docNames = r.document_names.join(" ").toLowerCase();
        return (
          text.includes(lower) ||
          checkName.includes(lower) ||
          docNames.includes(lower)
        );
      });
    }

    // Сортировка: critical → high → medium, внутри — по check_name
    list.sort((a, b) => {
      const pa = PRIORITY_ORDER[a.priority] ?? 9;
      const pb = PRIORITY_ORDER[b.priority] ?? 9;
      if (pa !== pb) return pa - pb;
      return (a.check_name ?? "").localeCompare(b.check_name ?? "");
    });

    return list;
  }, [requests, searchText]);

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
            {filtered.map((req) => {
              // Segment context: показываем если есть хотя бы один из полей
              const hasSegment = !!(
                req.segment_id ||
                req.segment_title ||
                req.chunk_index != null
              );

              return (
                <tr
                  key={req.request_id}
                  className="hover:bg-gray-50 cursor-pointer transition"
                  onClick={() => onRowClick(req)}
                >
                  {/* Приоритет */}
                  <td className="px-4 py-3">
                    <PriorityBadge priority={req.priority} />
                  </td>

                  {/* Текст */}
                  <td className="px-4 py-3">
                    <p className="text-sm text-gray-900 line-clamp-2">
                      {req.text}
                    </p>
                    {req.check_name && (
                      <p className="text-xs text-gray-400 mt-0.5">
                        {req.check_name}
                      </p>
                    )}
                    {req.addressee && (
                      <p className="text-xs text-blue-500 mt-0.5">
                        → {req.addressee}
                      </p>
                    )}
                  </td>

                  {/* Документы — уже имена, не ID */}
                  <td className="px-4 py-3">
                    {req.document_names.length === 0 ? (
                      <span className="text-xs text-gray-300">—</span>
                    ) : req.document_names.length === 1 ? (
                      <span className="text-xs text-gray-700 line-clamp-2">
                        {req.document_names[0]}
                      </span>
                    ) : (
                      <span className="text-xs text-gray-700">
                        {req.document_names[0]}
                        <span className="text-gray-400">
                          {" "}+{req.document_names.length - 1}
                        </span>
                      </span>
                    )}
                  </td>

                  {/* Сегмент */}
                  <td className="px-4 py-3">
                    {hasSegment ? (
                      <div className="flex flex-col gap-0.5">
                        {req.segment_title && (
                          <span className="text-xs text-gray-700 line-clamp-1">
                            {req.segment_title}
                          </span>
                        )}
                        {req.chunk_index != null && (
                          <span className="text-[10px] text-gray-400">
                            Chunk #{req.chunk_index}
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


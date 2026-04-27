// =============================================================
// src/components/requests/RequestsTable.tsx
// Таблица DD‑запросов для юриста (legacy CRUD mode).
// Использует adapter для преобразования DDRequest в UI read-model.
// Колонки: Приоритет, Текст, Документы (count), Статус, Источник.
// Поиск, сортировка, кнопки экспорта.
// =============================================================

import React, { useMemo, useState } from "react";
import type { DDRequest } from "../../types";
import { toRequestTableRowFromLegacy } from "../../viewAdapters/requestPresentation";
import { RequestPriorityBadge } from "./shared/RequestPriorityBadge";
import { Search, Plus, Download, FileText } from "lucide-react";

interface Props {
  requests: DDRequest[];
  onRowClick: (request: DDRequest) => void;
  onCreateClick: () => void;
  onExportWord: () => Promise<void>;
  onExportExcel: () => Promise<void>;
  canManageRequests: boolean;
}

type SortKey = "priority" | "status" | "created";

const PRIORITY_ORDER: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
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

  // Преобразуем все запросы в UI read-model через adapter
  const viewModels = useMemo(() => {
    return requests.map((req) => ({
      dto: req, // сохраняем исходный DDRequest для onRowClick и сортировки
      view: toRequestTableRowFromLegacy(req),
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
        return text.includes(lower) || checkLabel.includes(lower);
      });
    }

    list.sort((a, b) => {
      if (sortBy === "priority") {
        return (
          (PRIORITY_ORDER[a.view.priority] ?? 9) -
          (PRIORITY_ORDER[b.view.priority] ?? 9)
        );
      }
      if (sortBy === "status") {
        return (a.view.statusLabel ?? "").localeCompare(
          b.view.statusLabel ?? ""
        );
      }
      // created (newest first) — используем исходный DTO
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
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-gray-900">
          Запросы ({requests.length})
        </h2>
        <div className="flex gap-2">
          {canManageRequests && (
            <button
              onClick={onCreateClick}
              className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 text-white rounded text-sm font-medium hover:bg-blue-700 transition"
            >
              <Plus size={14} />
              Новый запрос
            </button>
          )}
          <button
            onClick={onExportWord}
            className="flex items-center gap-1 px-3 py-1.5 bg-gray-100 text-gray-700 rounded text-sm hover:bg-gray-200 transition"
          >
            <FileText size={14} />
            Word
          </button>
          <button
            onClick={onExportExcel}
            className="flex items-center gap-1 px-3 py-1.5 bg-gray-100 text-gray-700 rounded text-sm hover:bg-gray-200 transition"
          >
            <Download size={14} />
            Excel
          </button>
        </div>
      </div>

      {/* Поиск */}
      <div className="relative">
        <Search
          className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
          size={16}
        />
        <input
          type="text"
          placeholder="Поиск по тексту запроса или ID проверки…"
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
              {(
                [
                  ["priority", "Приоритет", "w-28"],
                  ["text", "Текст запроса", ""],
                  ["docs", "Документы", "w-24"],
                  ["status", "Статус", "w-28"],
                  ["source", "Источник", "w-32"],
                ] as const
              ).map(([key, label, width]) => (
                <th
                  key={key}
                  className={`px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider ${width}`}
                >
                  {key === "priority" || key === "status" ? (
                    <button
                      onClick={() => setSortBy(key as SortKey)}
                      className={`hover:text-gray-700 ${
                        sortBy === key ? "text-blue-600 underline" : ""
                      }`}
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
                        Проверка: {view.checkLabel}
                      </p>
                    )}
                  </td>

                  {/* Документы — используем готовый count из view model */}
                  <td className="px-4 py-3 text-sm text-gray-700">
                    {view.documentCount} док.
                  </td>

                  {/* Статус */}
                  <td className="px-4 py-3">
                    {view.statusLabel ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-700">
                        <span>{view.statusLabel}</span>
                      </span>
                    ) : (
                      <span className="text-gray-300 text-xs">—</span>
                    )}
                  </td>

                  {/* Источник */}
                  <td className="px-4 py-3">
                    {view.sourceLabel && view.sourceColorClass ? (
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${view.sourceColorClass}`}
                      >
                        <span>{view.sourceLabel}</span>
                      </span>
                    ) : (
                      <span className="text-gray-300 text-xs">—</span>
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
                ? "Запросы появятся после анализа с найденными проблемами"
                : "Попробуйте изменить поиск"}
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default RequestsTable;




// =============================================================
// src/components/requests/RequestsTable.tsx
// Таблица DD‑запросов для юриста.
// Колонки: Приоритет, Текст, Документы (count), Статус, Источник.
// Поиск, сортировка, кнопки экспорта.
// =============================================================

import React, { useMemo, useState } from "react";
import type { DDRequest } from "../../types";
import {
  DD_REQUEST_STATUS_DISPLAY,
  DD_REQUEST_SOURCE_DISPLAY,
} from "../../constants";
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

  const filtered = useMemo(() => {
    let list = [...requests];

    if (searchText.trim()) {
      const lower = searchText.toLowerCase();
      list = list.filter((r) => {
        const text = r.text.toLowerCase();
        const checkName = r.check_id?.toLowerCase() ?? "";
        return text.includes(lower) || checkName.includes(lower);
      });
    }

    list.sort((a, b) => {
      if (sortBy === "priority") {
        return (
          (PRIORITY_ORDER[a.priority] ?? 9) -
          (PRIORITY_ORDER[b.priority] ?? 9)
        );
      }
      if (sortBy === "status") {
        return a.status.localeCompare(b.status);
      }
      // created (newest first)
      return (
        new Date(b.created_at).getTime() -
        new Date(a.created_at).getTime()
      );
    });

    return list;
  }, [requests, searchText, sortBy]);

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
            {filtered.map((req) => {
              const statusDisplay =
                DD_REQUEST_STATUS_DISPLAY[req.status] ?? req.status;
              const [statusIcon, statusLabel] =
                statusDisplay.includes(" ")
                  ? statusDisplay.split(" ", 2)
                  : ["", statusDisplay];

              const sourceCfg = req.source
                ? DD_REQUEST_SOURCE_DISPLAY[req.source]
                : undefined;

              const documentCount = Array.isArray(req.document_refs)
                ? req.document_refs.length
                : 0;

              return (
                <tr
                  key={req.id}
                  className="hover:bg-gray-50 cursor-pointer transition"
                  onClick={() => onRowClick(req)}
                >
                  {/* Приоритет */}
                  <td className="px-4 py-3">
                    <span
                      className={`px-2 py-1 rounded text-xs font-semibold ${
                        req.priority === "critical"
                          ? "bg-red-100 text-red-800"
                          : req.priority === "high"
                          ? "bg-orange-100 text-orange-800"
                          : "bg-yellow-100 text-yellow-800"
                      }`}
                    >
                      {req.priority === "critical"
                        ? "Критичный"
                        : req.priority === "high"
                        ? "Высокий"
                        : "Средний"}
                    </span>
                  </td>

                  {/* Текст */}
                  <td className="px-4 py-3">
                    <p className="text-sm text-gray-900 line-clamp-2">
                      {req.text}
                    </p>
                    {req.check_id && (
                      <p className="text-xs text-gray-400 mt-0.5">
                        Проверка: {req.check_id}
                      </p>
                    )}
                  </td>

                  {/* Документы */}
                  <td className="px-4 py-3 text-sm text-gray-700">
                    {documentCount} док.
                  </td>

                  {/* Статус */}
                  <td className="px-4 py-3">
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-700">
                      {statusIcon && (
                        <span aria-hidden="true">{statusIcon}</span>
                      )}
                      <span>{statusLabel}</span>
                    </span>
                  </td>

                  {/* Источник */}
                  <td className="px-4 py-3">
                    {sourceCfg ? (
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${sourceCfg.color}`}
                      >
                        {sourceCfg.icon && (
                          <span aria-hidden="true">
                            {sourceCfg.icon}
                          </span>
                        )}
                        <span>{sourceCfg.label}</span>
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

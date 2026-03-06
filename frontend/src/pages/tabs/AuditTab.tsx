// =============================================================
// src/pages/tabs/AuditTab.tsx
// Вкладка «Аудит» (только admin / reviewer как security role).
// Журнал действий: кто, когда, что сделал, с фильтром по действию.
// =============================================================

import React, { useState } from "react";
import { useAuditLog } from "../../api/audit";
import { useAuth } from "../../hooks/useAuth";
import { AUDIT_ACTION_LABEL } from "../../constants";
import { Loader2, Shield, ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "../../utils";

interface Props {
  dealId: string;
}

export const AuditTab: React.FC<Props> = ({ dealId }) => {
  const { userRole } = useAuth();
  const [filterAction, setFilterAction] = useState<string>("");
  const [page, setPage] = useState(1);

  // RBAC: только admin и reviewer (как security / lead)
  if (!["admin", "reviewer"].includes(userRole)) {
    return (
      <div className="flex flex-col items-center justify-center bg-gray-50 rounded-lg py-20 text-center">
        <Shield size={48} className="text-gray-300 mb-4" />
        <h2 className="text-xl font-semibold text-gray-900 mb-2">
          Доступ ограничен
        </h2>
        <p className="text-gray-500">
          Журнал аудита доступен только администраторам и ответственным за безопасность.
        </p>
      </div>
    );
  }

  const { data: auditData, isLoading } = useAuditLog(dealId, {
    action: filterAction || undefined,
    page,
    per_page: 50,
  });

  const items = auditData?.items ?? [];
  const totalPages = auditData?.total_pages ?? 1;

  return (
    <div className="space-y-4">
      {/* Шапка */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-gray-900">
          Журнал аудита
        </h2>
        <div className="flex gap-2">
          <select
            value={filterAction}
            onChange={(e) => {
              setFilterAction(e.target.value);
              setPage(1);
            }}
            className="px-3 py-1.5 border rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">Все действия</option>
            {Object.entries(AUDIT_ACTION_LABEL).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Таблица */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="animate-spin mr-3 text-blue-500" size={24} />
          <span className="text-gray-500">Загружаем журнал…</span>
        </div>
      ) : (
        <>
          <div className="border rounded-lg overflow-hidden bg-white">
            <table className="w-full">
              <thead>
                <tr className="bg-gray-50">
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase w-48">
                    Время
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase w-32">
                    Действие
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase w-40">
                    Пользователь
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase w-24">
                    Роль
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">
                    Детали
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {items.map((log) => (
                  <tr
                    key={log.id}
                    className={cn(
                      "hover:bg-gray-50",
                      log.action === "RECLASSIFY" && "bg-purple-50",
                    )}
                  >
                    <td className="px-4 py-3 text-sm text-gray-700">
                      {new Date(log.created_at).toLocaleString("ru-RU", {
                        day: "2-digit",
                        month: "2-digit",
                        year: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                      })}
                    </td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 bg-blue-100 text-blue-800 text-xs rounded-full font-medium">
                        {AUDIT_ACTION_LABEL[log.action] || log.action}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm font-medium text-gray-900">
                      {log.actor}
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-500">
                      {log.actor_role}
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-600 max-w-[360px] truncate">
                      {formatDetails(log.details as Record<string, unknown>)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {items.length === 0 && (
              <div className="text-center py-12 text-gray-400">
                Записи не найдены
              </div>
            )}
          </div>

          {/* Пагинация */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-3">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="p-1.5 border rounded hover:bg-gray-50 disabled:opacity-30"
              >
                <ChevronLeft size={16} />
              </button>
              <span className="text-sm text-gray-600">
                Страница {page} из {totalPages}
              </span>
              <button
                onClick={() =>
                  setPage((p) => Math.min(totalPages, p + 1))
                }
                disabled={page >= totalPages}
                className="p-1.5 border rounded hover:bg-gray-50 disabled:opacity-30"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
};

/* --- Форматирование деталей --- */
function formatDetails(details: Record<string, unknown>): string {
  if (!details || Object.keys(details).length === 0) return "—";

  // Специальный кейс: переклассификация документа
  if (details.previous_doc_type !== undefined) {
    const prev = String(details.previous_doc_type || "?");
    const next = String(details.new_doc_type || "?");
    const reason =
      details.reason && String(details.reason).trim().length > 0
        ? ` · Причина: ${String(details.reason)}`
        : "";
    return `${prev} → ${next}${reason}`;
  }

  // Общий формат: k: v, ... (без document_id)
  return Object.entries(details)
    .filter(([k]) => !["document_id"].includes(k))
    .map(([k, v]) => `${k}: ${String(v)}`)
    .join(", ");
}

export default AuditTab;

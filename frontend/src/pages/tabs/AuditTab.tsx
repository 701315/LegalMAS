// =============================================================
// src/pages/tabs/AuditTab.tsx
// Вкладка «Аудит» (только admin / reviewer как security role).
// Журнал действий: кто, когда, что сделал, с фильтром по действию.
// =============================================================

import React, { useState } from "react";
import { useAuditLog } from "../../api/audit";
import { AUDIT_ACTION_LABEL } from "../../constants";
import { Loader2, Shield, ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "../../utils";
import { useDealPermissions } from "../../hooks/usePermissions";

interface Props {
  dealId: string;
}

export const AuditTab: React.FC<Props> = ({ dealId }) => {
  const { canViewAuditLog } = useDealPermissions(dealId);
  const [filterAction, setFilterAction] = useState<string>("");
  const [page, setPage] = useState(1);

  const { data: auditData, isLoading } = useAuditLog(dealId, {
    action: filterAction || undefined,
    page,
    per_page: 50,
  });

  const items = auditData?.items ?? [];
  const totalPages = auditData?.total_pages ?? 1;

  // Нет доступа
  if (!canViewAuditLog) {
    return (
      <div className="flex flex-col items-center justify-center rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-6 py-16 text-center">
        <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-white/5">
          <Shield size={32} className="text-[var(--text-muted)]" />
        </div>
        <h2 className="mb-1 text-sm font-semibold tracking-tight text-[var(--text-primary)]">
          Доступ к журналу ограничен
        </h2>
        <p className="max-w-md text-xs text-[var(--text-muted)]">
          Журнал аудита доступен только администраторам и ответственным за
          безопасность в рамках этого проекта.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Шапка */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold tracking-tight text-[var(--text-primary)]">
            Журнал аудита
          </h2>
          <p className="mt-0.5 text-xs text-[var(--text-muted)]">
            Кто, когда и какие действия выполнял в рамках сделки.
          </p>
        </div>
        <div className="flex gap-2">
          <select
            value={filterAction}
            onChange={(e) => {
              setFilterAction(e.target.value);
              setPage(1);
            }}
            className="input-base h-8 w-56 text-xs"
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

      {/* Таблица / loading */}
      {isLoading ? (
        <div className="flex items-center justify-center rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] py-16">
          <Loader2 className="mr-3 animate-spin text-[var(--accent)]" size={20} />
          <span className="text-sm text-[var(--text-muted)]">
            Загружаем журнал…
          </span>
        </div>
      ) : (
        <>
          <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)]">
            <table className="w-full table-fixed border-collapse">
              <thead className="border-b border-[var(--border)] bg-white/2">
                <tr>
                  <th className="w-48 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                    Время
                  </th>
                  <th className="w-32 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                    Действие
                  </th>
                  <th className="w-40 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                    Пользователь
                  </th>
                  <th className="w-24 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                    Роль
                  </th>
                  <th className="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                    Детали
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((log) => (
                  <tr
                    key={log.id}
                    className={cn(
                      "border-b border-[var(--border)] transition-colors hover:bg-white/3",
                      log.action === "RECLASSIFY" && "bg-purple-950/20",
                      log.action === "SET_DEAL_PLAYBOOK" && "bg-sky-950/20",
                    )}
                  >
                    <td className="px-3 py-2.5 text-xs text-[var(--text-secondary)]">
                      {new Date(log.created_at).toLocaleString("ru-RU", {
                        day: "2-digit",
                        month: "2-digit",
                        year: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                      })}
                    </td>
                    <td className="px-3 py-2.5">
                      <span className="rounded-full bg-sky-900/40 px-2 py-0.5 text-[11px] font-medium text-sky-200">
                        {AUDIT_ACTION_LABEL[log.action] || log.action}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-xs font-medium text-[var(--text-primary)]">
                      {log.actor}
                    </td>
                    <td className="px-3 py-2.5 text-[11px] text-[var(--text-muted)]">
                      {log.actor_role}
                    </td>
                    <td className="max-w-[380px] px-3 py-2.5 text-[11px] text-[var(--text-secondary)]">
                      <span className="line-clamp-2">
                        {formatDetails(
                          log.action,
                          log.details as Record<string, unknown> | null,
                        )}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {items.length === 0 && (
              <div className="py-10 text-center">
                <p className="mb-1 text-sm text-[var(--text-secondary)]">
                  Записи не найдены
                </p>
                <p className="text-xs text-[var(--text-muted)]">
                  Журнал пока пуст или не подходит под текущий фильтр.
                </p>
              </div>
            )}
          </div>

          {/* Пагинация */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-3 pt-1">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="flex h-8 w-8 items-center justify-center rounded-full border border-[var(--border)] text-[var(--text-secondary)] hover:bg-white/5 disabled:opacity-40"
              >
                <ChevronLeft size={16} />
              </button>
              <span className="text-xs text-[var(--text-muted)]">
                Страница {page} из {totalPages}
              </span>
              <button
                type="button"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="flex h-8 w-8 items-center justify-center rounded-full border border-[var(--border)] text-[var(--text-secondary)] hover:bg-white/5 disabled:opacity-40"
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
function formatDetails(
  action: string,
  details: Record<string, unknown> | null,
): string {
  if (!details || Object.keys(details).length === 0) return "—";

  if (action === "SET_DEAL_PLAYBOOK") {
    const playbookName =
      (details.playbook_name && String(details.playbook_name)) || "Playbook";
    const semver =
      details.semver && String(details.semver).trim().length > 0
        ? String(details.semver)
        : "";
    const namePart = semver ? `${playbookName} (${semver})` : playbookName;

    const oldId =
      details.old_playbook_version_id &&
      String(details.old_playbook_version_id).trim().length > 0
        ? String(details.old_playbook_version_id)
        : "—";
    const newId =
      details.new_playbook_version_id &&
      String(details.new_playbook_version_id).trim().length > 0
        ? String(details.new_playbook_version_id)
        : "—";

    return `${namePart}: ${oldId} → ${newId}`;
  }

  if (details.previous_doc_type !== undefined) {
    const prev = String(details.previous_doc_type || "?");
    const next = String(details.new_doc_type || "?");
    const reason =
      details.reason &&
      String(details.reason).toString().trim().length > 0
        ? ` · Причина: ${String(details.reason)}`
        : "";
    return `${prev} → ${next}${reason}`;
  }

  return Object.entries(details)
    .filter(([k]) => !["document_id"].includes(k))
    .map(([k, v]) => `${k}: ${String(v)}`)
    .join(", ");
}

export default AuditTab;




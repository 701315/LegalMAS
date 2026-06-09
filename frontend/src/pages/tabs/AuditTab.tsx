// =============================================================
// src/pages/tabs/AuditTab.tsx
// Вкладка «Аудит».
// Режимы:
// - audit_log: стандартный журнал действий;
// - classification_audit: аудит классификации документов проекта.
//
// Layout contract:
// - Верхняя часть вкладки (PageSection header, mode switch, filter bar) — не скроллится.
// - Таблица журнала аудита получает внутренний scroll viewport.
// - Шапка таблицы sticky внутри viewport.
// - Пагинация находится под таблицей и не входит в scroll viewport.
// =============================================================

import React, { useState } from "react";
import { Loader2, Shield, ChevronLeft, ChevronRight } from "lucide-react";

import { useAuditLog } from "../../api/audit";
import { AUDIT_ACTION_LABEL } from "../../constants";
import { cn } from "../../utils";
import { useDealPermissions } from "../../hooks/usePermissions";
import PageSection from "../../components/ui/PageSection";
import Button from "../../components/ui/Button";
import ClassificationAuditView from "./audit/ClassificationAuditView";

interface Props {
  dealId: string;
}

type AuditViewMode = "audit_log" | "classification_audit";

const FILTER_BUTTON_ACTIVE_CLASS =
  "border-[var(--accent-primary)] bg-[var(--accent-muted)] text-[var(--text-primary)] shadow-sm hover:bg-[var(--accent-muted)]";

const ROW_HIGHLIGHT_RECLASSIFY =
  "bg-[color:color-mix(in_srgb,var(--accent-primary)_6%,transparent)]";

const ROW_HIGHLIGHT_PLAYBOOK =
  "bg-[color:color-mix(in_srgb,var(--color-blue,#3b82f6)_6%,transparent)]";

const AuditActionFilterInlinePanel: React.FC<{
  selectedAction: string;
  onSelect: (value: string) => void;
  onReset: () => void;
  onClose: () => void;
}> = ({ selectedAction, onSelect, onReset, onClose }) => (
  <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated-soft)]">
    <div className="border-b border-[var(--border-subtle)] px-4 py-3">
      <p className="text-sm font-semibold text-[var(--text-primary)]">
        Фильтр по действиям
      </p>
      <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
        Выберите действие, чтобы показать только соответствующие записи журнала
      </p>
    </div>

    <div className="px-4 py-4">
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          variant={selectedAction === "" ? "outline" : "secondary"}
          onClick={() => onSelect("")}
          aria-pressed={selectedAction === ""}
          className={selectedAction === "" ? FILTER_BUTTON_ACTIVE_CLASS : ""}
        >
          Все действия
        </Button>

        {Object.entries(AUDIT_ACTION_LABEL).map(([key, label]) => {
          const isSelected = selectedAction === key;

          return (
            <Button
              key={key}
              type="button"
              size="sm"
              variant={isSelected ? "outline" : "secondary"}
              onClick={() => onSelect(key)}
              aria-pressed={isSelected}
              className={isSelected ? FILTER_BUTTON_ACTIVE_CLASS : ""}
            >
              {label}
            </Button>
          );
        })}
      </div>
    </div>

    <div className="flex items-center justify-between gap-2 border-t border-[var(--border-subtle)] px-4 py-3">
      <Button size="sm" variant="ghost" onClick={onReset}>
        Сбросить
      </Button>

      <div className="flex gap-2">
        <Button size="sm" variant="secondary" onClick={onClose}>
          Закрыть
        </Button>
      </div>
    </div>
  </div>
);

export const AuditTab: React.FC<Props> = ({ dealId }) => {
  const { canViewAuditLog } = useDealPermissions(dealId);

  const [viewMode, setViewMode] = useState<AuditViewMode>("audit_log");
  const [filterAction, setFilterAction] = useState<string>("");
  const [page, setPage] = useState(1);
  const [isActionFilterOpen, setIsActionFilterOpen] = useState(false);

  const { data: auditData, isLoading } = useAuditLog(dealId, {
    action: filterAction || undefined,
    page,
    per_page: 50,
  });

  const items = auditData?.items ?? [];
  const totalPages = auditData?.total_pages ?? 1;

  const currentFilterLabel =
    filterAction && AUDIT_ACTION_LABEL[filterAction]
      ? `Действие: ${AUDIT_ACTION_LABEL[filterAction]}`
      : "Все действия";

  if (!canViewAuditLog) {
    return (
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
        <div className="px-6 py-10">
          <div className="flex min-h-[320px] flex-col items-center justify-center text-center">
            <div className="mb-4 inline-flex h-14 w-14 items-center justify-center rounded-full bg-[var(--bg-elevated-soft)]">
              <Shield size={30} className="text-[var(--text-muted)]" />
            </div>

            <h2 className="text-base font-semibold text-[var(--text-primary)]">
              Доступ к журналу ограничен
            </h2>

            <p className="mt-2 max-w-md text-sm text-[var(--text-muted)]">
              Журнал аудита доступен только администраторам и ответственным за
              безопасность в рамках этого проекта.
            </p>
          </div>
        </div>
      </section>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PageSection
        title={
          viewMode === "audit_log"
            ? "Журнал аудита"
            : "Аудит классификации документов"
        }
        subtitle={
          viewMode === "audit_log"
            ? "Кто, когда и какие действия выполнял в рамках сделки."
            : "Сводная explainability-информация по классификации документов текущего проекта."
        }
        rightSlot={
          <div className="flex flex-wrap items-center gap-2">
            {viewMode === "audit_log" ? (
              <Button
                type="button"
                size="sm"
                variant={isActionFilterOpen ? "outline" : "secondary"}
                onClick={() => setIsActionFilterOpen((prev) => !prev)}
                aria-expanded={isActionFilterOpen}
                aria-controls="audit-action-filter-panel"
                className={isActionFilterOpen ? FILTER_BUTTON_ACTIVE_CLASS : ""}
              >
                {currentFilterLabel}
              </Button>
            ) : (
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={() => setViewMode("audit_log")}
              >
                К журналу аудита
              </Button>
            )}

            <Button
              type="button"
              size="sm"
              variant={
                viewMode === "classification_audit" ? "outline" : "secondary"
              }
              onClick={() => {
                setViewMode("classification_audit");
                setIsActionFilterOpen(false);
              }}
              className={
                viewMode === "classification_audit"
                  ? FILTER_BUTTON_ACTIVE_CLASS
                  : ""
              }
            >
              Аудит классификации документов
            </Button>
          </div>
        }
        className="flex-1 min-h-0"
        contentClassName="flex min-h-0 flex-1 flex-col"
        bodyClassName="flex h-full min-h-0 flex-col"
      >
        {viewMode === "classification_audit" ? (
          <div className="min-h-0 flex-1 overflow-y-auto">
            <ClassificationAuditView dealId={dealId} />
          </div>
        ) : (
          <div className="flex h-full min-h-0 flex-col">
            {isActionFilterOpen && (
              <div id="audit-action-filter-panel" className="mb-4 shrink-0">
                <AuditActionFilterInlinePanel
                  selectedAction={filterAction}
                  onSelect={(value) => {
                    setFilterAction(value);
                    setPage(1);
                  }}
                  onReset={() => {
                    setFilterAction("");
                    setPage(1);
                  }}
                  onClose={() => setIsActionFilterOpen(false)}
                />
              </div>
            )}

            <div className="flex min-h-0 flex-1 flex-col">
              {isLoading ? (
                <div className="flex flex-1 items-center justify-center rounded-xl border border-[var(--border)] bg-[var(--bg-card)] py-16">
                  <Loader2
                    className="mr-3 animate-spin text-[var(--accent)]"
                    size={20}
                  />
                  <span className="text-sm text-[var(--text-muted)]">
                    Загружаем журнал…
                  </span>
                </div>
              ) : (
                <>
                  {/* Scroll viewport только для таблицы */}
                  <div className="min-h-0 flex-1 overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--bg-card)]">
                    {items.length > 0 ? (
                      <div className="h-full overflow-y-auto overflow-x-auto">
                        <table className="w-full table-fixed border-collapse">
                          <thead className="sticky top-0 z-10 border-b border-[var(--border)] bg-[var(--bg-elevated-soft)]">
                            <tr>
                              <th
                                scope="col"
                                className="w-48 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                              >
                                Время
                              </th>
                              <th
                                scope="col"
                                className="w-52 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                              >
                                Действие
                              </th>
                              <th
                                scope="col"
                                className="w-40 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                              >
                                Пользователь
                              </th>
                              <th
                                scope="col"
                                className="w-28 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                              >
                                Роль
                              </th>
                              <th
                                scope="col"
                                className="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                              >
                                Детали
                              </th>
                            </tr>
                          </thead>

                          <tbody>
                            {items.map((log) => (
                              <tr
                                key={log.id}
                                className={cn(
                                  "border-b border-[var(--border)] transition-colors hover:bg-[var(--bg-elevated-soft)]",
                                  log.action === "RECLASSIFY" &&
                                    ROW_HIGHLIGHT_RECLASSIFY,
                                  log.action === "SET_DEAL_PLAYBOOK" &&
                                    ROW_HIGHLIGHT_PLAYBOOK,
                                )}
                              >
                                <td className="px-3 py-2.5 text-xs text-[var(--text-secondary)]">
                                  {new Date(log.created_at).toLocaleString(
                                    "ru-RU",
                                    {
                                      day: "2-digit",
                                      month: "2-digit",
                                      year: "numeric",
                                      hour: "2-digit",
                                      minute: "2-digit",
                                      second: "2-digit",
                                    },
                                  )}
                                </td>

                                <td className="px-3 py-2.5">
                                  <div className="min-w-0">
                                    <span
                                      className="inline-flex max-w-full truncate rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-secondary)] align-middle"
                                      title={
                                        AUDIT_ACTION_LABEL[log.action] ||
                                        log.action
                                      }
                                    >
                                      {AUDIT_ACTION_LABEL[log.action] ||
                                        log.action}
                                    </span>
                                  </div>
                                </td>

                                <td
                                  className="truncate px-3 py-2.5 text-xs font-medium text-[var(--text-primary)]"
                                  title={log.actor}
                                >
                                  {log.actor}
                                </td>

                                <td
                                  className="truncate px-3 py-2.5 text-[11px] text-[var(--text-muted)]"
                                  title={log.actor_role}
                                >
                                  {log.actor_role}
                                </td>

                                <td className="max-w-[380px] px-3 py-2.5 text-[11px] text-[var(--text-secondary)]">
                                  <span
                                    className="block truncate"
                                    title={formatDetails(
                                      log.action,
                                      log.details as
                                        | Record<string, unknown>
                                        | null,
                                    )}
                                  >
                                    {formatDetails(
                                      log.action,
                                      log.details as
                                        | Record<string, unknown>
                                        | null,
                                    )}
                                  </span>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <div className="flex h-full items-center justify-center px-4 py-10 text-center">
                        <div>
                          <p className="mb-1 text-sm text-[var(--text-secondary)]">
                            Записи не найдены
                          </p>
                          <p className="text-xs text-[var(--text-muted)]">
                            Журнал пока пуст или не подходит под текущий фильтр.
                          </p>
                        </div>
                      </div>
                    )}
                  </div>

                  {totalPages > 1 && (
                    <div className="mt-4 flex shrink-0 flex-wrap items-center justify-center gap-3">
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        onClick={() => setPage((p) => Math.max(1, p - 1))}
                        disabled={page <= 1}
                        leftIcon={<ChevronLeft size={14} />}
                      >
                        Назад
                      </Button>

                      <span className="text-xs text-[var(--text-muted)]">
                        Страница {page} из {totalPages}
                      </span>

                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        onClick={() =>
                          setPage((p) => Math.min(totalPages, p + 1))
                        }
                        disabled={page >= totalPages}
                        rightIcon={<ChevronRight size={14} />}
                      >
                        Вперёд
                      </Button>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        )}
      </PageSection>
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
      details.reason && String(details.reason).trim().length > 0
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



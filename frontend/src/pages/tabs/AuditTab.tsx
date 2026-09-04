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
import { useTranslation } from "react-i18next";
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
  "bg-[color:color-mix(in_srgb,var(--color-blue)_6%,transparent)]";

const AuditActionFilterInlinePanel: React.FC<{
  selectedAction: string;
  onSelect: (value: string) => void;
  onReset: () => void;
  onClose: () => void;
}> = ({ selectedAction, onSelect, onReset, onClose }) => {
  const { t } = useTranslation(["projects", "common"]);

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated-soft)]">
      <div className="border-b border-[var(--border-subtle)] px-4 py-3">
        <p className="text-sm font-semibold text-[var(--text-primary)]">
          {t("auditTab.filter.title", { ns: "projects" })}
        </p>
        <p className="mt-0.5 text-[11px] text-[var(--text-muted)]">
          {t("auditTab.filter.subtitle", { ns: "projects" })}
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
            {t("auditTab.filter.allActions", { ns: "projects" })}
          </Button>

          {(Object.keys(AUDIT_ACTION_LABEL) as string[]).map((key: string) => {
            const isSelected = selectedAction === key;
            const label = t(`auditActions.${key}`, {
              ns: "common",
              defaultValue: AUDIT_ACTION_LABEL[key] ?? key,
            });

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
          {t("actions.reset", { ns: "common", defaultValue: "Reset" })}
        </Button>

        <div className="flex gap-2">
          <Button size="sm" variant="secondary" onClick={onClose}>
            {t("actions.close", { ns: "common", defaultValue: "Close" })}
          </Button>
        </div>
      </div>
    </div>
  );
};

export const AuditTab: React.FC<Props> = ({ dealId }) => {
  const { t, i18n } = useTranslation(["projects", "common"]);
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

  const currentFilterLabel = filterAction
    ? t("auditTab.filter.actionLabel", {
        ns: "projects",
        label: t(`auditActions.${filterAction}`, {
          ns: "common",
          defaultValue: AUDIT_ACTION_LABEL[filterAction] ?? filterAction,
        }),
      })
    : t("auditTab.filter.allActions", { ns: "projects" });

  if (!canViewAuditLog) {
    return (
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
        <div className="px-6 py-10">
          <div className="flex min-h-[320px] flex-col items-center justify-center text-center">
            <div className="mb-4 inline-flex h-14 w-14 items-center justify-center rounded-full bg-[var(--bg-elevated-soft)]">
              <Shield size={30} className="text-[var(--text-muted)]" />
            </div>

            <h2 className="text-base font-semibold text-[var(--text-primary)]">
              {t("auditTab.noAccess.title", { ns: "projects" })}
            </h2>

            <p className="mt-2 max-w-md text-sm text-[var(--text-muted)]">
              {t("auditTab.noAccess.description", { ns: "projects" })}
            </p>
          </div>
        </div>
      </section>
    );
  }

  return (
    <div className="flex flex-col lg:h-full lg:min-h-0">
      <PageSection
        title={
          viewMode === "audit_log"
            ? t("auditTab.modes.logTitle", { ns: "projects" })
            : t("auditTab.modes.classificationTitle", { ns: "projects" })
        }
        subtitle={
          viewMode === "audit_log"
            ? t("auditTab.modes.logSubtitle", { ns: "projects" })
            : t("auditTab.modes.classificationSubtitle", { ns: "projects" })
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
                className={
                  isActionFilterOpen ? FILTER_BUTTON_ACTIVE_CLASS : ""
                }
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
                {t("auditTab.buttons.toLog", { ns: "projects" })}
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
              {t("auditTab.buttons.toClassification", { ns: "projects" })}
            </Button>
          </div>
        }
        className="lg:flex-1 lg:min-h-0"
        contentClassName="flex flex-col lg:min-h-0 lg:flex-1"
        bodyClassName="flex flex-col lg:h-full lg:min-h-0"
      >
        {viewMode === "classification_audit" ? (
          <div className="flex flex-col lg:min-h-0 lg:flex-1">
            <ClassificationAuditView dealId={dealId} />
          </div>
        ) : (
          <div className="flex flex-col lg:h-full lg:min-h-0">
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

            <div className="flex flex-col lg:min-h-0 lg:flex-1">
              {isLoading ? (
                <div className="flex items-center justify-center rounded-xl border border-[var(--border)] bg-[var(--bg-card)] py-16 lg:flex-1">
                  <Loader2
                    className="mr-3 animate-spin text-[var(--accent-primary)]"
                    size={20}
                  />
                  <span className="text-sm text-[var(--text-muted)]">
                    {t("auditTab.loading", { ns: "projects" })}
                  </span>
                </div>
              ) : (
                <>
                  <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-card)] lg:min-h-0 lg:flex-1 lg:overflow-hidden">
                    {items.length > 0 ? (
                      <div className="overflow-x-auto lg:h-full lg:overflow-y-auto">
                        <table className="w-full table-fixed border-collapse">
                          <thead className="sticky top-0 z-10 border-b border-[var(--border)] bg-[var(--bg-elevated-soft)]">
                            <tr>
                              <th
                                scope="col"
                                className="w-48 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                              >
                                {t("auditTab.table.headers.time", { ns: "projects" })}
                              </th>
                              <th
                                scope="col"
                                className="w-52 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                              >
                                {t("auditTab.table.headers.action", { ns: "projects" })}
                              </th>
                              <th
                                scope="col"
                                className="w-40 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                              >
                                {t("auditTab.table.headers.user", { ns: "projects" })}
                              </th>
                              <th
                                scope="col"
                                className="w-28 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                              >
                                {t("auditTab.table.headers.role", { ns: "projects" })}
                              </th>
                              <th
                                scope="col"
                                className="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                              >
                                {t("auditTab.table.headers.details", { ns: "projects" })}
                              </th>
                            </tr>
                          </thead>

                          <tbody>
                            {items.map((log) => {
                              const actionLabel = t(`auditActions.${log.action}`, {
                                ns: "common",
                                defaultValue: AUDIT_ACTION_LABEL[log.action] ?? log.action,
                              });

                              return (
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
                                      i18n.language,
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
                                        title={actionLabel}
                                      >
                                        {actionLabel}
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
                                        log.details as Record<string, unknown> | null,
                                        (key, options) => String(t(key, options)),
                                      )}
                                    >
                                      {formatDetails(
                                        log.action,
                                        log.details as Record<string, unknown> | null,
                                        (key, options) => String(t(key, options)),
                                      )}
                                    </span>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <div className="flex items-center justify-center px-4 py-10 text-center lg:h-full">
                        <div>
                          <p className="mb-1 text-sm text-[var(--text-secondary)]">
                            {t("auditTab.emptyState.title", { ns: "projects" })}
                          </p>
                          <p className="text-xs text-[var(--text-muted)]">
                            {t("auditTab.emptyState.subtitle", { ns: "projects" })}
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
                        {t("actions.back", { ns: "common", defaultValue: "Back" })}
                      </Button>

                      <span className="text-xs text-[var(--text-muted)]">
                        {t("auditTab.pagination.pageInfo", {
                          ns: "projects",
                          current: page,
                          total: totalPages
                        })}
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
                        {t("actions.forward", { ns: "common", defaultValue: "Forward" })}
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
type TranslateFn = (key: string, options?: Record<string, unknown>) => string;

function formatDetails(
  action: string,
  details: Record<string, unknown> | null,
  tFn: TranslateFn,
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
    const reasonLabel = tFn("auditTab.format.reason", { ns: "projects" });
    const reason =
      details.reason && String(details.reason).trim().length > 0
        ? ` · ${reasonLabel}: ${String(details.reason)}`
        : "";
    return `${prev} → ${next}${reason}`;
  }

  return Object.entries(details)
    .filter(([k]) => !["document_id"].includes(k))
    .map(([k, v]) => `${k}: ${String(v)}`)
    .join(", ");
}

export default AuditTab;



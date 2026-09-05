// =============================================================
// src/components/requests/RequestsTable.tsx
// =============================================================

import React, { useMemo, useState, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { DDRequest } from "../../types";
import { toRequestTableRowFromLegacy } from "../../viewAdapters/requestPresentation";
import { RequestPriorityBadge } from "./shared/RequestPriorityBadge";
import { Search, Plus, Download, FileText } from "lucide-react";
import Button from "../ui/Button";
import { REQUEST_PRIORITY_ORDER } from "../../types/requestPriority";

interface Props {
  requests: DDRequest[];
  selectedRequestId?: string | null;
  onRowClick: (request: DDRequest, rowElement: HTMLElement | null) => void;
  onCreateClick: () => void;
  onExportWord: () => Promise<void>;
  onExportExcel: () => Promise<void>;
  canManageRequests: boolean;
}

type SortKey = "priority" | "status" | "created";

function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

const statusToneClass = (statusCode?: string | null): string => {
  if (!statusCode) {
    return "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-muted)]";
  }

  const code = statusCode.toLowerCase();

  if (code === "open") {
    return "border-[color:color-mix(in_oklab,var(--color-blue)_22%,transparent)] bg-[var(--color-blue-highlight)] text-[var(--color-blue)]";
  }

  if (code === "in_progress" || code === "progress" || code === "processing") {
    return "border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] text-[var(--color-warning-text)]";
  }

  if (code === "resolved" || code === "done" || code === "closed") {
    return "border-[var(--color-success-border)] bg-[var(--color-success-bg)] text-[var(--color-success-text)]";
  }

  return "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)]";
};

export const RequestsTable: React.FC<Props> = ({
  requests,
  selectedRequestId,
  onRowClick,
  onCreateClick,
  onExportWord,
  onExportExcel,
  canManageRequests,
}) => {
  const { t, i18n } = useTranslation("requests");
  const [searchText, setSearchText] = useState("");
  const [sortBy, setSortBy] = useState<SortKey>("priority");

  const rowRefs = useRef<Map<string, HTMLTableRowElement>>(new Map());

  const viewModels = useMemo(
    () =>
      requests.map((req) => ({
        dto: req,
        view: toRequestTableRowFromLegacy(req, t),
      })),
    [requests, t],
  );

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
          (REQUEST_PRIORITY_ORDER[a.view.priority] ?? 9) -
          (REQUEST_PRIORITY_ORDER[b.view.priority] ?? 9)
        );
      }

      if (sortBy === "status") {
        return (a.view.statusLabel ?? "").localeCompare(
          b.view.statusLabel ?? "",
          i18n.language,
        );
      }

      return (
        new Date(b.dto.created_at).getTime() -
        new Date(a.dto.created_at).getTime()
      );
    });

    return list;
  }, [viewModels, searchText, sortBy, i18n.language]);

  const columns: Array<[string, string, string]> = [
    ["priority", t("table.columns.priority"), "w-28"],
    ["text", t("table.columns.text"), ""],
    ["docs", t("table.columns.documents"), "w-28"],
    ["status", t("table.columns.status"), "w-32"],
    ["source", t("table.columns.source"), "w-40"],
  ];

  return (
    <section
      className="flex h-full min-h-0 flex-col gap-3 overflow-hidden"
      aria-labelledby="requests-table-title"
    >
      {/* Шапка */}
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-faint)]">
            {t("table.eyebrow")}
          </p>
          <h2
            id="requests-table-title"
            className="mt-1 text-sm font-semibold text-[var(--text-primary)]"
          >
            {t("table.title")}
            <span className="ml-1 text-[var(--text-muted)]">
              ({requests.length})
            </span>
          </h2>
        </div>

        <div className="flex flex-wrap gap-2">
          {canManageRequests && (
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={onCreateClick}
              leftIcon={<Plus className="h-4 w-4" />}
            >
              {t("table.newRequest")}
            </Button>
          )}

          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={onExportWord}
            leftIcon={<FileText className="h-4 w-4" />}
          >
            Word
          </Button>

          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={onExportExcel}
            leftIcon={<Download className="h-4 w-4" />}
          >
            Excel
          </Button>
        </div>
      </div>

      {/* Поиск */}
      <div className="relative shrink-0">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
          size={16}
          aria-hidden="true"
        />
        <input
          type="text"
          placeholder={t("table.searchPlaceholder")}
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          className="mt-1 w-full rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-9 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
          aria-label={t("table.searchAria")}
        />
      </div>

      {/* Таблица */}
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)]">
        <div className="min-h-0 flex-1 overflow-auto">
          <table className="w-full border-collapse text-left">
            <thead className="border-b border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)]">
              <tr>
                {columns.map(([key, label, width]) => (
                  <th
                    key={key}
                    scope="col"
                    className={cn(
                      "px-3 py-2.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]",
                      width,
                    )}
                  >
                    {key === "priority" || key === "status" ? (
                      <button
                        type="button"
                        onClick={() => setSortBy(key as SortKey)}
                        className={cn(
                          "inline-flex items-center gap-1 transition-colors hover:text-[var(--text-secondary)]",
                          sortBy === key &&
                            "text-[var(--accent-primary)] underline underline-offset-4",
                        )}
                      >
                        <span>{label}</span>
                      </button>
                    ) : (
                      label
                    )}
                  </th>
                ))}
              </tr>
            </thead>

            <tbody>
              {filtered.map((item) => {
                const { dto, view } = item;
                const isSelected = selectedRequestId === view.id;

                return (
                  <tr
                    key={view.id}
                    ref={(el) => {
                      if (el) {
                        rowRefs.current.set(view.id, el);
                      } else {
                        rowRefs.current.delete(view.id);
                      }
                    }}
                    className={cn(
                      "cursor-pointer border-b border-[var(--border-subtle)] transition-colors last:border-b-0",
                      isSelected
                        ? "bg-[var(--bg-elevated-soft)]"
                        : "hover:bg-[var(--bg-elevated-soft)]",
                    )}
                    onClick={() =>
                      onRowClick(dto, rowRefs.current.get(view.id) ?? null)
                    }
                    aria-selected={isSelected}
                  >
                    <td
                      className={cn(
                        "px-3 py-2.5 align-top",
                        isSelected &&
                          "shadow-[inset_3px_0_0_var(--accent-primary)]",
                      )}
                    >
                      <RequestPriorityBadge priority={view.priority} size="sm" />
                    </td>

                    <td className="px-3 py-2.5 align-top">
                      <p className="line-clamp-2 text-sm text-[var(--text-primary)]">
                        {view.text}
                      </p>
                      {view.checkLabel && (
                        <p className="mt-0.5 text-[12px] text-[var(--text-muted)]">
                          {t("table.checkPrefix", { label: view.checkLabel })}
                        </p>
                      )}
                    </td>

                    <td className="px-3 py-2.5 align-top text-sm text-[var(--text-secondary)]">
                      {t("table.docsSuffix", { count: view.documentCount })}
                    </td>

                    <td className="px-3 py-2.5 align-top">
                      {view.statusLabel ? (
                        <span
                          className={cn(
                            "inline-flex max-w-full items-center rounded-full border px-2 py-0.5 text-xs font-medium",
                            statusToneClass(dto.status),
                          )}
                        >
                          <span className="truncate">{view.statusLabel}</span>
                        </span>
                      ) : (
                        <span className="text-xs text-[var(--text-muted)]">—</span>
                      )}
                    </td>

                    <td className="px-3 py-2.5 align-top">
                      {view.sourceLabel && view.sourceColorClass ? (
                        <span
                          className={cn(
                            "inline-flex max-w-full items-center rounded-full px-2 py-0.5 text-xs font-medium",
                            view.sourceColorClass,
                          )}
                        >
                          <span className="truncate">{view.sourceLabel}</span>
                        </span>
                      ) : (
                        <span className="text-xs text-[var(--text-muted)]">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {filtered.length === 0 && (
          <div className="shrink-0 border-t border-[var(--border-subtle)] px-6 py-10 text-center">
            <p className="mb-1 text-sm text-[var(--text-secondary)]">
              {t("table.empty.title")}
            </p>
            <p className="text-[12px] text-[var(--text-muted)]">
              {requests.length === 0
                ? t("table.empty.descNoRequests")
                : t("table.empty.descFiltered")}
            </p>
          </div>
        )}
      </div>
    </section>
  );
};

export default RequestsTable;



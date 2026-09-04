// =============================================================
// src/components/requests/ReviewRequestsTable.tsx
// =============================================================

import React, { useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { DDRequestDTO } from "../../types/dealReview";
import { toRequestTableRowFromReview } from "../../viewAdapters/requestPresentation";
import { RequestPriorityBadge } from "./shared/RequestPriorityBadge";
import { Search } from "lucide-react";
import { REQUEST_PRIORITY_ORDER } from "../../types/requestPriority";

interface Props {
  requests: DDRequestDTO[];
  selectedRequestId?: string | null;
  onRowClick: (request: DDRequestDTO, rowElement: HTMLElement | null) => void;
}

function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

export const ReviewRequestsTable: React.FC<Props> = ({
  requests,
  selectedRequestId,
  onRowClick,
}) => {
  const { t, i18n } = useTranslation("requests");
  const [searchText, setSearchText] = useState("");

  const rowRefs = useRef<Map<string, HTMLTableRowElement>>(new Map());

  const viewModels = useMemo(
    () =>
      requests.map((req) => ({
        dto: req,
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
        const docsLabel = view.documentsLabel?.toLowerCase() ?? "";

        return (
          text.includes(lower) ||
          checkLabel.includes(lower) ||
          addressee.includes(lower) ||
          docsLabel.includes(lower)
        );
      });
    }

    list.sort((a, b) => {
      const pa = REQUEST_PRIORITY_ORDER[a.view.priority] ?? 9;
      const pb = REQUEST_PRIORITY_ORDER[b.view.priority] ?? 9;

      if (pa !== pb) return pa - pb;

      return (a.view.checkLabel ?? "").localeCompare(
        b.view.checkLabel ?? "",
        i18n.language,
      );
    });

    return list;
  }, [viewModels, searchText, i18n.language]);

  return (
    <section className="flex h-full min-h-0 flex-col gap-2 overflow-hidden">
      {/* Поиск */}
      <div className="relative shrink-0">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
          size={16}
          aria-hidden="true"
        />
        <input
          type="text"
          placeholder={t("reviewTable.searchPlaceholder")}
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          className="mt-1 w-full rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-card)] px-9 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
          aria-label={t("reviewTable.searchAria")}
        />
      </div>

      {/* Таблица */}
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-card)]">
        <div className="min-h-0 flex-1 overflow-auto">
          <table className="w-full table-fixed border-collapse">
            <thead className="border-b border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)]">
              <tr>
                <th
                  scope="col"
                  className="w-28 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                  aria-sort="ascending"
                >
                  {t("reviewTable.columns.priority")}
                </th>
                <th
                  scope="col"
                  className="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                >
                  {t("reviewTable.columns.text")}
                </th>
                <th
                  scope="col"
                  className="w-48 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                >
                  {t("reviewTable.columns.documents")}
                </th>
                <th
                  scope="col"
                  className="w-36 px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]"
                >
                  {t("reviewTable.columns.segment")}
                </th>
              </tr>
            </thead>

            <tbody>
              {filtered.map(({ dto, view }) => {
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
                          {view.checkLabel}
                        </p>
                      )}

                      {view.addressee && (
                        <p className="mt-1 text-[12px] text-[var(--text-secondary)]">
                          {t("reviewTable.addresseePrefix", { name: view.addressee })}
                        </p>
                      )}
                    </td>

                    <td className="px-3 py-2.5 align-top">
                      {view.documentsLabel ? (
                        <span className="line-clamp-2 text-[12px] leading-5 text-[var(--text-secondary)]">
                          {view.documentsLabel}
                        </span>
                      ) : (
                        <span className="text-xs text-[var(--text-muted)]">—</span>
                      )}
                    </td>

                    <td className="px-3 py-2.5 align-top">
                      {view.hasSegmentContext ? (
                        <div className="flex flex-col gap-1">
                          {view.segmentTitle && (
                            <span className="line-clamp-1 text-[12px] text-[var(--text-secondary)]">
                              {view.segmentTitle}
                            </span>
                          )}

                          {view.chunkIndex != null && (
                            <span
                              className={cn(
                                "inline-flex w-fit items-center rounded-full border px-2 py-0.5 text-[10px] font-medium",
                                "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-muted)]",
                              )}
                            >
                              Chunk #{view.chunkIndex}
                            </span>
                          )}
                        </div>
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
          <div className="shrink-0 border-t border-[var(--border-subtle)] px-4 py-10 text-center">
            <p className="mb-1 text-sm text-[var(--text-secondary)]">
              {t("reviewTable.empty.title")}
            </p>
            <p className="text-[12px] text-[var(--text-muted)]">
              {requests.length === 0
                ? t("reviewTable.empty.descNoRequests")
                : t("reviewTable.empty.descFiltered")}
            </p>
          </div>
        )}
      </div>
    </section>
  );
};

export default ReviewRequestsTable;



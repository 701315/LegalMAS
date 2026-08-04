// =============================================================
// src/components/DealCard.tsx
// Карточка сделки для списка (DealListPage).
// Приведено к единому product-дизайну workspace.
// =============================================================

import React from "react";
import type { Deal } from "../types";
import { timeAgo } from "../utils";

interface Props {
  deal: Deal;
  onClick?: () => void;
  isActive?: boolean;
}

function getChecksModeLabel(mode?: string | null) {
  if (!mode) return null;
  if (mode === "global_and_doc_type") return "Плейбук + типы документов";
  if (mode === "global_only") return "Только плейбук";
  if (mode === "doc_type_only") return "Только типы документов";
  return mode;
}

function getStatusTone(status?: string | null) {
  switch (status) {
    case "completed":
      return (
        "bg-[var(--color-success-bg)] " +
        "text-[var(--color-success-text)] " +
        "border-[var(--color-success-border)]"
      );
    case "in_progress":
      return (
        "bg-[var(--accent-muted)] " +
        "text-[var(--accent-primary)] " +
        "border-[color:color-mix(in_oklab,var(--accent-primary)_20%,transparent)]"
      );
    case "draft":
    case "created":
    default:
      return (
        "bg-[var(--bg-elevated-soft)] " +
        "text-[var(--text-secondary)] " +
        "border-[var(--border-soft)]"
      );
  }
}

const DealCard: React.FC<Props> = ({ deal, onClick, isActive = false }) => {
  const checksModeLabel = getChecksModeLabel(deal.last_run_checks_mode);

  const stateClasses = isActive
    ? "border-[var(--accent-primary)] bg-[var(--accent-muted)]/40 shadow-md ring-1 ring-[var(--accent-primary)]/10"
    : "border-[var(--border)] bg-[var(--bg-card)] hover:border-[var(--border-strong)] hover:bg-[var(--bg-card-hover)] hover:-translate-y-0.5 hover:shadow-md";

  const interactiveProps = onClick
    ? {
        role: "button" as const,
        tabIndex: 0,
        onClick,
        onKeyDown: (e: React.KeyboardEvent<HTMLDivElement>) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onClick();
          }
        },
      }
    : {};

  return (
    <div
      {...interactiveProps}
      className={[
        "w-full rounded-[24px] border p-4 transition-all duration-200",
        onClick
          ? "cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]"
          : "cursor-default",
        stateClasses,
      ].join(" ")}
      aria-label={onClick ? `Открыть проект ${deal.name}` : undefined}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
            Project
          </div>
          <h2 className="mt-1 truncate text-base font-semibold tracking-tight text-[var(--text-primary)]">
            {deal.name}
          </h2>
        </div>

        <span className="shrink-0 rounded-full border border-[var(--border-soft)] bg-[var(--bg-base)] px-2.5 py-1 font-mono text-[11px] text-[var(--text-muted)]">
          #{deal.id}
        </span>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <span
          className={[
            "inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium",
            getStatusTone(deal.status),
          ].join(" ")}
        >
          {deal.status}
        </span>

        {deal.last_run_id ? (
          <span className="inline-flex items-center rounded-full border border-[var(--border-soft)] bg-[var(--bg-base)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)]">
            run {deal.last_run_id}
          </span>
        ) : (
          <span className="inline-flex items-center rounded-full border border-[var(--border-soft)] bg-[var(--bg-base)] px-2.5 py-1 text-[11px] text-[var(--text-muted)]">
            Без запуска анализа
          </span>
        )}
      </div>

      <div className="mt-4 space-y-2 rounded-[18px] border border-[var(--border-soft)] bg-[var(--bg-base)] px-3 py-3">
        {deal.last_run_id ? (
          <>
            <div className="text-xs text-[var(--text-secondary)]">
              <span className="text-[var(--text-muted)]">Последний анализ:</span>{" "}
              <span className="font-medium text-[var(--text-primary)]">
                run {deal.last_run_id}
              </span>
            </div>

            {checksModeLabel && (
              <div className="text-xs text-[var(--text-secondary)]">
                <span className="text-[var(--text-muted)]">Режим проверок:</span>{" "}
                <span className="font-medium text-[var(--text-primary)]">
                  {checksModeLabel}
                </span>
              </div>
            )}

            {deal.last_run_pipeline_strategy && (
              <div className="text-xs text-[var(--text-secondary)]">
                <span className="text-[var(--text-muted)]">Стратегия пайплайна:</span>{" "}
                <span className="font-medium text-[var(--text-primary)]">
                  {deal.last_run_pipeline_strategy}
                </span>
              </div>
            )}
          </>
        ) : (
          <p className="text-xs leading-5 text-[var(--text-muted)]">
            Анализ по этой сделке ещё не запускался.
          </p>
        )}
      </div>

      <div className="mt-4 flex items-center justify-between gap-2 border-t border-[var(--border-soft)] pt-3">
        <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
          Updated
        </span>
        <span className="text-xs text-[var(--text-secondary)]">
          {timeAgo(deal.updated_at ?? undefined)}
        </span>
      </div>
    </div>
  );
};

export default DealCard;



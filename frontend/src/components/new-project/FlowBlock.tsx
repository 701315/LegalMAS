// =============================================================
// src/components/new-project/FlowBlock.tsx
//
// Wrapper for an individual step in the new project creation flow.
//
// Three states:
//   disabled — step is not yet available (reduced opacity, no interaction)
//   active   — current active step (accent stripe on the left)
//              + optional "Back to step N" button in the header
//   done     — step is completed; collapsed to a single line with checkmark,
//              summary, and edit pencil button
//
// Pure presentation wrapper containing no business logic.
// =============================================================

import React from "react";
import { ArrowLeft, Pencil } from "lucide-react";
import { useTranslation } from "react-i18next";

export type FlowBlockStatus = "disabled" | "active" | "done";

interface FlowBlockProps {
  /** Step order number for display */
  step: number;
  /** Block title */
  title: string;
  /** Block state */
  status: FlowBlockStatus;
  /**
   * Short summary for the done state.
   * Displayed inline to the right of the title.
   */
  summary?: string;
  /** Block content (form, list, etc.) */
  children: React.ReactNode;

  /**
   * Click handler for the "Back to step N" button in the active block header.
   * If omitted, the button is not rendered.
   */
  onBackRequest?: () => void;
  /**
   * Label for the back button. For example: "Back to step 3".
   * Required if onBackRequest is provided.
   */
  backLabel?: string;

  /**
   * Click handler for the pencil/edit button in the done block.
   * If omitted, the button is not rendered.
   */
  onEditRequest?: () => void;
}

const FlowBlock: React.FC<FlowBlockProps> = ({
  step,
  title,
  status,
  summary,
  children,
  onBackRequest,
  backLabel,
  onEditRequest,
}) => {
  const { t } = useTranslation("projects");

  const isDone = status === "done";
  const isDisabled = status === "disabled";
  const isActive = status === "active";

  const showContent = isActive;

  return (
    <div
      className={[
        "relative rounded-2xl border bg-[var(--bg-card)] shadow-sm transition-opacity duration-200",
        isDisabled
          ? "border-[var(--border)] opacity-50"
          : isActive
            ? "border-[var(--accent-primary)]/40"
            : "border-[var(--border)]",
      ]
        .filter(Boolean)
        .join(" ")}
      aria-disabled={isDisabled}
    >
      {/* Left accent stripe — active state only */}
      {isActive && (
        <div
          className="absolute left-0 top-4 bottom-4 w-[3px] rounded-full bg-[var(--accent-primary)]"
          aria-hidden="true"
        />
      )}

      {/* ── Back button in active block header ──────────── */}
      {isActive && onBackRequest && backLabel ? (
        <div className="border-b border-[var(--border-subtle)] px-5 pb-2 pt-3">
          <button
            type="button"
            onClick={onBackRequest}
            className="inline-flex items-center gap-1.5 rounded-md text-[11px] font-medium text-[var(--text-muted)] transition-colors hover:text-[var(--accent-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
          >
            <ArrowLeft className="h-3 w-3" aria-hidden="true" />
            {backLabel}
          </button>
        </div>
      ) : null}

      {/* ── Header ───────────────────────────────────────── */}
      <div className="flex items-center gap-4 px-5 py-4">
        {/* Step indicator */}
        <div
          className={[
            "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold transition-colors",
            isDone
              ? "bg-[var(--accent-primary)] text-white"
              : isActive
                ? "border-2 border-[var(--accent-primary)] text-[var(--accent-primary)]"
                : "border border-[var(--border)] text-[var(--text-muted)]",
          ]
            .filter(Boolean)
            .join(" ")}
          aria-hidden="true"
        >
          {isDone ? (
            <svg
              viewBox="0 0 12 12"
              fill="none"
              className="h-3.5 w-3.5"
              aria-hidden="true"
            >
              <path
                d="M2 6l3 3 5-5"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          ) : (
            step
          )}
        </div>

        {/* Title + inline summary for done state */}
        <div className="min-w-0 flex-1">
          {isDone && summary ? (
            <div className="flex items-center gap-2 min-w-0">
              <h2 className="text-sm font-semibold text-[var(--text-primary)] shrink-0">
                {title}
              </h2>
              <span
                className="shrink-0 text-[var(--text-faint)]"
                aria-hidden="true"
              >
                ·
              </span>
              <p
                className="min-w-0 truncate text-[12px] text-[var(--text-secondary)]"
                title={summary}
              >
                {summary}
              </p>
            </div>
          ) : (
            <h2
              className={[
                "text-sm font-semibold",
                isDisabled
                  ? "text-[var(--text-muted)]"
                  : "text-[var(--text-primary)]",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              {title}
            </h2>
          )}
        </div>

        {/* Done state edit pencil button */}
        {isDone && onEditRequest ? (
          <button
            type="button"
            onClick={onEditRequest}
            aria-label={t("newProject.editStepAria", { title })}
            className="shrink-0 rounded-md p-1.5 text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-elevated-soft)] hover:text-[var(--accent-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]"
          >
            <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        ) : null}
      </div>

      {/* ── Content (active state only) ─────────────────── */}
      {showContent && (
        <>
          <div className="mx-5 border-t border-[var(--border-subtle)]" />
          <div className="px-5 py-5">{children}</div>
        </>
      )}
    </div>
  );
};

export default FlowBlock;



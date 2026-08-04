// =============================================================
// src/components/qc/QCCellRenderer.tsx
// =============================================================

import React from "react";
import type { CheckResult, QCStatus } from "../../types";

interface QCCellRendererProps {
  value: QCStatus | undefined;
  data: CheckResult;
  onQcChange?: (
    result: CheckResult,
    newStatus: "approved" | "rejected",
  ) => void;
}

function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

const STATUS_META: Record<
  QCStatus,
  {
    label: string;
    chipClass: string;
  }
> = {
  pending: {
    label: "Pending",
    chipClass:
      "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)]",
  },
  approved: {
    label: "Approved",
    chipClass:
      "border-[var(--color-success-border)] bg-[var(--color-success-bg)] text-[var(--color-success-text)]",
  },
  rejected: {
    label: "Rejected",
    chipClass:
      "border-[var(--color-error-border)] bg-[var(--color-error-bg)] text-[var(--color-error-text)]",
  },
  needs_review: {
    label: "Needs review",
    chipClass:
      "border-[color:color-mix(in_srgb,var(--color-gold)_24%,transparent)] bg-[var(--color-gold-highlight)] text-[var(--color-gold-text)]",
  },
};

export const QCCellRenderer: React.FC<QCCellRendererProps> = ({
  value,
  data,
  onQcChange,
}) => {
  const label: QCStatus = value ?? "pending";
  const meta = STATUS_META[label];
  const isPending = label === "pending";

  const handleApprove = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    onQcChange?.(data, "approved");
  };

  const handleReject = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    onQcChange?.(data, "rejected");
  };

  return (
    <div className="flex items-center gap-2">
      <span
        className={cn(
          "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium leading-none",
          meta.chipClass,
        )}
        title={`QC status: ${meta.label}`}
      >
        {meta.label}
      </span>

      {onQcChange && (
        <div className="flex items-center gap-1">
          <button
            type="button"
            className={cn(
              "inline-flex h-5 w-5 items-center justify-center rounded border text-[10px] leading-none transition",
              "border-[var(--color-success-border)] bg-[var(--color-success-bg)] text-[var(--color-success-text)]",
              "hover:opacity-80",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]",
              "disabled:cursor-not-allowed disabled:opacity-40",
            )}
            onClick={handleApprove}
            title="Подтвердить (QC approve)"
            disabled={!isPending}
            aria-label="Подтвердить QC"
          >
            ✓
          </button>

          <button
            type="button"
            className={cn(
              "inline-flex h-5 w-5 items-center justify-center rounded border text-[10px] leading-none transition",
              "border-[var(--color-error-border)] bg-[var(--color-error-bg)] text-[var(--color-error-text)]",
              "hover:opacity-80",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]/35 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-card)]",
              "disabled:cursor-not-allowed disabled:opacity-40",
            )}
            onClick={handleReject}
            title="Отклонить (QC reject)"
            disabled={!isPending}
            aria-label="Отклонить QC"
          >
            ✕
          </button>
        </div>
      )}
    </div>
  );
};

export default QCCellRenderer;


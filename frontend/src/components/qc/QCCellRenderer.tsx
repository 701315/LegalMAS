// =============================================================
// src/components/qc/QCCellRenderer.tsx
// Отдельная колонка QC-статуса + быстрые действия.
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
    textClass: string;
    chipClass: string;
  }
> = {
  pending: {
    label: "Pending",
    textClass: "text-[var(--text-secondary)]",
    chipClass:
      "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)]",
  },
  approved: {
    label: "Approved",
    textClass: "text-[var(--success)]",
    chipClass:
      "border-[color:color-mix(in_srgb,var(--success)_22%,transparent)] bg-[color:color-mix(in_srgb,var(--success)_10%,white)] text-[var(--success)]",
  },
  rejected: {
    label: "Rejected",
    textClass: "text-[var(--color-error)]",
    chipClass:
      "border-[color:color-mix(in_srgb,var(--color-error)_22%,transparent)] bg-[var(--color-error-highlight)] text-[var(--color-error)]",
  },
  needs_review: {
    label: "Needs review",
    textClass: "text-[var(--color-orange)]",
    chipClass:
      "border-[color:color-mix(in_srgb,var(--color-orange)_22%,transparent)] bg-[var(--color-orange-highlight)] text-[var(--color-orange)]",
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
              "border-[color:color-mix(in_srgb,var(--success)_22%,transparent)] text-[var(--success)]",
              "hover:bg-[color:color-mix(in_srgb,var(--success)_10%,white)]",
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
              "border-[color:color-mix(in_srgb,var(--color-error)_22%,transparent)] text-[var(--color-error)]",
              "hover:bg-[var(--color-error-highlight)]",
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



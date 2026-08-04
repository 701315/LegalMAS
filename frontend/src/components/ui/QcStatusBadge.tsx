// src/components/ui/QcStatusBadge.tsx

import React from "react";
import { CheckCircle2, Clock, RotateCcw, ShieldAlert } from "lucide-react";
import type { ReviewQcStatus } from "../../types/dealReview";

interface QcStatusBadgeProps {
  status: ReviewQcStatus | string | null | undefined;
  size?: "xs" | "sm";
  className?: string;
}

interface QcStatusVisual {
  label: string;
  toneClass: string;
  icon: React.ReactNode;
}

function getVisual(
  status: ReviewQcStatus | string | null | undefined,
  iconSize: number,
): QcStatusVisual | null {
  if (!status) return null;

  switch (status) {
    case "approved":
      return {
        label: "Approved",
        toneClass:
          "border-[var(--color-success-border)] " +
          "bg-[var(--color-success-bg)] " +
          "text-[var(--color-success-text)]",
        icon: <CheckCircle2 width={iconSize} height={iconSize} />,
      };
    case "rejected":
      return {
        label: "Rejected",
        toneClass:
          "border-[var(--color-error-border)] " +
          "bg-[var(--color-error-bg)] " +
          "text-[var(--color-error-text)]",
        icon: <ShieldAlert width={iconSize} height={iconSize} />,
      };
    case "needs_review":
      return {
        label: "Needs review",
        toneClass:
          "border-[var(--color-warning-border)] " +
          "bg-[var(--color-warning-bg)] " +
          "text-[var(--color-warning-text)]",
        icon: <RotateCcw width={iconSize} height={iconSize} />,
      };
    case "pending":
      return null;
    default:
      return {
        label: String(status),
        toneClass:
          "border-[var(--border-subtle)] " +
          "bg-[var(--bg-elevated-soft)] " +
          "text-[var(--text-secondary)]",
        icon: <Clock width={iconSize} height={iconSize} />,
      };
  }
}

export const QcStatusBadge: React.FC<QcStatusBadgeProps> = ({
  status,
  size = "xs",
  className,
}) => {
  const iconSize = size === "sm" ? 12 : 10;
  const visual = getVisual(status, iconSize);
  if (!visual) return null;

  const sizeClass =
    size === "sm"
      ? "px-2 py-0.5 text-[11px]"
      : "px-1.5 py-0.5 text-[10px]";

  return (
    <span
      className={[
        "inline-flex items-center gap-1 rounded-full border font-medium leading-none",
        sizeClass,
        visual.toneClass,
        className ?? "",
      ]
        .filter(Boolean)
        .join(" ")}
      title={`QC: ${visual.label}`}
    >
      {visual.icon}
      <span>{visual.label}</span>
    </span>
  );
};

export default QcStatusBadge;



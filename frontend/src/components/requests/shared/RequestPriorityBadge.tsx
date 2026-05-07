// =============================================================
// src/components/requests/shared/RequestPriorityBadge.tsx
// Shared UI компонент для отображения приоритета DD-запроса.
// =============================================================

import React from "react";
import type { RequestPriority } from "../../../types/requestPriority";
import { REQUEST_PRIORITY_META } from "../../../types/requestPriority";

interface RequestPriorityBadgeProps {
  priority: RequestPriority;
  size?: "sm" | "md";
  className?: string;
}

function cn(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

const PRIORITY_TONE: Record<RequestPriority, string> = {
  critical:
    "border-[color:color-mix(in_oklab,var(--color-error)_22%,transparent)] bg-[var(--color-error-highlight)] text-[var(--color-error)]",
  high:
    "border-[color:color-mix(in_oklab,var(--color-orange)_22%,transparent)] bg-[var(--color-orange-highlight)] text-[var(--color-orange)]",
  medium:
    "border-[color:color-mix(in_oklab,var(--color-gold)_22%,transparent)] bg-[var(--color-gold-highlight)] text-[var(--color-gold-hover)]",
  low:
    "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)]",
};

const PRIORITY_DOT_TONE: Record<RequestPriority, string> = {
  critical: "bg-[var(--color-error)]",
  high: "bg-[var(--color-orange)]",
  medium: "bg-[var(--color-gold)]",
  low: "bg-[var(--text-muted)]",
};

/**
 * Отображает цветную плашку с приоритетом запроса.
 */
export const RequestPriorityBadge: React.FC<RequestPriorityBadgeProps> = ({
  priority,
  size = "md",
  className = "",
}) => {
  const config =
    REQUEST_PRIORITY_META[priority] ?? REQUEST_PRIORITY_META.medium;

  const toneClass = PRIORITY_TONE[priority] ?? PRIORITY_TONE.medium;
  const dotToneClass = PRIORITY_DOT_TONE[priority] ?? PRIORITY_DOT_TONE.medium;

  const sizeClass =
    size === "sm"
      ? "min-h-6 gap-1.5 px-2 py-0.5 text-[11px]"
      : "min-h-7 gap-1.5 px-2.5 py-1 text-xs";

  const dotClass = size === "sm" ? "h-1.5 w-1.5" : "h-2 w-2";

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border font-semibold whitespace-nowrap",
        toneClass,
        sizeClass,
        className,
      )}
      aria-label={`Приоритет: ${config.label}`}
    >
      <span
        className={cn("shrink-0 rounded-full", dotToneClass, dotClass)}
        aria-hidden="true"
      />
      <span>{config.label}</span>
    </span>
  );
};

export default RequestPriorityBadge;




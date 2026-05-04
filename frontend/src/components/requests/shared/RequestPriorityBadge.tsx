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
    "border-[color:color-mix(in_srgb,var(--color-error)_22%,transparent)] bg-[var(--color-error-highlight)] text-[var(--color-error)]",
  high:
    "border-[color:color-mix(in_srgb,var(--color-orange)_22%,transparent)] bg-[var(--color-orange-highlight)] text-[var(--color-orange)]",
  medium:
    "border-[color:color-mix(in_srgb,var(--color-gold)_22%,transparent)] bg-[var(--color-gold-highlight)] text-[var(--color-gold-hover)]",
  low:
    "border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] text-[var(--text-secondary)]",
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

  const sizeClass =
    size === "sm"
      ? "px-2 py-0.5 text-[11px]"
      : "px-2 py-1 text-xs";

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border font-semibold whitespace-nowrap",
        toneClass,
        sizeClass,
        className,
      )}
      title={`Приоритет: ${config.label}`}
    >
      {config.label}
    </span>
  );
};

export default RequestPriorityBadge;


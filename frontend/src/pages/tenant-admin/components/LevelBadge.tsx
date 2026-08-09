// =============================================================
// src/pages/tenant-admin/components/LevelBadge.tsx
//
// Badge для отображения log level (error/warning/info/critical/etc).
// Автоматически нормализует incoming level (напр., "warn" → "warning")
// и применяет семантическую окраску.
//
// Design contract:
// - Rounded pill shape (rounded-full)
// - Uppercase text для visual consistency
// - Border + subtle background в соответствии с level severity
// - Fallback на info-стиль для unknown levels
// =============================================================

import React from "react";
import { normLevel } from "../utils";

export interface LevelBadgeProps {
  /** Log level string, может быть null/undefined — тогда fallback на "info" */
  level: string | null | undefined;
}

const LevelBadge: React.FC<LevelBadgeProps> = ({ level }) => {
  const n = normLevel(level);

  const cls =
    n === "error" || n === "critical"
      ? "border-[var(--color-error-border)] bg-[var(--color-error-bg)] text-[var(--color-error-text)]"
      : n === "warning"
        ? "border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] text-[var(--color-warning-text)]"
        : "border-[color:color-mix(in_oklab,var(--color-blue)_25%,transparent)] bg-[var(--color-blue-highlight)] text-[var(--color-blue-strong)]";

  return (
    <span
      className={`inline-flex rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.06em] ${cls}`}
    >
      {n}
    </span>
  );
};

export default LevelBadge;



// =============================================================
// src/pages/tenant-admin/components/KpiCard.tsx
//
// Compact KPI card for displaying a metric (label + value + optional sub).
// Used across all admin panel tabs: Monitoring, Overview, Logs.
//
// Design contract:
// - Constrained height — all cards in a grid share the same height
// - Truncation on value and sub — prevents overflow with long values
// - Tone parameter for semantic value coloring (default | ok | warn | error)
// =============================================================

import React from "react";
import { LABEL_XS } from "../constants";
import { toneClass } from "../utils";

export interface KpiCardProps {
  /** Uppercase label above the value (e.g. "TOTAL", "ERRORS") */
  label: string;
  /** Primary value (number, string, or JSX) */
  value: React.ReactNode;
  /** Optional subtitle below the value (small font) */
  sub?: React.ReactNode;
  /**
   * Semantic value coloring:
   * - default: standard text-primary color
   * - ok: green (success)
   * - warn: orange (warning)
   * - error: red (error)
   */
  tone?: "default" | "ok" | "warn" | "error";
}

const KpiCard: React.FC<KpiCardProps> = ({
  label,
  value,
  sub,
  tone = "default",
}) => (
  <div className="flex min-w-0 flex-col gap-0.5 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3 shadow-sm">
    <p className={LABEL_XS}>{label}</p>
    <p
      className={`truncate text-sm font-semibold tabular-nums leading-5 ${toneClass(tone)}`}
    >
      {value}
    </p>
    {sub && (
      <p className="truncate text-[10px] leading-4 text-[var(--text-muted)]">
        {sub}
      </p>
    )}
  </div>
);

export default KpiCard;



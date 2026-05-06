// =============================================================
// src/pages/tabs/overview/shared.tsx
// =============================================================

import React from "react";

export const StatusRow: React.FC<{
  label: string;
  value: string;
  tone?: "ok" | "warn" | "neutral";
}> = ({ label, value, tone = "neutral" }) => {
  const toneClass =
    tone === "ok"
      ? "text-emerald-600"
      : tone === "warn"
        ? "text-amber-600"
        : "text-[var(--text-primary)]";

  return (
    <div className="flex flex-col gap-1 rounded-xl border border-[var(--border-soft)] bg-[var(--bg-elevated-soft)] px-3 py-2">
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
        {label}
      </p>
      <p className={`text-sm ${toneClass}`}>{value}</p>
    </div>
  );
};



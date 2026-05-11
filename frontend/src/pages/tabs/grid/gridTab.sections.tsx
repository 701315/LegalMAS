// =============================================================
// src/pages/tabs/grid/gridTab.sections.tsx
// Презентационные UI-блоки для DD Grid workspace.
// На текущем этапе содержит только StatCard — карточку KPI
// для сводных метрик run-scoped review matrix.
// =============================================================

import React from "react";

export function StatCard({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: React.ReactNode;
  tone?: "default" | "critical" | "accent";
}) {
  const valueClass =
    tone === "critical"
      ? "text-[var(--color-error)]"
      : tone === "accent"
        ? "text-[var(--accent-primary)]"
        : "text-[var(--text-primary)]";

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated-soft)] px-4 py-3">
      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]">
        {label}
      </div>
      <div className={`mt-2 text-lg font-semibold tracking-tight ${valueClass}`}>
        {value}
      </div>
    </div>
  );
}



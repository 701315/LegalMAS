// =============================================================
// src/pages/tabs/grid/gridTab.sections.tsx
// Презентационные UI-блоки для DD Grid workspace.
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
    <div className="flex min-w-0 flex-col gap-0.5 rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] px-4 py-3 shadow-sm">
      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
        {label}
      </p>
      <p className={`truncate text-sm font-semibold tabular-nums leading-5 ${valueClass}`}>
        {value}
      </p>
    </div>
  );
}



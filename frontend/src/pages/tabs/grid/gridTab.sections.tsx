// =============================================================
// src/pages/tabs/grid/gridTab.sections.tsx
// =============================================================

import React from "react";

export function SectionCard({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] shadow-sm">
      <div className="px-6 pt-5">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-[var(--text-primary)]">
              {title}
            </h2>
            {description ? (
              <p className="mt-1 text-sm text-[var(--text-muted)]">
                {description}
              </p>
            ) : null}
          </div>

          {actions ? (
            <div className="flex flex-wrap items-center gap-2">{actions}</div>
          ) : null}
        </div>

        <div className="mt-4 border-t border-[var(--border-subtle)]" />
      </div>

      <div className="px-6 py-5">{children}</div>
    </section>
  );
}

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



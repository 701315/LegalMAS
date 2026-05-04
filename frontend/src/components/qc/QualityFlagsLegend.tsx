// =============================================================
// src/components/qc/QualityFlagsLegend.tsx
// Легенда для значков флагов качества.
// =============================================================

import React from "react";

function Dot({ className }: { className: string }) {
  return <span className={`h-2 w-2 rounded-full ${className}`} aria-hidden="true" />;
}

export const QualityFlagsLegend: React.FC = () => {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-3 py-2 text-[11px] text-[var(--text-secondary)]">
      <span className="font-semibold text-[var(--text-primary)]">
        Флаги качества:
      </span>

      <span className="inline-flex items-center gap-1.5">
        <Dot className="bg-[var(--color-orange)]" />
        <span>Структура документа нарушена</span>
      </span>

      <span className="inline-flex items-center gap-1.5">
        <Dot className="bg-[var(--accent-primary)]" />
        <span>Использован LLM fallback</span>
      </span>

      <span className="inline-flex items-center gap-1.5">
        <Dot className="bg-[var(--text-muted)]" />
        <span>Другие флаги</span>
      </span>
    </div>
  );
};

export default QualityFlagsLegend;

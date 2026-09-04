// =============================================================
// src/components/qc/QualityFlagsLegend.tsx
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";

function Dot({ className }: { className: string }) {
  return <span className={`h-2 w-2 rounded-full ${className}`} aria-hidden="true" />;
}

export const QualityFlagsLegend: React.FC = () => {
  const { t } = useTranslation("ddGrid");

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated-soft)] px-3 py-2 text-[11px] text-[var(--text-secondary)]">
      <span className="font-semibold text-[var(--text-primary)]">
        {t("qualityFlagsLegend.title")}
      </span>

      <span className="inline-flex items-center gap-1.5">
        <Dot className="bg-[var(--color-warning)]" />
        <span>{t("qualityFlagsLegend.structureDegraded")}</span>
      </span>

      <span className="inline-flex items-center gap-1.5">
        <Dot className="bg-[var(--accent-primary)]" />
        <span>{t("qualityFlagsLegend.llmFallback")}</span>
      </span>

      <span className="inline-flex items-center gap-1.5">
        <Dot className="bg-[var(--text-muted)]" />
        <span>{t("qualityFlagsLegend.otherFlags")}</span>
      </span>
    </div>
  );
};

export default QualityFlagsLegend;



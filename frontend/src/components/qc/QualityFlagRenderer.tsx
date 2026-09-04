// =============================================================
// src/components/qc/QualityFlagRenderer.tsx
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import type { CheckResult } from "../../types";

interface QualityFlagRendererProps {
  result: CheckResult;
}

function FlagDot({
  className,
  title,
}: {
  className: string;
  title: string;
}) {
  return (
    <span
      className={`inline-block h-2 w-2 rounded-full ${className}`}
      title={title}
      aria-label={title}
    />
  );
}

export const QualityFlagRenderer: React.FC<QualityFlagRendererProps> = ({
  result,
}) => {
  const { t } = useTranslation("ddGrid");
  const flags: Record<string, boolean> = result.quality_flags ?? {};

  const hasStructureDegraded = Boolean(flags.structure_degraded);
  const hasLlmFallback = Boolean(flags.llm_fallback_used);

  const otherFlagsExist =
    Object.keys(flags).filter(
      (k) => k !== "structure_degraded" && k !== "llm_fallback_used",
    ).length > 0;

  if (!hasStructureDegraded && !hasLlmFallback && !otherFlagsExist) {
    return (
      <span
        className="text-[11px] text-[var(--text-muted)]"
        title={t("qualityFlagRenderer.noFlags")}
      >
        —
      </span>
    );
  }

  return (
    <div className="flex items-center gap-1.5">
      {hasStructureDegraded && (
        <FlagDot
          className="bg-[var(--color-warning)]"
          title={t("qualityFlagRenderer.structureDegraded")}
        />
      )}

      {hasLlmFallback && (
        <FlagDot
          className="bg-[var(--accent-primary)]"
          title={t("qualityFlagRenderer.llmFallback")}
        />
      )}

      {otherFlagsExist && (
        <FlagDot
          className="bg-[var(--text-muted)]"
          title={t("qualityFlagRenderer.otherFlags")}
        />
      )}
    </div>
  );
};

export default QualityFlagRenderer;


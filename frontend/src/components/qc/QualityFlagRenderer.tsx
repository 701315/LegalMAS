// =============================================================
// src/components/qc/QualityFlagRenderer.tsx
// Компактный рендерер флагов качества.
// =============================================================

import React from "react";
import type { CheckResult } from "../../types";

interface QualityFlagRendererProps {
  result: CheckResult;
}

export const QualityFlagRenderer: React.FC<QualityFlagRendererProps> = ({
  result,
}) => {
  const flags = result.quality_flags || {};
  const hasStructureDegraded = (flags as any).structure_degraded;
  const hasLlmFallback = (flags as any).llm_fallback_used;
  const otherFlags =
    Object.keys(flags).filter(
      (k) => k !== "structure_degraded" && k !== "llm_fallback_used",
    ).length > 0;

  if (!hasStructureDegraded && !hasLlmFallback && !otherFlags) {
    return <span className="text-[11px] text-gray-300">—</span>;
  }

  return (
    <div className="flex items-center gap-1">
      {hasStructureDegraded && (
        <span
          className="w-2 h-2 rounded-full bg-orange-500"
          title="Нарушена структура документа"
        />
      )}
      {hasLlmFallback && (
        <span
          className="w-2 h-2 rounded-full bg-purple-500"
          title="Использован LLM fallback"
        />
      )}
      {otherFlags && (
        <span
          className="w-2 h-2 rounded-full bg-gray-500"
          title="Другие флаги качества"
        />
      )}
    </div>
  );
};

export default QualityFlagRenderer;

// =============================================================
// src/pages/tabs/overview/CollapsedPipelineRail.tsx
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import { Settings, ChevronRight } from "lucide-react";
import type { RunStatus } from "../../../types";

interface CollapsedPipelineRailProps {
  runId: string | null;
  onExpand: () => void;
  runStatus?: RunStatus | null;
}

export const CollapsedPipelineRail: React.FC<CollapsedPipelineRailProps> = ({
  onExpand,
  runStatus,
}) => {
  const { t } = useTranslation("projects");

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col">
      <p className="mb-2 shrink-0 text-[10px] font-semibold uppercase tracking-[0.10em] text-[var(--text-muted)]">
        {t("overviewPanels.pipelineRail.title")}
      </p>

      <button
        type="button"
        onClick={onExpand}
        title={t("overviewPanels.pipelineRail.expandHint")}
        aria-label={t("overviewPanels.pipelineRail.expandHint")}
        className="group flex h-full min-h-0 flex-1 flex-col items-center justify-center gap-2 rounded-xl border border-[var(--border)] bg-[var(--bg-card)] transition-colors hover:border-[var(--accent-primary)] hover:bg-[var(--bg-elevated-soft)]"
      >
        {/* Иконка пайплайна — точно как в CollapsedSummaryRail */}
        <div
          className={`flex h-10 w-10 items-center justify-center rounded-full transition-colors ${
            runStatus === "completed_with_errors" || runStatus === "failed"
              ? runStatus === "failed"
                ? "bg-[var(--color-error)] text-white"
                : "bg-[var(--color-warning)] text-white"
              : "bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] group-hover:bg-[var(--accent-primary)] group-hover:text-white"
          }`}
        >
          <Settings className="h-5 w-5" aria-hidden />
        </div>

        {/* Стрелка — точно как в CollapsedSummaryRail */}
        <ChevronRight className="h-3.5 w-3.5 text-[var(--text-muted)] transition-transform group-hover:translate-x-0.5" />
      </button>
    </div>
  );
};

export default CollapsedPipelineRail;



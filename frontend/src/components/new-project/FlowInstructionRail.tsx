// =============================================================
// src/components/new-project/FlowInstructionRail.tsx
// =============================================================

import React from "react";
import { useTranslation } from "react-i18next";
import FlowSummary from "./FlowSummary";
import type { FlowSummaryData } from "./FlowSummary";
import { getFlowInstruction, collectBullets } from "./flowInstructions";

interface FlowInstructionRailProps {
  activeStep: number | null;
  summary: FlowSummaryData;
}

const FlowInstructionRail: React.FC<FlowInstructionRailProps> = ({
  activeStep,
  summary,
}) => {
  const { t } = useTranslation("projects");
  const descriptor = getFlowInstruction(activeStep);
  const title = t(descriptor.titleKey);
  const description = t(descriptor.descriptionKey);
  const bullets = collectBullets(t, descriptor.bulletsKeyPrefix);

  return (
    <aside className="sticky top-4 flex flex-col gap-4">
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-4 shadow-sm">
        <div className="mb-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            {activeStep !== null
              ? t("flowInstructions.stepLabel", { step: activeStep, total: 6 })
              : t("flowInstructions.overviewLabel")}
          </p>
        </div>

        <h3 className="text-sm font-semibold text-[var(--text-primary)]">
          {title}
        </h3>

        <p className="mt-2 text-[12px] leading-5 text-[var(--text-secondary)]">
          {description}
        </p>

        {bullets.length > 0 && (
          <ul className="mt-3 space-y-1.5">
            {bullets.map((bullet: string, index: number) => (
              <li
                key={index}
                className="flex items-start gap-2 text-[11px] leading-5 text-[var(--text-secondary)]"
              >
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-[var(--accent-primary)]" />
                <span>{bullet}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <FlowSummary data={summary} />
    </aside>
  );
};

export default FlowInstructionRail;
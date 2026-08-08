// =============================================================
// src/components/new-project/FlowInstructionRail.tsx
//
// 25% колонка — сначала инструкция,
// затем сводка проекта.
// Sticky.
// =============================================================

import React from "react";
import FlowSummary from "./FlowSummary";
import type { FlowSummaryData } from "./FlowSummary";
import { getFlowInstruction } from "./flowInstructions";

interface FlowInstructionRailProps {
  activeStep: number | null;
  summary: FlowSummaryData;
}

const FlowInstructionRail: React.FC<FlowInstructionRailProps> = ({
  activeStep,
  summary,
}) => {
  const instruction = getFlowInstruction(activeStep);

  return (
    <aside className="sticky top-4 flex flex-col gap-4">
      {/* ── Инструкция активного шага ───────────────── */}
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-4 shadow-sm">
        <div className="mb-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            {activeStep !== null ? `Шаг ${activeStep} из 6` : "Обзор процесса"}
          </p>
        </div>

        <h3 className="text-sm font-semibold text-[var(--text-primary)]">
          {instruction.title}
        </h3>

        <p className="mt-2 text-[12px] leading-5 text-[var(--text-secondary)]">
          {instruction.description}
        </p>

        {instruction.bullets.length > 0 && (
          <ul className="mt-3 space-y-1.5">
            {instruction.bullets.map((bullet, index) => (
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

      {/* ── Сводка проекта ───────────────────────── */}
      <FlowSummary data={summary} />
    </aside>
  );
};

export default FlowInstructionRail;



// =============================================================
// src/components/new-project/FlowRightRail.tsx
//
// Правая колонка страницы запуска нового проекта.
//
// Содержит три части (сверху вниз):
//   1. Сводка проекта  — актуальные значения всех 6 параметров
//   2. Инструкция     — заголовок / описание / буллеты по активному шагу
//   3. Иллюстрация    — крупный номер шага + иконка + подпись
//
// Всё внутри sticky-контейнера — не уезжает при скролле.
// На узких экранах (< xl) скрывается через parent-обёртку.
// =============================================================

import React from "react";

import FlowSummary from "./FlowSummary";
import type { FlowSummaryData } from "./FlowSummary";
import { getFlowInstruction } from "./flowInstructions";

interface FlowRightRailProps {
  /** Активный шаг 1..6 или null если flow ещё не начат / завершён */
  activeStep: number | null;
  /** Данные для блока «Сводка проекта» */
  summary: FlowSummaryData;
}

const FlowRightRail: React.FC<FlowRightRailProps> = ({
  activeStep,
  summary,
}) => {
  const instruction = getFlowInstruction(activeStep);
  const Icon = instruction.icon;

  // Крупный номер шага для "иллюстрации".
  // Для intro (activeStep === null) — короткая метка.
  const stepDisplay =
    activeStep !== null ? String(activeStep).padStart(2, "0") : "";

  return (
    <aside className="sticky top-4 flex flex-col gap-4">
      {/* ── 1. Сводка проекта ─────────────────────────────── */}
      <FlowSummary data={summary} />

      {/* ── 2. Инструкция активного шага ──────────────────── */}
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-card)] p-4 shadow-sm">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
            {activeStep !== null ? `Шаг ${activeStep} из 6` : "Обзор процесса"}
          </h3>
        </div>

        <h4 className="text-sm font-semibold text-[var(--text-primary)]">
          {instruction.title}
        </h4>

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
                <span
                  className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-[var(--accent-primary)]"
                  aria-hidden="true"
                />
                <span>{bullet}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* ── 3. Иллюстрация — крупный номер + иконка ───────── */}
      <section className="rounded-2xl border border-[var(--border)] bg-gradient-to-br from-[var(--bg-card)] to-[var(--accent-subtle)] p-5 shadow-sm">
        <div className="flex items-center justify-between gap-4">
          <div className="min-w-0">
            {activeStep !== null && (
              <div
                className="font-[var(--font-display)] text-[54px] leading-none text-[var(--accent-primary)]"
                style={{ fontFamily: "var(--font-display)" }}
                aria-hidden="true"
              >
                {stepDisplay}
              </div>
            )}

            <p
              className={[
                "text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--text-muted)]",
                activeStep !== null ? "mt-2" : "",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              {instruction.iconLabel}
            </p>
          </div>

          <div
            className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-[var(--bg-card)] text-[var(--accent-primary)] shadow-sm"
            aria-hidden="true"
          >
            <Icon className="h-7 w-7" strokeWidth={1.5} />
          </div>
        </div>
      </section>
    </aside>
  );
};

export default FlowRightRail;



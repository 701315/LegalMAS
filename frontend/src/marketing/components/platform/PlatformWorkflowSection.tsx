// src/marketing/components/platform/PlatformWorkflowSection.tsx

import React from "react";
import Reveal from "../../motion/Reveal";
import { WORKFLOW_CONTENT } from "./content/platformContent";
import FlowSchema from "./diagrams/FlowSchema";

/**
 * PlatformWorkflowSection — Section 1 (упрощённая версия).
 *
 * Изменения:
 *   • Сжато с 3 до 2 абзацев
 *   • Bullets перенесены из белой карточки в editorial-выноску
 *     с левым бордером — единый стиль со Structure-секцией
 *
 * Композиция:
 *   • Заголовок + eyebrow сверху
 *   • Full-width горизонтальная схема с 7 шагами
 *   • Split ниже: слева editorial-текст (7/12), справа bullets
 *     в выноске с левым бордером (5/12)
 *
 * Фон off-white (#F3F0EB) — ритмичное чередование с hero (белым).
 */

const PlatformWorkflowSection: React.FC = () => {
  return (
    <section
      className="relative"
      style={{ background: "#F3F0EB" }}
      data-header-theme="light"
    >
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        {/* ── Header ─────────────────────────────────────────────────── */}
        <Reveal>
          <div className="max-w-3xl">
            <div className="eyebrow">{WORKFLOW_CONTENT.eyebrow}</div>
            <h2 className="mt-4 font-serif text-[clamp(2.25rem,4vw,3.25rem)] leading-[1.05] tracking-[-0.03em] text-[#1A1917]">              {WORKFLOW_CONTENT.title}
            </h2>
          </div>
        </Reveal>

        {/* ── Flow schema ─────────────────────────────────────────────── */}
        <div className="mt-14 lg:mt-16">
          <FlowSchema steps={WORKFLOW_CONTENT.steps} />
        </div>

        {/* ── Split: текст + editorial-выноска bullets ────────────────── */}
        <div className="mt-16 grid gap-10 lg:mt-20 lg:grid-cols-12 lg:gap-12 lg:items-center">
          {/* Левая колонка: текст */}
          <Reveal className="lg:col-span-7">
            <div className="space-y-5" style={{ maxWidth: 640 }}>
              {WORKFLOW_CONTENT.paragraphs.map((p, i) => (
                <p
                  key={i}
                  className="text-[1rem] leading-[1.75] text-[#78756F]"
                >
                  {p}
                </p>
              ))}
            </div>
          </Reveal>

          {/* Правая колонка: editorial-выноска с bullets */}
          <Reveal delay={0.1} className="lg:col-span-5">
            <div className="border-l border-[#E8E4DD] pl-6">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#A8A29E]">
                {WORKFLOW_CONTENT.bulletsLabel}
              </div>
              <ul className="mt-4 space-y-3">
                {WORKFLOW_CONTENT.bullets.map((bullet) => (
                  <li
                    key={bullet}
                    className="flex items-start gap-3 text-[#78756F]"
                  >
                    <span
                      className="mt-2 flex h-1.5 w-1.5 shrink-0 rounded-full bg-[#C86B52]"
                      aria-hidden="true"
                    />
                    <span className="text-[0.9375rem] leading-[1.65]">
                      {bullet}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
};

export default PlatformWorkflowSection;



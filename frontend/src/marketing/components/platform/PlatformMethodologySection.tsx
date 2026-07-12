// src/marketing/components/platform/PlatformMethodologySection.tsx

import React from "react";
import Reveal from "../../motion/Reveal";
import { METHODOLOGY_CONTENT } from "./content/platformContent";
import VerticalNodeChain from "./diagrams/VerticalNodeChain";

/**
 * PlatformMethodologySection — Section 5 (упрощённая версия).
 *
 * Изменения:
 *   • Сжато с 3 до 2 абзацев
 *   • Добавлен короткий lead-in курсивом перед основным текстом —
 *     работает как «tagline» или «эпиграф» к секции
 *   • Убран sticky у схемы, выравнивание по центру
 *
 * Композиция:
 *   • Split 7/5 на десктопе: слева заголовок + lead-in + 2 абзаца,
 *     справа VerticalNodeChain (size="md") с accent на «Steloom»
 *   • Фон белый (#FAF8F5)
 */

const PlatformMethodologySection: React.FC = () => {
  return (
    <section
      className="relative"
      style={{ background: "#FAF8F5" }}
      data-header-theme="light"
    >
      <div
        className="mx-auto w-full px-6 py-28 lg:px-8 lg:py-40"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid gap-16 lg:grid-cols-12 lg:gap-20 lg:items-center">
          {/* ── Left: eyebrow + заголовок + lead-in + текст ──────────── */}
          <Reveal className="lg:col-span-7">
            <div className="max-w-2xl">
              <div className="eyebrow">{METHODOLOGY_CONTENT.eyebrow}</div>

              <h2 className="mt-4 font-serif text-[clamp(2.25rem,4vw,3.25rem)] leading-[1.05] tracking-[-0.03em] text-[#1A1917]">
                {METHODOLOGY_CONTENT.title}
              </h2>

              {/* Lead-in — короткое tagline-предложение перед основным текстом */}
              <p
                className="mt-6 font-serif text-[1.25rem] italic leading-[1.5] text-[#1A1917]"
                style={{ maxWidth: 560 }}
              >
                {METHODOLOGY_CONTENT.leadIn}
              </p>

              <div className="mt-6 space-y-5" style={{ maxWidth: 620 }}>
                {METHODOLOGY_CONTENT.paragraphs.map((p, i) => (
                  <p
                    key={i}
                    className="text-[1.0625rem] leading-[1.75] text-[#78756F]"
                  >
                    {p}
                  </p>
                ))}
              </div>
            </div>
          </Reveal>

          {/* ── Right: VerticalNodeChain (size="md") ─────────────────── */}
          <div className="lg:col-span-5">
            <Reveal delay={0.15}>
              <div className="mx-auto" style={{ maxWidth: 420 }}>
                <VerticalNodeChain
                  nodes={METHODOLOGY_CONTENT.chain}
                  size="md"
                />
              </div>
            </Reveal>
          </div>
        </div>
      </div>
    </section>
  );
};

export default PlatformMethodologySection;



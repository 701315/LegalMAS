// src/marketing/components/platform/PlatformStandardsSection.tsx

import React from "react";
import Reveal from "../../motion/Reveal";
import { STANDARDS_CONTENT } from "./content/platformContent";
import StandardsDiagram from "./diagrams/StandardsDiagram";

/**
 * PlatformStandardsSection — Section 3 (ЕДИНСТВЕННАЯ ТЁМНАЯ СЕКЦИЯ).
 *
 * Композиция:
 *   • Full-width тёмный фон (#1A1917)
 *   • Split: слева StandardsDiagram (архитектурная схема правил),
 *     справа заголовок + editorial текст (без bullets — они визуально шумят
 *     на тёмном; на тёмном фоне читаемость обеспечивается только крупной
 *     типографикой)
 *   • Крупные вертикальные отступы (py-32 / py-40) — секция «дышит»
 *
 * Атрибут data-header-theme="dark" сигнализирует SiteHeader переключить
 * цвета навигации на светлые, когда секция попадает в viewport.
 * Это работает автоматически через useSectionTheme() в SiteHeader,
 * если в CapabilitiesPage у SiteHeader НЕ передан forcedTheme.
 */

const PlatformStandardsSection: React.FC = () => {
  return (
    <section
      className="relative"
      style={{ background: "#1A1917" }}
      data-header-theme="dark"
    >
      {/* Мягкий верхний градиент — визуальное смягчение перехода от светлой
          секции к тёмной. Никакого «obvious разлома» между секциями. */}
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-24"
        style={{
          background:
            "linear-gradient(180deg, rgba(26,25,23,0) 0%, rgba(26,25,23,0.6) 100%)",
        }}
        aria-hidden="true"
      />

      <div
        className="relative mx-auto w-full px-6 py-32 lg:px-8 lg:py-40"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid items-center gap-16 lg:grid-cols-12 lg:gap-20">
          {/* ── Left: StandardsDiagram ──────────────────────────────────── */}
          <div className="lg:col-span-6 lg:order-1">
            <Reveal>
              <div className="mx-auto flex justify-center lg:justify-start">
                <StandardsDiagram
                  sources={STANDARDS_CONTENT.diagram.sources}
                  core={STANDARDS_CONTENT.diagram.core}
                  targets={STANDARDS_CONTENT.diagram.targets}
                />
              </div>
            </Reveal>
          </div>

          {/* ── Right: заголовок + текст ────────────────────────────────── */}
          <Reveal className="lg:col-span-6 lg:order-2" delay={0.1}>
            <div className="max-w-xl">
              <div
                className="text-[11px] font-medium uppercase tracking-[0.22em]"
                style={{ color: "rgba(250, 248, 245, 0.55)" }}
              >
                {STANDARDS_CONTENT.eyebrow}
              </div>

              <h2
                className="mt-4 font-serif text-[clamp(2.25rem,4vw,3.25rem)] leading-[1.05] tracking-[-0.03em]"
                style={{ color: "#FAF8F5" }}
              >
                {STANDARDS_CONTENT.title}
              </h2>

              <div className="mt-7 space-y-5">
                {STANDARDS_CONTENT.paragraphs.map((p, i) => (
                  <p
                    key={i}
                    className="text-[1rem] leading-[1.75]"
                    style={{ color: "rgba(250, 248, 245, 0.72)" }}
                  >
                    {p}
                  </p>
                ))}
              </div>
            </div>
          </Reveal>
        </div>
      </div>

      {/* Мягкий нижний градиент — симметричный переход к светлой секции ниже. */}
      <div
        className="pointer-events-none absolute inset-x-0 bottom-0 h-24"
        style={{
          background:
            "linear-gradient(0deg, rgba(26,25,23,0) 0%, rgba(26,25,23,0.6) 100%)",
        }}
        aria-hidden="true"
      />
    </section>
  );
};

export default PlatformStandardsSection;



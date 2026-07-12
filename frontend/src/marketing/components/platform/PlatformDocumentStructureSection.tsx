// src/marketing/components/platform/PlatformDocumentStructureSection.tsx

import React from "react";
import Reveal from "../../motion/Reveal";
import { STRUCTURE_CONTENT } from "./content/platformContent";
import VerticalNodeChain from "./diagrams/VerticalNodeChain";

/**
 * PlatformDocumentStructureSection — Section 2.
 *
 * Композиция (split 50/50 на десктопе):
 *   • Слева: eyebrow → h2 → 2 абзаца → bullets «Что это даёт юристу»
 *   • Справа: VerticalNodeChain с 5 узлами структуры документа
 */

const PlatformDocumentStructureSection: React.FC = () => {
  return (
    <section
      className="relative"
      style={{ background: "#FAF8F5" }}
      data-header-theme="light"
    >
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid gap-14 lg:grid-cols-12 lg:gap-16 lg:items-center">
          {/* ── Left: текст ─────────────────────────────────────────────── */}
          <Reveal className="lg:col-span-7">
            <div className="max-w-2xl">
              <div className="eyebrow">{STRUCTURE_CONTENT.eyebrow}</div>

              {/* ✅ Унифицированный размер h2 */}
              <h2 className="mt-4 font-serif text-[clamp(2.25rem,4vw,3.25rem)] leading-[1.05] tracking-[-0.03em] text-[#1A1917]">
                {STRUCTURE_CONTENT.title}
              </h2>

              <div className="mt-7 space-y-5">
                {STRUCTURE_CONTENT.paragraphs.map((p, i) => (
                  <p
                    key={i}
                    className="text-[1rem] leading-[1.75] text-[#78756F]"
                  >
                    {p}
                  </p>
                ))}
              </div>

              <div className="mt-10 border-l border-[#E8E4DD] pl-6">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#A8A29E]">
                  {STRUCTURE_CONTENT.bulletsLabel}
                </div>
                <ul className="mt-4 space-y-3">
                  {STRUCTURE_CONTENT.bullets.map((bullet) => (
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
            </div>
          </Reveal>

          {/* ── Right: вертикальная схема структуры ─────────────────────── */}
          <div className="lg:col-span-5">
            <Reveal delay={0.15}>
              <div className="mx-auto" style={{ maxWidth: 380 }}>
                <VerticalNodeChain
                  nodes={STRUCTURE_CONTENT.chain}
                  size="sm"
                />
              </div>
            </Reveal>
          </div>
        </div>
      </div>
    </section>
  );
};

export default PlatformDocumentStructureSection;



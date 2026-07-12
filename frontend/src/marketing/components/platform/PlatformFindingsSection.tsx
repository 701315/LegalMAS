// src/marketing/components/platform/PlatformFindingsSection.tsx

import React from "react";
import Reveal from "../../motion/Reveal";
import { FINDINGS_CONTENT } from "./content/platformContent";
import FindingsDiagram from "./diagrams/FindingsDiagram";

/**
 * PlatformFindingsSection — Section 4 (Structured Results).
 *
 * Композиция (checkerboard, обратная относительно Structure-секции):
 *   • Слева: текст (широкая колонка) — 55% ширины
 *   • Справа: FindingsDiagram (горизонтальная цепочка с 5 узлами) — 45%
 *
 * Отличается от предыдущих секций:
 *   • Фон off-white (#F3F0EB) — ритмичное чередование после тёмной Standards
 *   • Диаграмма — горизонтальная цепочка (в отличие от вертикальной в Structure)
 *   • Нет отдельного блока «Что это даёт юристу» — смысл выражается
 *     через саму диаграмму (акцентный последний узел Source Link)
 *     и подпись под ней
 */

const PlatformFindingsSection: React.FC = () => {
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
        <div className="grid gap-14 lg:grid-cols-12 lg:gap-16 lg:items-center">
          {/* ── Left: eyebrow + title + текст ────────────────────────── */}
          <Reveal className="lg:col-span-6">
            <div className="max-w-xl">
              <div className="eyebrow">{FINDINGS_CONTENT.eyebrow}</div>

              <h2 className="mt-4 font-serif text-[clamp(2.25rem,4vw,3.25rem)] leading-[1.05] tracking-[-0.03em] text-[#1A1917]">                {FINDINGS_CONTENT.title}
              </h2>

              <div className="mt-7 space-y-5">
                {FINDINGS_CONTENT.paragraphs.map((p, i) => (
                  <p
                    key={i}
                    className="text-[1rem] leading-[1.75] text-[#78756F]"
                  >
                    {p}
                  </p>
                ))}
              </div>
            </div>
          </Reveal>

          {/* ── Right: FindingsDiagram ───────────────────────────────── */}
          <Reveal className="lg:col-span-6" delay={0.12}>
            <FindingsDiagram chain={FINDINGS_CONTENT.chain} />
          </Reveal>
        </div>
      </div>
    </section>
  );
};

export default PlatformFindingsSection;



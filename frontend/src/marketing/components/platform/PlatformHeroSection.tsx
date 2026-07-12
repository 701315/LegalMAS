// src/marketing/components/platform/PlatformHeroSection.tsx

import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { HERO_CONTENT } from "./content/platformContent";
import HeroFlowVisual from "./diagrams/HeroFlowVisual";
import PathCrumb from "./primitives/PathCrumb";

/**
 * PlatformHeroSection — первая секция страницы Platform.
 *
 * Композиция:
 *   • Split-layout 60/40 на десктопе (текст / визуализация)
 *   • Слева: path-крошка → большой serif h1 → 2 абзаца
 *   • Справа: HeroFlowVisual (архитектурная схема document flow)
 *   • На мобильных: stack vertical, визуализация уходит под текст
 *
 * Обновление:
 *   • Убраны CTA-кнопки — призыв к действию сфокусирован в финальной
 *     PlatformCTASection в конце страницы. Hero теперь чисто editorial:
 *     задаёт тему без давления на конверсию.
 */

const PlatformHeroSection: React.FC = () => {
  const shouldReduceMotion = useReducedMotion();

  const ease: [number, number, number, number] = [0.22, 1, 0.36, 1];

  return (
    <section className="relative">
      <div
        className="mx-auto w-full px-6 pb-24 pt-20 lg:px-8 lg:pb-32 lg:pt-28"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid gap-12 lg:grid-cols-12 lg:gap-16 lg:items-center">
          {/* ── Left: текст ─────────────────────────────────────────────── */}
          <div className="lg:col-span-7 xl:col-span-7">
            <motion.div
              initial={shouldReduceMotion ? undefined : { opacity: 0, y: 12 }}
              animate={shouldReduceMotion ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.05, ease }}
            >
              <PathCrumb
                root={HERO_CONTENT.eyebrow.root}
                leaf={HERO_CONTENT.eyebrow.leaf}
              />
            </motion.div>

            <motion.h1
              initial={shouldReduceMotion ? undefined : { opacity: 0, y: 14 }}
              animate={shouldReduceMotion ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.12, ease }}
              className="mt-5 font-serif text-[clamp(2.5rem,5vw,4rem)] leading-[1.05] tracking-[-0.03em] text-[#1A1917]"
            >
              {HERO_CONTENT.title}
            </motion.h1>

            <motion.div
              initial={shouldReduceMotion ? undefined : { opacity: 0, y: 12 }}
              animate={shouldReduceMotion ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.22, ease }}
              className="mt-7 space-y-5"
              style={{ maxWidth: 620 }}
            >
              {HERO_CONTENT.paragraphs.map((p, i) => (
                <p
                  key={i}
                  className="text-[1.0625rem] leading-[1.7] text-[#78756F]"
                >
                  {p}
                </p>
              ))}
            </motion.div>
          </div>

          {/* ── Right: визуализация ──────────────────────────────────── */}
          <div className="lg:col-span-5 xl:col-span-5">
            <motion.div
              initial={shouldReduceMotion ? undefined : { opacity: 0, y: 16 }}
              animate={shouldReduceMotion ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.7, delay: 0.28, ease }}
              className="flex h-full items-center justify-center lg:justify-end"
            >
              <HeroFlowVisual />
            </motion.div>
          </div>
        </div>
      </div>

      {/* Разделительная линия внизу секции */}
      <div
        className="mx-auto"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="mx-6 lg:mx-8">
          <div className="h-px w-full bg-[#E8E4DD]" />
        </div>
      </div>
    </section>
  );
};

export default PlatformHeroSection;



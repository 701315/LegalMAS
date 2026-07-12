// src/marketing/components/platform/diagrams/StandardsDiagram.tsx

import React from "react";
import { motion, useReducedMotion } from "framer-motion";

/**
 * StandardsDiagram — архитектурная схема для тёмной Section 3.
 *
 * Показывает, как входы (Playbooks / Policies / Instructions) сходятся
 * в единый движок правил (Analysis Rules), который затем применяется
 * к каждому документу (Document A / B / C).
 *
 * Визуальная логика:
 *   [ Playbooks ]  ─┐
 *   [ Policies  ]  ─┼─► [ Analysis Rules ] ─┬─► [ Document A ]
 *   [ Instructions] ┘                       ├─► [ Document B ]
 *                                           └─► [ Document C ]
 *
 * Специально стилизована под тёмный фон:
 *   • Полупрозрачные светлые бордеры вместо тёмных
 *   • Текст в off-white (#FAF8F5) с разной прозрачностью для иерархии
 *   • Центральный «Analysis Rules» — акцентная terracotta-обводка
 *   • Соединительные линии — очень тонкие, полупрозрачные светлые
 *
 * Никаких иконок, никаких заливок — только линии, бордеры, текст.
 */

interface StandardsDiagramProps {
  sources: string[]; // 3 источника правил (левая колонка)
  core: string;       // центральный узел (движок правил)
  targets: string[]; // 3 применения (правая колонка)
}

const EASE: [number, number, number, number] = [0.22, 1, 0.36, 1];

const StandardsDiagram: React.FC<StandardsDiagramProps> = ({
  sources,
  core,
  targets,
}) => {
  const shouldReduceMotion = useReducedMotion();

  return (
    <motion.div
      initial={shouldReduceMotion ? undefined : "hidden"}
      whileInView={shouldReduceMotion ? undefined : "visible"}
      viewport={{ once: true, margin: "-80px" }}
      variants={{
        hidden: {},
        visible: {
          transition: {
            staggerChildren: 0.06,
            delayChildren: 0.05,
          },
        },
      }}
      className="relative w-full"
      style={{ aspectRatio: "1 / 1", maxWidth: 520 }}
      aria-hidden="true"
    >
      {/* ── SVG-слой с соединительными линиями ─────────────────────────── */}
      <svg
        viewBox="0 0 400 400"
        className="absolute inset-0 h-full w-full"
        preserveAspectRatio="none"
      >
        {/* Sources → Core: 3 линии сходятся в центральный узел */}
        {[75, 200, 325].map((y, i) => (
          <motion.path
            key={`src-${i}`}
            d={`M 130 ${y} C 165 ${y}, 165 200, 200 200`}
            stroke="rgba(250, 248, 245, 0.14)"
            strokeWidth="1"
            fill="none"
            initial={
              shouldReduceMotion ? undefined : { pathLength: 0, opacity: 0 }
            }
            animate={
              shouldReduceMotion
                ? undefined
                : { pathLength: 1, opacity: 1 }
            }
            transition={{
              duration: 0.7,
              delay: 0.25 + i * 0.04,
              ease: EASE,
            }}
          />
        ))}

        {/* Core → Targets: 3 линии расходятся к применениям */}
        {[75, 200, 325].map((y, i) => (
          <motion.path
            key={`tgt-${i}`}
            d={`M 265 200 C 300 200, 300 ${y}, 335 ${y}`}
            stroke="rgba(250, 248, 245, 0.14)"
            strokeWidth="1"
            fill="none"
            initial={
              shouldReduceMotion ? undefined : { pathLength: 0, opacity: 0 }
            }
            animate={
              shouldReduceMotion
                ? undefined
                : { pathLength: 1, opacity: 1 }
            }
            transition={{
              duration: 0.7,
              delay: 0.55 + i * 0.04,
              ease: EASE,
            }}
          />
        ))}
      </svg>

      {/* ── Left: sources ─────────────────────────────────────────────── */}
      <div
        className="absolute inset-y-0 left-0 flex flex-col justify-between"
        style={{ width: "32%" }}
      >
        {sources.map((label, i) => (
          <motion.div
            key={label}
            variants={{
              hidden: { opacity: 0, x: -6 },
              visible: {
                opacity: 1,
                x: 0,
                transition: { duration: 0.5, ease: EASE, delay: i * 0.04 },
              },
            }}
            className="rounded-lg border px-3.5 py-2.5"
            style={{
              borderColor: "rgba(250, 248, 245, 0.14)",
              background: "rgba(250, 248, 245, 0.02)",
            }}
          >
            <div
              className="text-[10px] font-medium uppercase tracking-[0.14em]"
              style={{ color: "rgba(250, 248, 245, 0.45)" }}
            >
              Input
            </div>
            <div
              className="mt-0.5 text-[0.8125rem] font-medium leading-tight"
              style={{ color: "#FAF8F5" }}
            >
              {label}
            </div>
          </motion.div>
        ))}
      </div>

      {/* ── Center: core (accent) ─────────────────────────────────────── */}
      <div className="absolute inset-0 flex items-center justify-center">
        <motion.div
          variants={{
            hidden: { opacity: 0, scale: 0.96 },
            visible: {
              opacity: 1,
              scale: 1,
              transition: { duration: 0.55, ease: EASE, delay: 0.42 },
            },
          }}
          className="relative rounded-xl px-5 py-3.5"
          style={{
            border: "1px solid rgba(200, 107, 82, 0.55)",
            background: "rgba(200, 107, 82, 0.08)",
            minWidth: 140,
            boxShadow: "0 8px 24px rgba(200, 107, 82, 0.12)",
          }}
        >
          <div
            className="text-[10px] font-medium uppercase tracking-[0.14em]"
            style={{ color: "#E89A82" }}
          >
            Engine
          </div>
          <div
            className="mt-0.5 text-[0.9375rem] font-semibold leading-tight"
            style={{ color: "#FAF8F5" }}
          >
            {core}
          </div>
        </motion.div>
      </div>

      {/* ── Right: targets ────────────────────────────────────────────── */}
      <div
        className="absolute inset-y-0 right-0 flex flex-col justify-between"
        style={{ width: "32%" }}
      >
        {targets.map((label, i) => (
          <motion.div
            key={label}
            variants={{
              hidden: { opacity: 0, x: 6 },
              visible: {
                opacity: 1,
                x: 0,
                transition: {
                  duration: 0.5,
                  ease: EASE,
                  delay: 0.72 + i * 0.04,
                },
              },
            }}
            className="rounded-lg border px-3.5 py-2.5"
            style={{
              borderColor: "rgba(250, 248, 245, 0.14)",
              background: "rgba(250, 248, 245, 0.02)",
            }}
          >
            <div
              className="text-[10px] font-medium uppercase tracking-[0.14em]"
              style={{ color: "rgba(250, 248, 245, 0.45)" }}
            >
              Applied to
            </div>
            <div
              className="mt-0.5 text-[0.8125rem] font-medium leading-tight"
              style={{ color: "#FAF8F5" }}
            >
              {label}
            </div>
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
};

export default StandardsDiagram;



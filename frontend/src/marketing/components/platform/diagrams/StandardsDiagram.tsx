// src/marketing/components/platform/diagrams/StandardsDiagram.tsx

import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useTranslation } from "react-i18next";

interface StandardsDiagramProps {
  sources?: string[];
  targets?: string[];
}

const EASE: [number, number, number, number] = [0.22, 1, 0.36, 1];

const StandardsDiagram: React.FC<StandardsDiagramProps> = ({
  sources = ["Playbooks", "Policies", "Instructions"],
  targets = ["Document A", "Document B", "Document C"],
}) => {
  const shouldReduceMotion = useReducedMotion();
  const { t, i18n } = useTranslation("marketing");
  const isRTL = i18n.language === "ar";

  const safeSources = Array.isArray(sources) && sources.length > 0
    ? sources
    : ["Playbooks", "Policies", "Instructions"];
  const safeTargets = Array.isArray(targets) && targets.length > 0
    ? targets
    : ["Document A", "Document B", "Document C"];

  const slideFromStart = isRTL ? 12 : -12;
  const slideFromEnd = isRTL ? -12 : 12;

  return (
    <motion.div
      initial={shouldReduceMotion ? undefined : "hidden"}
      whileInView={shouldReduceMotion ? undefined : "visible"}
      viewport={{ once: true, margin: "-80px" }}
      variants={{
        hidden: {},
        visible: {
          transition: {
            staggerChildren: 0.08,
            delayChildren: 0.05,
          },
        },
      }}
      className="relative w-full"
      style={{ aspectRatio: "1 / 1", maxWidth: 480 }}
      aria-hidden="true"
    >
      {/* ── Соединительные линии напрямую слева направо (БЕЗ ENGINE) ── */}
      <svg
        viewBox="0 0 400 400"
        className="absolute inset-0 h-full w-full pointer-events-none"
        preserveAspectRatio="none"
        style={{ transform: isRTL ? "scaleX(-1)" : "none" }}
      >
        {[75, 200, 325].map((y, i) => (
          <React.Fragment key={`lines-${i}`}>
            <motion.path
              d={`M 130 ${y} L 270 ${y}`}
              stroke="rgba(200, 107, 82, 0.6)"
              strokeWidth="1.5"
              strokeDasharray="4 4"
              fill="none"
              initial={shouldReduceMotion ? undefined : { pathLength: 0, opacity: 0 }}
              animate={shouldReduceMotion ? undefined : { pathLength: 1, opacity: 1 }}
              transition={{ duration: 0.7, delay: 0.2 + i * 0.08, ease: EASE }}
            />
            {i !== 1 && (
              <motion.path
                d={`M 130 ${y} C 200 ${y}, 200 200, 270 200`}
                stroke="rgba(250, 248, 245, 0.2)"
                strokeWidth="1"
                fill="none"
                initial={shouldReduceMotion ? undefined : { pathLength: 0, opacity: 0 }}
                animate={shouldReduceMotion ? undefined : { pathLength: 1, opacity: 1 }}
                transition={{ duration: 0.7, delay: 0.4 + i * 0.08, ease: EASE }}
              />
            )}
          </React.Fragment>
        ))}
      </svg>

      {/* ── Левая колонка: Источники ────────────────────────────── */}
      <div
        className="absolute inset-y-0 start-0 flex flex-col justify-between"
        style={{ width: "34%" }}
      >
        {safeSources.map((label, i) => (
          <motion.div
            key={`src-${label}-${i}`}
            variants={{
              hidden: { opacity: 0, x: slideFromStart },
              visible: {
                opacity: 1,
                x: 0,
                transition: { duration: 0.5, ease: EASE, delay: i * 0.06 },
              },
            }}
            className="rounded-xl border px-4 py-3 text-start backdrop-blur-md shadow-lg"
            style={{
              borderColor: "rgba(255, 255, 255, 0.15)",
              background: "rgba(26, 25, 23, 0.75)",
            }}
          >
            <div
              className="text-meta font-semibold uppercase tracking-wider"
              style={{ color: "#C86B52" }}
            >
              {t("platform.standardsDiagram.inputLabel", "ВХОД")}
            </div>
            <div
              className="mt-1 text-body-sm font-medium leading-snug"
              style={{ color: "#FAF8F5" }}
            >
              {label}
            </div>
          </motion.div>
        ))}
      </div>

      {/* ── Правая колонка: Применение ───────────────────────────── */}
      <div
        className="absolute inset-y-0 end-0 flex flex-col justify-between"
        style={{ width: "34%" }}
      >
        {safeTargets.map((label, i) => (
          <motion.div
            key={`tgt-${label}-${i}`}
            variants={{
              hidden: { opacity: 0, x: slideFromEnd },
              visible: {
                opacity: 1,
                x: 0,
                transition: { duration: 0.5, ease: EASE, delay: 0.3 + i * 0.06 },
              },
            }}
            className="rounded-xl border px-4 py-3 text-start backdrop-blur-md shadow-lg"
            style={{
              borderColor: "rgba(255, 255, 255, 0.15)",
              background: "rgba(26, 25, 23, 0.75)",
            }}
          >
            <div
              className="text-meta font-semibold uppercase tracking-wider"
              style={{ color: "rgba(250, 248, 245, 0.5)" }}
            >
              {t("platform.standardsDiagram.appliedToLabel", "ПРИМЕНЯЕТСЯ К")}
            </div>
            <div
              className="mt-1 text-body-sm font-medium leading-snug"
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

import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useTranslation } from "react-i18next";
import type { ChainNode } from "./VerticalNodeChain";

interface FindingsDiagramProps {
  chain: ChainNode[];
}

const EASE: [number, number, number, number] = [0.22, 1, 0.36, 1];

const FindingsDiagram: React.FC<FindingsDiagramProps> = ({ chain }) => {
  const shouldReduceMotion = useReducedMotion();
  
  // RTL FIX: Инициализация i18n и определение направления
  const { t, i18n } = useTranslation("marketing");
  const isRTL = i18n.language === "ar";

  // RTL FIX: Защита от сбоев, если prop chain не передан или не является массивом
  const safeChain = Array.isArray(chain) ? chain : [];

  return (
    <motion.div
      initial={shouldReduceMotion ? undefined : "hidden"}
      whileInView={shouldReduceMotion ? undefined : "visible"}
      viewport={{ once: true, margin: "-80px" }}
      variants={{
        hidden: {},
        visible: {
          transition: {
            staggerChildren: 0.09,
            delayChildren: 0.05,
          },
        },
      }}
      className="w-full"
      role="list"
      aria-label={t("platform.findingsDiagram.ariaLabel")}
    >
      {/* ── Desktop: horizontal chain ─────────────────────────────────── */}
      <div className="hidden md:block">
        <div className="flex items-stretch">
          {safeChain.map((node, i) => {
            const isLast = i === safeChain.length - 1;
            const isAccent = !!node.accent;

            return (
              <React.Fragment key={`${node.label}-${i}`}>
                <motion.div
                  role="listitem"
                  variants={{
                    hidden: { opacity: 0, y: 8 },
                    visible: {
                      opacity: 1,
                      y: 0,
                      transition: { duration: 0.5, ease: EASE },
                    },
                  }}
                  className="flex flex-1 flex-col"
                >
                  <div
                    className="relative flex flex-col rounded-xl bg-white px-4 py-4 text-start"
                    style={{
                      border: `1px solid ${isAccent ? "#C86B52" : "#E8E4DD"}`,
                      boxShadow: isAccent
                        ? "0 4px 16px rgba(200,107,82,0.08)"
                        : "0 1px 2px rgba(26,25,23,0.03)",
                      minHeight: 92,
                    }}
                  >
                    <div
                      className="text-[10px] font-medium uppercase tracking-[0.14em]"
                      style={{ color: isAccent ? "#C86B52" : "#A8A29E" }}
                    >
                      {t("platform.findingsDiagram.levelPrefix")} {String(i + 1).padStart(2, "0")}
                    </div>
                    <div
                      className="mt-1 text-body-sm font-semibold leading-tight tracking-[-0.005em]"
                      style={{ color: isAccent ? "#B55D46" : "#1A1917" }}
                    >
                      {node.label}
                    </div>
                    {node.meta && (
                      <div className="mt-1.5 text-meta leading-[1.4] text-[var(--text-secondary)] text-start">
                        {node.meta}
                      </div>
                    )}
                  </div>
                </motion.div>

                {/* Стрелка между узлами */}
                {!isLast && (
                  <motion.div
                    variants={{
                      hidden: { opacity: 0, scaleX: 0 },
                      visible: {
                        opacity: 1,
                        scaleX: 1,
                        transition: { duration: 0.35, ease: EASE },
                      },
                    }}
                    className="flex shrink-0 items-center justify-center"
                    style={{
                      width: 28,
                      transformOrigin: "left center",
                    }}
                    aria-hidden="true"
                  >
                    {/* RTL FIX: Зеркалирование стрелки для арабского языка (указывает влево) */}
                    <svg
                      width="28"
                      height="8"
                      viewBox="0 0 28 8"
                      className="text-[var(--text-faint)]"
                      fill="none"
                      style={{ transform: isRTL ? "scaleX(-1)" : "none" }}
                    >
                      <line
                        x1="0"
                        y1="4"
                        x2="22"
                        y2="4"
                        stroke="currentColor"
                        strokeWidth="1"
                      />
                      <path
                        d="M 22 1 L 27 4 L 22 7"
                        stroke="currentColor"
                        strokeWidth="1"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        fill="none"
                      />
                    </svg>
                  </motion.div>
                )}
              </React.Fragment>
            );
          })}
        </div>

        {/* Финальная подпись под цепочкой */}
        <motion.div
          variants={{
            hidden: { opacity: 0, y: 6 },
            visible: {
              opacity: 1,
              y: 0,
              transition: { duration: 0.5, ease: EASE, delay: 0.05 },
            },
          }}
          className="mt-6 flex items-center gap-2 text-meta text-[var(--text-muted)] text-start"
        >
          <span
            className="inline-block h-px w-6 bg-[#D6D0C7]"
            aria-hidden="true"
          />
          <span>
            {t("platform.findingsDiagram.footerNote")}
          </span>
        </motion.div>
      </div>

      {/* ── Mobile: vertical chain ────────────────────────────────────── */}
      <div className="flex flex-col gap-2 md:hidden">
        {safeChain.map((node, i) => {
          const isLast = i === safeChain.length - 1;
          const isAccent = !!node.accent;

          return (
            <React.Fragment key={`${node.label}-${i}`}>
              <motion.div
                variants={{
                  hidden: { opacity: 0, x: -6 },
                  visible: {
                    opacity: 1,
                    x: 0,
                    transition: { duration: 0.5, ease: EASE },
                  },
                }}
                className="rounded-xl bg-white px-4 py-3.5 text-start"
                style={{
                  border: `1px solid ${isAccent ? "#C86B52" : "#E8E4DD"}`,
                }}
              >
                <div className="flex items-baseline justify-between gap-3">
                  <div
                    className="text-[10px] font-medium uppercase tracking-[0.14em]"
                    style={{ color: isAccent ? "#C86B52" : "#A8A29E" }}
                  >
                    {t("platform.findingsDiagram.levelPrefix")} {String(i + 1).padStart(2, "0")}
                  </div>
                </div>
                <div
                  className="mt-1 text-body-sm font-semibold leading-tight"
                  style={{ color: isAccent ? "#B55D46" : "#1A1917" }}
                >
                  {node.label}
                </div>
                {node.meta && (
                  <div className="mt-1 text-meta leading-[1.4] text-[var(--text-secondary)] text-start">
                    {node.meta}
                  </div>
                )}
              </motion.div>

              {!isLast && (
                // RTL FIX: ml-6 заменен на ms-6 (логический отступ слева/справа в зависимости от языка)
                <div
                  className="ms-6 h-3 w-px bg-[#D6D0C7]"
                  aria-hidden="true"
                />
              )}
            </React.Fragment>
          );
        })}

        {/* Финальная подпись на мобильных */}
        <div className="mt-3 text-meta leading-[1.5] text-[var(--text-muted)] text-start">
          {t("platform.findingsDiagram.footerNote")}
        </div>
      </div>
    </motion.div>
  );
};

export default FindingsDiagram;
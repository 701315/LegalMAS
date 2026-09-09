import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useTranslation } from "react-i18next";

interface FlowSchemaProps {
  steps: string[];
  accentIndex?: number;
}

const EASE: [number, number, number, number] = [0.22, 1, 0.36, 1];

const FlowSchema: React.FC<FlowSchemaProps> = ({ steps, accentIndex }) => {
  const shouldReduceMotion = useReducedMotion();
  
  // RTL FIX: Инициализация i18n и определение направления
  const { t, i18n } = useTranslation("marketing");
  const isRTL = i18n.language === "ar";

  // RTL FIX: Защита от сбоев, если prop steps не передан или не является массивом
  const safeSteps = Array.isArray(steps) ? steps : [];

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
      className="w-full"
      role="list"
      aria-label={t("platform.flowSchema.ariaLabel")}
    >
      {/* ── Desktop: horizontal row ───────────────────────────────────── */}
      <div className="hidden md:flex md:items-stretch md:justify-between md:gap-0">
        {safeSteps.map((step, i) => {
          const isAccent = accentIndex === i;
          const isLast = i === safeSteps.length - 1;

          return (
            <React.Fragment key={`${step}-${i}`}>
              <motion.div
                role="listitem"
                variants={{
                  hidden: { opacity: 0, y: 8 },
                  visible: {
                    opacity: 1,
                    y: 0,
                    transition: { duration: 0.45, ease: EASE },
                  },
                }}
                className="flex flex-1 flex-col items-center"
              >
                <div
                  className="relative flex h-14 w-full items-center justify-center rounded-lg border bg-white px-3 text-center transition-colors"
                  style={{
                    borderColor: isAccent ? "#C86B52" : "#E8E4DD",
                    boxShadow: "0 1px 2px rgba(26,25,23,0.03)",
                  }}
                >
                  <span
                    className="text-eyebrow font-medium leading-tight"
                    style={{ color: isAccent ? "#B55D46" : "#1A1917" }}
                  >
                    {step}
                  </span>
                </div>

                <div className="mt-2.5 text-meta">
                  {String(i + 1).padStart(2, "0")}
                </div>
              </motion.div>

              {/* Соединительная линия со стрелкой */}
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
                  className="flex shrink-0 items-start pt-6"
                  style={{
                    width: 32,
                    // RTL FIX: В RTL анимация должна идти справа налево
                    transformOrigin: isRTL ? "right center" : "left center",
                  }}
                  aria-hidden="true"
                >
                  <svg
                    width="32"
                    height="8"
                    viewBox="0 0 32 8"
                    className="text-[var(--text-faint)]"
                    fill="none"
                    // RTL FIX: Зеркалирование стрелки для арабского языка (указывает влево)
                    style={{ transform: isRTL ? "scaleX(-1)" : "none" }}
                  >
                    <line
                      x1="0"
                      y1="4"
                      x2="26"
                      y2="4"
                      stroke="currentColor"
                      strokeWidth="1"
                    />
                    <path
                      d="M 26 1 L 31 4 L 26 7"
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

      {/* ── Mobile: vertical column ───────────────────────────────────── */}
      <div className="flex flex-col gap-2 md:hidden">
        {safeSteps.map((step, i) => {
          const isAccent = accentIndex === i;
          const isLast = i === safeSteps.length - 1;

          return (
            <React.Fragment key={`${step}-${i}`}>
              <motion.div
                variants={{
                  hidden: { opacity: 0, x: -6 },
                  visible: {
                    opacity: 1,
                    x: 0,
                    transition: { duration: 0.4, ease: EASE },
                  },
                }}
                className="flex items-center gap-3 rounded-lg border bg-white px-4 py-3"
                style={{
                  borderColor: isAccent ? "#C86B52" : "#E8E4DD",
                }}
              >
                <span className="text-meta">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span
                  className="text-sm font-medium"
                  style={{ color: isAccent ? "#B55D46" : "#1A1917" }}
                >
                  {step}
                </span>
              </motion.div>

              {!isLast && (
                // RTL FIX: ml-6 заменен на ms-6 (логический отступ)
                <div
                  className="ms-6 h-3 w-px bg-[#D6D0C7]"
                  aria-hidden="true"
                />
              )}
            </React.Fragment>
          );
        })}
      </div>
    </motion.div>
  );
};

export default FlowSchema;
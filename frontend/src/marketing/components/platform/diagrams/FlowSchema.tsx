// src/marketing/components/platform/diagrams/FlowSchema.tsx

import React from "react";
import { motion, useReducedMotion } from "framer-motion";

/**
 * FlowSchema — универсальная горизонтальная пайплайн-схема.
 *
 * Используется в PlatformWorkflowSection для отображения последовательности:
 *   Документ → Classification → Analysis → Findings → DD Grid → Review → Decision
 *
 * Композиция:
 *   • Ряд карточек с подписями шагов
 *   • Между ними — тонкие соединительные линии со стрелками
 *   • На мобильных: превращается в вертикальную колонку
 *
 * Принципы:
 *   • Без иконок — только текст. Иконки бы шумели и делали схему «слишком SaaS».
 *   • Ноды одинакового размера, нейтральные — никаких цветных бейджей.
 *   • Появление узлов последовательное (staggerChildren в родителе).
 */

interface FlowSchemaProps {
  steps: string[];
  /**
   * Опционально подсвечивает индекс акцентным цветом (используется, если
   * нужно выделить конкретный шаг). По умолчанию не подсвечивает ничего.
   */
  accentIndex?: number;
}

// Отдельная кривая для консистентности с остальными анимациями
const EASE: [number, number, number, number] = [0.22, 1, 0.36, 1];

const FlowSchema: React.FC<FlowSchemaProps> = ({ steps, accentIndex }) => {
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
      className="w-full"
      role="list"
      aria-label="Процесс анализа документов"
    >
      {/* ── Desktop: horizontal row ───────────────────────────────────── */}
      <div className="hidden md:flex md:items-stretch md:justify-between md:gap-0">
        {steps.map((step, i) => {
          const isAccent = accentIndex === i;
          const isLast = i === steps.length - 1;

          return (
            <React.Fragment key={step}>
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
                    className="text-[0.8125rem] font-medium leading-tight"
                    style={{ color: isAccent ? "#B55D46" : "#1A1917" }}
                  >
                    {step}
                  </span>
                </div>

                {/* Порядковый номер под карточкой — сдержанный editorial-элемент */}
                <div className="mt-2.5 text-[10px] font-medium uppercase tracking-[0.18em] text-[#A8A29E]">
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
                    transformOrigin: "left center",
                  }}
                  aria-hidden="true"
                >
                  <svg
                    width="32"
                    height="8"
                    viewBox="0 0 32 8"
                    className="text-[#D6D0C7]"
                    fill="none"
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
        {steps.map((step, i) => {
          const isAccent = accentIndex === i;
          const isLast = i === steps.length - 1;

          return (
            <React.Fragment key={step}>
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
                <span className="text-[10px] font-medium uppercase tracking-[0.18em] text-[#A8A29E]">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span
                  className="text-[0.875rem] font-medium"
                  style={{ color: isAccent ? "#B55D46" : "#1A1917" }}
                >
                  {step}
                </span>
              </motion.div>

              {!isLast && (
                <div
                  className="ml-6 h-3 w-px bg-[#D6D0C7]"
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




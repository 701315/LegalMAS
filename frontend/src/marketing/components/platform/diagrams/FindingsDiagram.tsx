// src/marketing/components/platform/diagrams/FindingsDiagram.tsx

import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import type { ChainNode } from "./VerticalNodeChain";

/**
 * FindingsDiagram — цепочка узлов для Section 4 (Structured Results).
 *
 * Отличается от VerticalNodeChain концептуально:
 *   • VerticalNodeChain — линейный список сверху вниз, простые линии
 *   • FindingsDiagram   — «lineage-цепочка»: каждый узел имеет метку «уровня»
 *     (Document → Clause → Risk → Severity → Source Link), а последний узел
 *     Source Link визуально выделен как «конечная точка проверяемости»
 *
 * Визуальная логика:
 *   Показать, что каждый finding — это не «текстовый вывод», а структура
 *   с чётко очерченными компонентами, каждый из которых прослеживается
 *   до первоисточника. Финальный узел (Source Link) — акцентный:
 *   ощущение «проверяемого якоря».
 *
 * Композиция:
 *   • Горизонтальная цепочка на десктопе (5 узлов + 4 стрелки между ними)
 *   • Каждый узел — компактная карточка с уровнем (Level 1, Level 2 …)
 *     и label
 *   • Стрелки между узлами — тонкие, направленные слева направо
 *   • Последний узел (Source Link) обведён terracotta с лёгким свечением
 *   • На мобильных — вертикальная цепочка, стрелки становятся вертикальными
 */

interface FindingsDiagramProps {
  chain: ChainNode[];
}

const EASE: [number, number, number, number] = [0.22, 1, 0.36, 1];

const FindingsDiagram: React.FC<FindingsDiagramProps> = ({ chain }) => {
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
            staggerChildren: 0.09,
            delayChildren: 0.05,
          },
        },
      }}
      className="w-full"
      role="list"
      aria-label="Структура finding"
    >
      {/* ── Desktop: horizontal chain ─────────────────────────────────── */}
      <div className="hidden md:block">
        <div className="flex items-stretch">
          {chain.map((node, i) => {
            const isLast = i === chain.length - 1;
            const isAccent = !!node.accent;

            return (
              <React.Fragment key={node.label}>
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
                    className="relative flex flex-col rounded-xl bg-white px-4 py-4"
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
                      Level {String(i + 1).padStart(2, "0")}
                    </div>
                    <div
                      className="mt-1 text-[0.9375rem] font-semibold leading-tight tracking-[-0.005em]"
                      style={{ color: isAccent ? "#B55D46" : "#1A1917" }}
                    >
                      {node.label}
                    </div>
                    {node.meta && (
                      <div className="mt-1.5 text-[0.75rem] leading-[1.4] text-[#78756F]">
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
                    <svg
                      width="28"
                      height="8"
                      viewBox="0 0 28 8"
                      className="text-[#D6D0C7]"
                      fill="none"
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

        {/* Финальная подпись под цепочкой — editorial-акцент на проверяемости */}
        <motion.div
          variants={{
            hidden: { opacity: 0, y: 6 },
            visible: {
              opacity: 1,
              y: 0,
              transition: { duration: 0.5, ease: EASE, delay: 0.05 },
            },
          }}
          className="mt-6 flex items-center gap-2 text-[0.75rem] text-[#A8A29E]"
        >
          <span
            className="inline-block h-px w-6 bg-[#D6D0C7]"
            aria-hidden="true"
          />
          <span>
            Каждый finding прослеживается от первоисточника до вывода
          </span>
        </motion.div>
      </div>

      {/* ── Mobile: vertical chain ────────────────────────────────────── */}
      <div className="flex flex-col gap-2 md:hidden">
        {chain.map((node, i) => {
          const isLast = i === chain.length - 1;
          const isAccent = !!node.accent;

          return (
            <React.Fragment key={node.label}>
              <motion.div
                variants={{
                  hidden: { opacity: 0, x: -6 },
                  visible: {
                    opacity: 1,
                    x: 0,
                    transition: { duration: 0.5, ease: EASE },
                  },
                }}
                className="rounded-xl bg-white px-4 py-3.5"
                style={{
                  border: `1px solid ${isAccent ? "#C86B52" : "#E8E4DD"}`,
                }}
              >
                <div className="flex items-baseline justify-between gap-3">
                  <div
                    className="text-[10px] font-medium uppercase tracking-[0.14em]"
                    style={{ color: isAccent ? "#C86B52" : "#A8A29E" }}
                  >
                    Level {String(i + 1).padStart(2, "0")}
                  </div>
                </div>
                <div
                  className="mt-1 text-[0.9375rem] font-semibold leading-tight"
                  style={{ color: isAccent ? "#B55D46" : "#1A1917" }}
                >
                  {node.label}
                </div>
                {node.meta && (
                  <div className="mt-1 text-[0.75rem] leading-[1.4] text-[#78756F]">
                    {node.meta}
                  </div>
                )}
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

        {/* Финальная подпись на мобильных */}
        <div className="mt-3 text-[0.75rem] leading-[1.5] text-[#A8A29E]">
          Каждый finding прослеживается от первоисточника до вывода.
        </div>
      </div>
    </motion.div>
  );
};

export default FindingsDiagram;



import React from "react";
import { motion, useReducedMotion } from "framer-motion";

export interface ChainNode {
  label: string;
  meta?: string;
  accent?: boolean;
}

interface VerticalNodeChainProps {
  nodes: ChainNode[];
  /**
   * Насколько «крупными» рисовать узлы.
   *   • "sm" — компактный вариант (структура документа, Section 2)
   *   • "md" — стандартный (Section 5)
   */
  size?: "sm" | "md";
}

const EASE: [number, number, number, number] = [0.22, 1, 0.36, 1];

const VerticalNodeChain: React.FC<VerticalNodeChainProps> = ({
  nodes,
  size = "sm",
}) => {
  const shouldReduceMotion = useReducedMotion();

  const nodePadding = size === "md" ? "px-6 py-5" : "px-5 py-4";
  const labelSize = size === "md" ? "text-base" : "text-body-sm";
  const connectorHeight = size === "md" ? 28 : 22;

  // RTL FIX: Защитная проверка входящего массива
  const safeNodes = Array.isArray(nodes) ? nodes : [];

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
      className="flex w-full flex-col items-stretch"
      role="list"
    >
      {safeNodes.map((node, i) => {
        const isLast = i === safeNodes.length - 1;
        const { label, meta, accent } = node;

        return (
          <React.Fragment key={`${label}-${i}`}> {/* RTL FIX: Стабильный ключ */}
            <motion.div
              role="listitem"
              variants={{
                hidden: { opacity: 0, y: 10 },
                visible: {
                  opacity: 1,
                  y: 0,
                  transition: { duration: 0.5, ease: EASE },
                },
              }}
              className={`relative rounded-xl bg-white ${nodePadding} transition-colors`}
              style={{
                border: `1px solid ${accent ? "#C86B52" : "#E8E4DD"}`,
                boxShadow: accent
                  ? "0 4px 16px rgba(200,107,82,0.08)"
                  : "0 1px 2px rgba(26,25,23,0.03)",
              }}
            >
              <div className="flex items-baseline justify-between gap-4">
                {/* RTL FIX: Добавлен text-start для корректного выравнивания в арабском */}
                <div className="min-w-0 flex-1 text-start">
                  <div
                    className={`${labelSize} font-semibold leading-tight`}
                    style={{ color: accent ? "#B55D46" : "#1A1917" }}
                  >
                    {label}
                  </div>
                  {meta && (
                    <div className="mt-1 text-eyebrow text-[var(--text-secondary)] text-start">
                      {meta}
                    </div>
                  )}
                </div>

                {/* Номер шага автоматически окажется слева в RTL благодаря justify-between */}
                <div className="shrink-0 text-meta">
                  {String(i + 1).padStart(2, "0")}
                </div>
              </div>
            </motion.div>

            {/* Соединительная вертикальная линия */}
            {!isLast && (
              <motion.div
                variants={{
                  hidden: { opacity: 0, scaleY: 0 },
                  visible: {
                    opacity: 1,
                    scaleY: 1,
                    transition: { duration: 0.35, ease: EASE },
                  },
                }}
                aria-hidden="true"
                className="mx-auto w-px bg-[#D6D0C7]"
                style={{
                  height: connectorHeight,
                  transformOrigin: "top center",
                }}
              />
            )}
          </React.Fragment>
        );
      })}
    </motion.div>
  );
};

export default VerticalNodeChain;
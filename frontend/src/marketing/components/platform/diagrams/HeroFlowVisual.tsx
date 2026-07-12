// src/marketing/components/platform/diagrams/HeroFlowVisual.tsx

import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { HERO_CONTENT } from "../content/platformContent";

/**
 * HeroFlowVisual — минималистичная document-flow иллюстрация для hero-секции.
 *
 * Композиция:
 *   • Слева: 3 узла-источника (входящие документы) — приглушённые (input)
 *   • Центр: узел «Steloom» (обработка) — акцентный
 *   • Справа: 3 узла-результата (DD Grid, Findings, материалы для review) —
 *     чуть более выразительные (output)
 *   • Между ними — тонкие SVG-линии, показывающие поток
 *
 * Контраст ролей (обновлено):
 *   • Input: приглушённый бордер #EBE8E1, светло-серый фон
 *   • Center: акцентный terracotta бордер + мягкое свечение
 *   • Output: более чёткий бордер #DFDAD0, лёгкий тонированный фон
 *
 * Это создаёт визуальную считываемость: серые входы → яркий центр →
 * чуть более определённые выходы. Читатель видит «поток становится
 * структурированным».
 */

const HeroFlowVisual: React.FC = () => {
  const shouldReduceMotion = useReducedMotion();
  const { inputs, processing, outputs } = HERO_CONTENT.flowNodes;

  const nodeTransition = {
    duration: 0.5,
    ease: [0.22, 1, 0.36, 1] as [number, number, number, number],
  };

  const delays = {
    inputs: [0.05, 0.12, 0.19],
    lines1: 0.28,
    core: 0.42,
    lines2: 0.55,
    outputs: [0.68, 0.75, 0.82],
  };

  return (
    <div
      className="relative w-full"
      aria-hidden="true"
      style={{ aspectRatio: "1 / 1", maxWidth: 520, marginLeft: "auto" }}
    >
      {/* ── SVG-слой с соединительными линиями ─────────────────────────── */}
      <svg
        viewBox="0 0 400 400"
        className="absolute inset-0 h-full w-full"
        preserveAspectRatio="none"
      >
        {/* Линии от inputs к core — более приглушённые */}
        {[75, 200, 325].map((y, i) => (
          <motion.path
            key={`in-${i}`}
            d={`M 140 ${y} C 175 ${y}, 175 200, 200 200`}
            stroke="#DFDAD0"
            strokeWidth="1"
            fill="none"
            initial={shouldReduceMotion ? undefined : { pathLength: 0, opacity: 0 }}
            animate={
              shouldReduceMotion ? undefined : { pathLength: 1, opacity: 1 }
            }
            transition={{
              duration: 0.6,
              delay: delays.lines1 + i * 0.04,
              ease: [0.22, 1, 0.36, 1],
            }}
          />
        ))}

        {/* Линии от core к outputs — чуть более выраженные */}
        {[75, 200, 325].map((y, i) => (
          <motion.path
            key={`out-${i}`}
            d={`M 260 200 C 285 200, 285 ${y}, 320 ${y}`}
            stroke="#C8C1B4"
            strokeWidth="1"
            fill="none"
            initial={shouldReduceMotion ? undefined : { pathLength: 0, opacity: 0 }}
            animate={
              shouldReduceMotion ? undefined : { pathLength: 1, opacity: 1 }
            }
            transition={{
              duration: 0.6,
              delay: delays.lines2 + i * 0.04,
              ease: [0.22, 1, 0.36, 1],
            }}
          />
        ))}
      </svg>

      {/* ── Left column: INPUTS (приглушённые) ─────────────────────────── */}
      <div
        className="absolute inset-y-0 left-0 flex flex-col justify-between"
        style={{ width: "35%" }}
      >
        {inputs.map((label, i) => (
          <motion.div
            key={label}
            initial={shouldReduceMotion ? undefined : { opacity: 0, y: 8 }}
            animate={shouldReduceMotion ? undefined : { opacity: 1, y: 0 }}
            transition={{ ...nodeTransition, delay: delays.inputs[i] }}
            className="rounded-lg px-3 py-2.5"
            style={{
              border: "1px solid #EBE8E1",
              background: "#FAF8F5",
              boxShadow: "0 1px 2px rgba(26,25,23,0.02)",
            }}
          >
            <div
              className="text-[10px] font-medium uppercase tracking-[0.14em]"
              style={{ color: "#B8B2AA" }}
            >
              Input
            </div>
            <div
              className="mt-0.5 text-[0.8125rem] font-medium leading-tight"
              style={{ color: "#78756F" }}
            >
              {label}
            </div>
          </motion.div>
        ))}
      </div>

      {/* ── Center: Steloom (акцентный) ─────────────────────────────────── */}
      <div className="absolute inset-0 flex items-center justify-center">
        <motion.div
          initial={shouldReduceMotion ? undefined : { opacity: 0, y: 8 }}
          animate={shouldReduceMotion ? undefined : { opacity: 1, y: 0 }}
          transition={{ ...nodeTransition, delay: delays.core }}
          className="relative rounded-xl bg-white px-5 py-3.5"
          style={{
            border: "1px solid rgba(200,107,82,0.35)",
            boxShadow: "0 6px 20px rgba(200,107,82,0.12)",
            minWidth: 120,
          }}
        >
          <div
            className="pointer-events-none absolute -inset-px rounded-xl"
            style={{
              background:
                "linear-gradient(180deg, rgba(200,107,82,0.06) 0%, rgba(200,107,82,0) 100%)",
            }}
          />
          <div className="relative">
            <div
              className="text-[10px] font-medium uppercase tracking-[0.14em]"
              style={{ color: "#C86B52" }}
            >
              Analysis
            </div>
            <div className="mt-0.5 text-[0.9375rem] font-semibold leading-tight text-[#1A1917]">
              {processing}
            </div>
          </div>
        </motion.div>
      </div>

      {/* ── Right column: OUTPUTS (чуть выразительнее) ──────────────────── */}
      <div
        className="absolute inset-y-0 right-0 flex flex-col justify-between"
        style={{ width: "35%" }}
      >
        {outputs.map((label, i) => (
          <motion.div
            key={label}
            initial={shouldReduceMotion ? undefined : { opacity: 0, y: 8 }}
            animate={shouldReduceMotion ? undefined : { opacity: 1, y: 0 }}
            transition={{ ...nodeTransition, delay: delays.outputs[i] }}
            className="rounded-lg bg-white px-3 py-2.5"
            style={{
              border: "1px solid #D6D0C7",
              boxShadow: "0 2px 6px rgba(26,25,23,0.04)",
            }}
          >
            <div
              className="text-[10px] font-medium uppercase tracking-[0.14em]"
              style={{ color: "#8A857D" }}
            >
              Output
            </div>
            <div
              className="mt-0.5 text-[0.8125rem] font-medium leading-tight"
              style={{ color: "#1A1917" }}
            >
              {label}
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
};

export default HeroFlowVisual;


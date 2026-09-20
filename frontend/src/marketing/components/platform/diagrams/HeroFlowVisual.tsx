import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useTranslation } from "react-i18next";

const HeroFlowVisual: React.FC = () => {
  const shouldReduceMotion = useReducedMotion();
  
  // RTL FIX: Инициализация i18n и определение направления
  const { t, i18n } = useTranslation("marketing");
  const isRTL = i18n.language === "ar";

  // RTL FIX: Защита от сбоев при получении массивов из i18n
  const inputsRaw = t("platform.hero.flowNodes.inputs", { returnObjects: true });
  const inputs = Array.isArray(inputsRaw) ? inputsRaw : [];

  const outputsRaw = t("platform.hero.flowNodes.outputs", { returnObjects: true });
  const outputs = Array.isArray(outputsRaw) ? outputsRaw : [];

  const processing = t("platform.hero.flowNodes.processing");

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
      // RTL FIX: marginLeft заменен на ms-auto (логический отступ)
      style={{ aspectRatio: "1 / 1", maxWidth: 520, marginInlineStart: "auto" }}
    >
      {/* ── SVG-слой с соединительными линиями ─────────────────────────── */}
      <svg
        viewBox="0 0 400 400"
        className="absolute inset-0 h-full w-full"
        preserveAspectRatio="none"
        // RTL FIX: Зеркалирование SVG-кривых для арабского языка (поток справа налево)
        style={{ transform: isRTL ? "scaleX(-1)" : "none" }}
      >
        {/* Линии от inputs к core */}
        {[75, 200, 325].map((y, i) => (
          <motion.path
            key={`in-${i}`}
            d={`M 140 ${y} C 175 ${y}, 175 200, 200 200`}
            stroke="#DFDAD0"
            strokeWidth="1"
            fill="none"
            initial={shouldReduceMotion ? undefined : { pathLength: 0, opacity: 0 }}
            animate={shouldReduceMotion ? undefined : { pathLength: 1, opacity: 1 }}
            transition={{
              duration: 0.6,
              delay: delays.lines1 + i * 0.04,
              ease: [0.22, 1, 0.36, 1],
            }}
          />
        ))}

        {/* Линии от core к outputs */}
        {[75, 200, 325].map((y, i) => (
          <motion.path
            key={`out-${i}`}
            d={`M 260 200 C 285 200, 285 ${y}, 320 ${y}`}
            stroke="#C8C1B4"
            strokeWidth="1"
            fill="none"
            initial={shouldReduceMotion ? undefined : { pathLength: 0, opacity: 0 }}
            animate={shouldReduceMotion ? undefined : { pathLength: 1, opacity: 1 }}
            transition={{
              duration: 0.6,
              delay: delays.lines2 + i * 0.04,
              ease: [0.22, 1, 0.36, 1],
            }}
          />
        ))}
      </svg>

      {/* ── Left/Start column: INPUTS ─────────────────────────────────── */}
      {/* RTL FIX: left-0 заменен на start-0. В RTL это будет правый край, что корректно для начала потока */}
      <div
        className="absolute inset-y-0 start-0 flex flex-col justify-between"
        style={{ width: "35%" }}
      >
        {inputs.map((label, i) => (
          <motion.div
            key={`${label}-${i}`} // RTL FIX: Стабильный ключ
            initial={shouldReduceMotion ? undefined : { opacity: 0, y: 8 }}
            animate={shouldReduceMotion ? undefined : { opacity: 1, y: 0 }}
            transition={{ ...nodeTransition, delay: delays.inputs[i] }}
            className="rounded-lg px-3 py-2.5 text-start"
            style={{
              border: "1px solid #EBE8E1",
              background: "#FAF8F5",
              boxShadow: "0 1px 2px rgba(26,25,23,0.02)",
            }}
          >
            <div
              className="text-meta font-medium uppercase"
              style={{ color: "#B8B2AA" }}
            >
              {t("platform.heroFlowVisual.inputLabel")}
            </div>
            <div
              className="mt-0.5 text-eyebrow font-medium leading-tight"
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
          className="relative rounded-xl bg-white px-5 py-3.5 text-center"
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
              className="text-meta font-medium uppercase"
              style={{ color: "#C86B52" }}
            >
              {t("platform.heroFlowVisual.analysisLabel")}
            </div>
            <div className="mt-0.5 text-body-sm font-semibold leading-tight text-[var(--text-primary)]">
              {processing}
            </div>
          </div>
        </motion.div>
      </div>

      {/* ── Right/End column: OUTPUTS ─────────────────────────────────── */}
      {/* RTL FIX: right-0 заменен на end-0. В RTL это будет левый край, что корректно для конца потока */}
      <div
        className="absolute inset-y-0 end-0 flex flex-col justify-between"
        style={{ width: "35%" }}
      >
        {outputs.map((label, i) => (
          <motion.div
            key={`${label}-${i}`} // RTL FIX: Стабильный ключ
            initial={shouldReduceMotion ? undefined : { opacity: 0, y: 8 }}
            animate={shouldReduceMotion ? undefined : { opacity: 1, y: 0 }}
            transition={{ ...nodeTransition, delay: delays.outputs[i] }}
            className="rounded-lg bg-white px-3 py-2.5 text-start"
            style={{
              border: "1px solid #D6D0C7",
              boxShadow: "0 2px 6px rgba(26,25,23,0.04)",
            }}
          >
            <div
              className="text-meta font-medium uppercase"
              style={{ color: "#8A857D" }}
            >
              {t("platform.heroFlowVisual.outputLabel")}
            </div>
            <div
              className="mt-0.5 text-eyebrow font-medium leading-tight"
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
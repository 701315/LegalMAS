import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useTranslation } from "react-i18next";

interface StandardsDiagramProps {
  sources: string[];
  core: string;
  targets: string[];
}

const EASE: [number, number, number, number] = [0.22, 1, 0.36, 1];

const StandardsDiagram: React.FC<StandardsDiagramProps> = ({
  sources,
  core,
  targets,
}) => {
  const shouldReduceMotion = useReducedMotion();
  
  // RTL FIX: Инициализация i18n и определение направления
  const { t, i18n } = useTranslation("marketing");
  const isRTL = i18n.language === "ar";

  // RTL FIX: Защита от сбоев при получении массивов из props
  const safeSources = Array.isArray(sources) ? sources : [];
  const safeTargets = Array.isArray(targets) ? targets : [];

  // RTL FIX: Динамические направления анимации появления
  // В LTR: источники выезжают слева (-6), цели справа (6)
  // В RTL: источники (теперь справа) выезжают справа (6), цели (теперь слева) выезжают слева (-6)
  const slideFromStart = isRTL ? 6 : -6;
  const slideFromEnd = isRTL ? -6 : 6;

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
        // RTL FIX: Зеркалирование SVG-кривых для арабского языка (поток справа налево)
        style={{ transform: isRTL ? "scaleX(-1)" : "none" }}
      >
        {/* Sources → Core: 3 линии сходятся в центральный узел */}
        {[75, 200, 325].map((y, i) => (
          <motion.path
            key={`src-${i}`}
            d={`M 130 ${y} C 165 ${y}, 165 200, 200 200`}
            stroke="rgba(250, 248, 245, 0.14)"
            strokeWidth="1"
            fill="none"
            initial={shouldReduceMotion ? undefined : { pathLength: 0, opacity: 0 }}
            animate={shouldReduceMotion ? undefined : { pathLength: 1, opacity: 1 }}
            transition={{ duration: 0.7, delay: 0.25 + i * 0.04, ease: EASE }}
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
            initial={shouldReduceMotion ? undefined : { pathLength: 0, opacity: 0 }}
            animate={shouldReduceMotion ? undefined : { pathLength: 1, opacity: 1 }}
            transition={{ duration: 0.7, delay: 0.55 + i * 0.04, ease: EASE }}
          />
        ))}
      </svg>

      {/* ── Left/Start: sources ────────────────────────────────────────── */}
      {/* RTL FIX: left-0 заменен на start-0. В RTL это правый край (начало потока) */}
      <div
        className="absolute inset-y-0 start-0 flex flex-col justify-between"
        style={{ width: "32%" }}
      >
        {safeSources.map((label, i) => (
          <motion.div
            key={`${label}-${i}`} // RTL FIX: Стабильный ключ
            variants={{
              hidden: { opacity: 0, x: slideFromStart },
              visible: {
                opacity: 1,
                x: 0,
                transition: { duration: 0.5, ease: EASE, delay: i * 0.04 },
              },
            }}
            className="rounded-lg border px-3.5 py-2.5 text-start"
            style={{
              borderColor: "rgba(250, 248, 245, 0.14)",
              background: "rgba(250, 248, 245, 0.02)",
            }}
          >
            <div
              className="text-[10px] font-medium uppercase tracking-[0.14em]"
              style={{ color: "rgba(250, 248, 245, 0.45)" }}
            >
              {t("platform.standardsDiagram.inputLabel")}
            </div>
            <div
              className="mt-0.5 text-eyebrow font-medium leading-tight"
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
          className="relative rounded-xl px-5 py-3.5 text-center"
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
            {t("platform.standardsDiagram.engineLabel")}
          </div>
          <div
            className="mt-0.5 text-body-sm font-semibold leading-tight"
            style={{ color: "#FAF8F5" }}
          >
            {core}
          </div>
        </motion.div>
      </div>

      {/* ── Right/End: targets ────────────────────────────────────────── */}
      {/* RTL FIX: right-0 заменен на end-0. В RTL это левый край (конец потока) */}
      <div
        className="absolute inset-y-0 end-0 flex flex-col justify-between"
        style={{ width: "32%" }}
      >
        {safeTargets.map((label, i) => (
          <motion.div
            key={`${label}-${i}`} // RTL FIX: Стабильный ключ
            variants={{
              hidden: { opacity: 0, x: slideFromEnd },
              visible: {
                opacity: 1,
                x: 0,
                transition: { duration: 0.5, ease: EASE, delay: 0.72 + i * 0.04 },
              },
            }}
            className="rounded-lg border px-3.5 py-2.5 text-start"
            style={{
              borderColor: "rgba(250, 248, 245, 0.14)",
              background: "rgba(250, 248, 245, 0.02)",
            }}
          >
            <div
              className="text-[10px] font-medium uppercase tracking-[0.14em]"
              style={{ color: "rgba(250, 248, 245, 0.45)" }}
            >
              {t("platform.standardsDiagram.appliedToLabel")}
            </div>
            <div
              className="mt-0.5 text-eyebrow font-medium leading-tight"
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
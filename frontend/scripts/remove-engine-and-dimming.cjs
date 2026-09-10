const fs = require('fs');
const path = require('path');

const sectionPath = path.join(__dirname, '../src/marketing/components/platform/PlatformStandardsSection.tsx');
const diagramPath = path.join(__dirname, '../src/marketing/components/platform/diagrams/StandardsDiagram.tsx');

// 1. ОБНОВЛЕНИЕ PlatformStandardsSection.tsx (Без затемнения картинки)
const updatedSectionCode = `// src/marketing/components/platform/PlatformStandardsSection.tsx

import React from "react";
import { useTranslation } from "react-i18next";
import StandardsDiagram from "./diagrams/StandardsDiagram";

const PlatformStandardsSection: React.FC = () => {
  const { t } = useTranslation("marketing");

  const eyebrow = t("platform.standards.eyebrow");
  const title = t("platform.standards.title");
  const paragraphsRaw = t("platform.standards.paragraphs", { returnObjects: true });
  const paragraphs: string[] = Array.isArray(paragraphsRaw)
    ? paragraphsRaw.map((p) => String(p))
    : [];

  return (
    <section
      data-theme="dark"
      data-header-theme="dark"
      className="relative overflow-hidden border-b border-white/10 bg-[#1A1917] py-24 lg:py-36 text-white"
    >
      {/* 1. ФОНОВОЕ ИЗОБРАЖЕНИЕ — БЕЗ ЗАТЕМНЕНИЯ */}
      <div className="absolute inset-0 z-0 pointer-events-none">
        <img
          src="/platform-1-1.png"
          alt=""
          className="h-full w-full object-cover object-right"
        />
      </div>

      {/* 2. КОНТЕНТ СЕКЦИИ */}
      <div
        className="relative z-10 mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid grid-cols-1 gap-12 lg:grid-cols-12 lg:items-center">
          {/* Левая колонка — Текст */}
          <div className="lg:col-span-6">
            <span className="eyebrow !text-[var(--accent-primary)] brightness-110 text-start">
              {eyebrow}
            </span>
            <h2 className="mt-4 text-h1 !text-white text-start">
              {title}
            </h2>
            <div className="mt-6 space-y-4">
              {paragraphs.map((paragraph, idx) => (
                <p key={idx} className="text-body !text-[#D6D0C7] text-start">
                  {paragraph}
                </p>
              ))}
            </div>
          </div>

          {/* Правая колонка — Диаграмма */}
          <div className="lg:col-span-6">
            <div className="relative rounded-2xl border border-white/10 bg-black/40 p-4 backdrop-blur-md lg:p-6">
              <StandardsDiagram />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default PlatformStandardsSection;
`;

// 2. ОБНОВЛЕНИЕ StandardsDiagram.tsx (Без блока Engine)
const updatedDiagramCode = `import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useTranslation } from "react-i18next";

interface StandardsDiagramProps {
  sources?: string[];
  core?: string;
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

  const safeSources = Array.isArray(sources) && sources.length > 0 ? sources : ["Playbooks", "Policies", "Instructions"];
  const safeTargets = Array.isArray(targets) && targets.length > 0 ? targets : ["Document A", "Document B", "Document C"];

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
      {/* ── ПРЯМЫЕ ЛИНИИ СВЯЗИ (БЕЗ УЗЛА ENGINE) ───────────────────────── */}
      <svg
        viewBox="0 0 400 400"
        className="absolute inset-0 h-full w-full"
        preserveAspectRatio="none"
        style={{ transform: isRTL ? "scaleX(-1)" : "none" }}
      >
        {[75, 200, 325].map((y, i) => (
          <motion.path
            key={`line-${i}`}
            d={\`M 130 \${y} L 270 \${y}\`}
            stroke="rgba(250, 248, 245, 0.25)"
            strokeWidth="1.5"
            strokeDasharray="4 4"
            fill="none"
            initial={shouldReduceMotion ? undefined : { pathLength: 0, opacity: 0 }}
            animate={shouldReduceMotion ? undefined : { pathLength: 1, opacity: 1 }}
            transition={{ duration: 0.7, delay: 0.25 + i * 0.04, ease: EASE }}
          />
        ))}
      </svg>

      {/* ── Левая колонка: ИСТОЧНИКИ ───────────────────────────────────── */}
      <div
        className="absolute inset-y-0 start-0 flex flex-col justify-between"
        style={{ width: "32%" }}
      >
        {safeSources.map((label, i) => (
          <motion.div
            key={\`src-\${label}-\${i}\`}
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
              borderColor: "rgba(250, 248, 245, 0.2)",
              background: "rgba(0, 0, 0, 0.4)",
              backdropFilter: "blur(4px)",
            }}
          >
            <div
              className="text-meta font-medium uppercase"
              style={{ color: "rgba(250, 248, 245, 0.6)" }}
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

      {/* ── Правая колонка: ПРИМЕНЕНИЕ ────────────────────────────────── */}
      <div
        className="absolute inset-y-0 end-0 flex flex-col justify-between"
        style={{ width: "32%" }}
      >
        {safeTargets.map((label, i) => (
          <motion.div
            key={\`tgt-\${label}-\${i}\`}
            variants={{
              hidden: { opacity: 0, x: slideFromEnd },
              visible: {
                opacity: 1,
                x: 0,
                transition: { duration: 0.5, ease: EASE, delay: 0.4 + i * 0.04 },
              },
            }}
            className="rounded-lg border px-3.5 py-2.5 text-start"
            style={{
              borderColor: "rgba(250, 248, 245, 0.2)",
              background: "rgba(0, 0, 0, 0.4)",
              backdropFilter: "blur(4px)",
            }}
          >
            <div
              className="text-meta font-medium uppercase"
              style={{ color: "rgba(250, 248, 245, 0.6)" }}
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
`;

fs.writeFileSync(sectionPath, updatedSectionCode, 'utf-8');
console.log('✅ PlatformStandardsSection.tsx: темный оверлей удален, картинка чисто на фоне!');

fs.writeFileSync(diagramPath, updatedDiagramCode, 'utf-8');
console.log('✅ StandardsDiagram.tsx: блок Engine удален, элементы соединены напрямую!');


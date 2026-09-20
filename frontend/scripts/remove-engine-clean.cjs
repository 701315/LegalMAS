const fs = require('fs');
const path = require('path');

const sectionPath = path.join(__dirname, '../src/marketing/components/platform/PlatformStandardsSection.tsx');
const diagramPath = path.join(__dirname, '../src/marketing/components/platform/diagrams/StandardsDiagram.tsx');

const sectionCode = `// src/marketing/components/platform/PlatformStandardsSection.tsx

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

  const diagramData = t("platform.standards.diagram", { returnObjects: true }) as any;
  const sources = Array.isArray(diagramData?.sources) ? diagramData.sources : ["Playbooks", "Policies", "Instructions"];
  const targets = Array.isArray(diagramData?.targets) ? diagramData.targets : ["Document A", "Document B", "Document C"];

  return (
    <section
      data-theme="dark"
      data-header-theme="dark"
      className="relative overflow-hidden border-b border-white/10 bg-[#1A1917] py-24 lg:py-36 text-white"
    >
      {/* 1. ФОНОВОЕ ИЗОБРАЖЕНИЕ НА ВСЮ ВЫСОТУ — БЕЗ ЗАТЕМНЕНИЯ */}
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

          {/* Правая колонка — Диаграмма БЕЗ темной рамки и БЕЗ Engine */}
          <div className="lg:col-span-6 flex justify-center lg:justify-end">
            <StandardsDiagram sources={sources} targets={targets} />
          </div>
        </div>
      </div>
    </section>
  );
};

export default PlatformStandardsSection;
`;

const diagramCode = `// src/marketing/components/platform/diagrams/StandardsDiagram.tsx

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
          <React.Fragment key={\`lines-\${i}\`}>
            <motion.path
              d={\`M 130 \${y} L 270 \${y}\`}
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
                d={\`M 130 \${y} C 200 \${y}, 200 200, 270 200\`}
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
            key={\`src-\${label}-\${i}\`}
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
            key={\`tgt-\${label}-\${i}\`}
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
`;

fs.writeFileSync(sectionPath, sectionCode, 'utf-8');
console.log('✅ PlatformStandardsSection.tsx: затемнение картинки и темная рамка удалены!');

fs.writeFileSync(diagramPath, diagramCode, 'utf-8');
console.log('✅ StandardsDiagram.tsx: овал ENGINE полностью удален!');


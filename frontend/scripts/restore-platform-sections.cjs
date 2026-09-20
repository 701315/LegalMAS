const fs = require('fs');
const path = require('path');

const standardsPath = path.join(__dirname, '../src/marketing/components/platform/PlatformStandardsSection.tsx');
const methodologyPath = path.join(__dirname, '../src/marketing/components/platform/PlatformMethodologySection.tsx');

// 1. ТЁМНАЯ СЕКЦИЯ: Правила и стандарты (PlatformStandardsSection)
const standardsCode = `// src/marketing/components/platform/PlatformStandardsSection.tsx

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
      className="border-b border-white/10 bg-[#1A1917] py-20 lg:py-28 text-white"
    >
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid grid-cols-1 gap-12 lg:grid-cols-12 lg:items-center">
          {/* Левая колонка — Текст (Светлый на тёмном фоне) */}
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

          {/* Правая колонка — Диаграмма стандартов */}
          <div className="lg:col-span-6">
            <StandardsDiagram />
          </div>
        </div>
      </div>
    </section>
  );
};

export default PlatformStandardsSection;
`;

// 2. СВЕТЛАЯ СЕКЦИЯ: Методология (PlatformMethodologySection)
const methodologyCode = `// src/marketing/components/platform/PlatformMethodologySection.tsx

import React from "react";
import { useTranslation } from "react-i18next";
import VerticalNodeChain from "./diagrams/VerticalNodeChain";

interface ChainNode {
  label: string;
  meta: string;
  accent?: boolean;
}

const PlatformMethodologySection: React.FC = () => {
  const { t } = useTranslation("marketing");

  const eyebrow = t("platform.methodology.eyebrow");
  const title = t("platform.methodology.title");
  const leadIn = t("platform.methodology.leadIn");
  const paragraphsRaw = t("platform.methodology.paragraphs", { returnObjects: true });
  const paragraphs: string[] = Array.isArray(paragraphsRaw)
    ? paragraphsRaw.map((p) => String(p))
    : [];

  const chainRaw = t("platform.methodology.chain", { returnObjects: true });
  const chain: ChainNode[] = Array.isArray(chainRaw)
    ? (chainRaw as ChainNode[])
    : [];

  return (
    <section className="border-b border-[var(--border-color)] bg-[var(--bg-base)] py-20 lg:py-28">
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid grid-cols-1 gap-12 lg:grid-cols-12 lg:items-center">
          {/* Левая колонка — Текст (Тёмный на светлом фоне) */}
          <div className="lg:col-span-6">
            <span className="eyebrow text-start">{eyebrow}</span>
            <h2 className="mt-4 text-h1 text-start text-[var(--text-primary)]">
              {title}
            </h2>
            <p className="mt-6 font-serif text-h3 italic text-[var(--text-primary)] text-start">
              {leadIn}
            </p>
            <div className="mt-6 space-y-4">
              {paragraphs.map((paragraph, idx) => (
                <p key={idx} className="text-body text-start text-[var(--text-secondary)]">
                  {paragraph}
                </p>
              ))}
            </div>
          </div>

          {/* Правая колонка — Цепочка процессов */}
          <div className="lg:col-span-6">
            <VerticalNodeChain chain={chain} />
          </div>
        </div>
      </div>
    </section>
  );
};

export default PlatformMethodologySection;
`;

fs.writeFileSync(standardsPath, standardsCode, 'utf-8');
console.log('✅ PlatformStandardsSection.tsx: восстановлена ТЁМНАЯ секция «Правила и стандарты» со своей диаграммой!');

fs.writeFileSync(methodologyPath, methodologyCode, 'utf-8');
console.log('✅ PlatformMethodologySection.tsx: восстановлена СВЕТЛАЯ секция «Методология» с цепочкой процессов!');


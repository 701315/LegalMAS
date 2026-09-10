const fs = require('fs');
const path = require('path');

const sectionPath = path.join(__dirname, '../src/marketing/components/platform/PlatformStandardsSection.tsx');
const diagramPath = path.join(__dirname, '../src/marketing/components/platform/diagrams/StandardsDiagram.cjs');

const cleanSectionCode = `// src/marketing/components/platform/PlatformStandardsSection.tsx

import React from "react";
import { useTranslation } from "react-i18next";

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
      {/* 1. ЧИСТОЕ 3D ФОНОВОЕ ИЗОБРАЖЕНИЕ — СПРАВА */}
      <div className="absolute inset-y-0 right-0 z-0 w-full lg:w-1/2 pointer-events-none flex items-center justify-end">
        <img
          src="/platform-1-1.png"
          alt="Platform Standards"
          className="h-full w-auto max-w-none object-cover object-right"
        />
      </div>

      {/* 2. КОНТЕНТ СЕКЦИИ */}
      <div
        className="relative z-10 mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid grid-cols-1 gap-12 lg:grid-cols-12 lg:items-center">
          {/* Левая колонка — Текст */}
          <div className="lg:col-span-7">
            <span className="eyebrow !text-[var(--accent-primary)] brightness-110 text-start">
              {eyebrow}
            </span>
            <h2 className="mt-4 text-h1 !text-white text-start">
              {title}
            </h2>
            <div className="mt-6 space-y-4 max-w-2xl">
              {paragraphs.map((paragraph, idx) => (
                <p key={idx} className="text-body !text-[#D6D0C7] text-start">
                  {paragraph}
                </p>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default PlatformStandardsSection;
`;

fs.writeFileSync(sectionPath, cleanSectionCode, 'utf-8');
console.log('✅ PlatformStandardsSection.tsx: Все наложенные плашки, плавающие карточки и линии полностью удалены!');


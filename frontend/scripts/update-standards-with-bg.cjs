const fs = require('fs');
const path = require('path');

const standardsPath = path.join(__dirname, '../src/marketing/components/platform/PlatformStandardsSection.tsx');

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
      className="relative overflow-hidden border-b border-white/10 bg-[#1A1917] py-24 lg:py-36 text-white"
    >
      {/* 1. ФОНОВОЕ ИЗОБРАЖЕНИЕ НА ВСЮ ВЫСОТУ БЛОКА */}
      <div className="absolute inset-0 z-0 pointer-events-none">
        <img
          src="/platform-1-1.png"
          alt=""
          className="h-full w-full object-cover object-right opacity-35 filter brightness-90 contrast-110"
        />
        {/* Плавный тёмный градиент для легкого чтения текста слева */}
        <div className="absolute inset-0 bg-gradient-to-r from-[#1A1917] via-[#1A1917]/85 to-transparent" />
      </div>

      {/* 2. КОНТЕНТ СЕКЦИИ */}
      <div
        className="relative z-10 mx-auto w-full px-6 lg:px-8"
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

          {/* Правая колонка — Диаграмма / Схема стандартов */}
          <div className="lg:col-span-6">
            <div className="relative rounded-2xl border border-white/10 bg-black/30 p-4 backdrop-blur-sm lg:p-6">
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

fs.writeFileSync(standardsPath, standardsCode, 'utf-8');
console.log('✅ PlatformStandardsSection.tsx: фоновое изображение /platform-1-1.png успешно установлено на всю высоту блока!');

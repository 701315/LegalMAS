const fs = require('fs');
const path = require('path');

const sectionPath = path.join(__dirname, '../src/marketing/components/platform/PlatformStandardsSection.tsx');

const fixedSectionCode = `// src/marketing/components/platform/PlatformStandardsSection.tsx

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
      className="relative overflow-hidden border-b border-white/10 bg-[#1A1917] py-20 lg:py-28 text-white min-h-[640px] lg:min-h-[720px] flex items-center"
    >
      <div
        className="relative z-10 mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid grid-cols-1 gap-12 lg:grid-cols-12 lg:items-center">
          {/* Левая колонка — Текст (RU & EN) */}
          <div className="lg:col-span-6 xl:col-span-6">
            <span className="eyebrow !text-[var(--accent-primary)] brightness-110 text-start">
              {eyebrow}
            </span>
            <h2 className="mt-4 text-h1 !text-white text-start">
              {title}
            </h2>
            <div className="mt-6 space-y-4 max-w-xl">
              {paragraphs.map((paragraph, idx) => (
                <p key={idx} className="text-body !text-[#D6D0C7] text-start">
                  {paragraph}
                </p>
              ))}
            </div>
          </div>

          {/* Правая колонка — 3D Изображение с четким размером и выравниванием */}
          <div className="lg:col-span-6 xl:col-span-6 flex justify-center lg:justify-end">
            <div className="relative w-full max-w-[500px] lg:max-w-[560px] xl:max-w-[620px] aspect-square flex items-center justify-center">
              <img
                src="/platform-1-1.png"
                alt="Platform Standards"
                className="w-full h-full object-contain pointer-events-none drop-shadow-2xl select-none"
              />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default PlatformStandardsSection;
`;

fs.writeFileSync(sectionPath, fixedSectionCode, 'utf-8');
console.log('✅ PlatformStandardsSection.tsx: Верстка и позиционирование картинки успешно исправлены для всех языков!');

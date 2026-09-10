const fs = require('fs');
const path = require('path');

const sectionPath = path.join(__dirname, '../src/marketing/components/platform/PlatformStandardsSection.tsx');

const updatedSectionCode = `// src/marketing/components/platform/PlatformStandardsSection.tsx

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
      className="relative overflow-hidden border-b border-white/10 bg-[#1A1917] py-20 lg:py-28 text-white min-h-[580px] lg:min-h-[660px] flex items-center"
    >
      {/* 1. 3D КОЛЕСО НА ВСЮ ВЫСОТУ ТЕМНОГО БЛОКА */}
      <div className="absolute inset-y-0 right-0 z-0 h-full w-full lg:w-[55%] pointer-events-none flex items-center justify-end overflow-hidden">
        <img
          src="/platform-1-1.png"
          alt="Platform Standards"
          className="h-full w-auto max-w-none object-cover lg:object-contain object-right scale-[1.35] lg:scale-[1.45] translate-x-8 lg:translate-x-12 mix-blend-screen select-none"
        />
      </div>

      {/* 2. ТЕКСТОВЫЙ КОНТЕНТ СЕКЦИИ (СЛЕВА) */}
      <div
        className="relative z-10 mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid grid-cols-1 gap-12 lg:grid-cols-12 lg:items-center">
          <div className="lg:col-span-7 xl:col-span-6">
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
        </div>
      </div>
    </section>
  );
};

export default PlatformStandardsSection;
`;

fs.writeFileSync(sectionPath, updatedSectionCode, 'utf-8');
console.log('✅ PlatformStandardsSection.tsx: 3D колесо успешно растянуто на всю высоту блока без квадратных рамок!');

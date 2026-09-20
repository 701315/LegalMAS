const fs = require('fs');
const path = require('path');

const standardsPath = path.join(__dirname, '../src/marketing/components/platform/PlatformStandardsSection.tsx');

const fixedStandardsCode = `// src/marketing/components/platform/PlatformStandardsSection.tsx

import React from "react";
import { useTranslation } from "react-i18next";
import StandardsDiagram from "./diagrams/StandardsDiagram";

const PlatformStandardsSection: React.FC = () => {
  const { t } = useTranslation("marketing");

  const eyebrow = t("platform.standards.eyebrow");
  const title = t("platform.standards.title");
  const paragraphsRaw = t("platform.standards.paragraphs", { returnObjects: true });
  const paragraphs: string[] = Array.isArray(paragraphsRaw)
    ? paragraphsRaw.map((p) => String(item => item))
    : [];

  return (
    <section className="border-b border-[var(--border-color)] bg-[var(--bg-base)] py-20 lg:py-28">
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid grid-cols-1 gap-12 lg:grid-cols-12 lg:items-center">
          {/* Левая колонка — Текст */}
          <div className="lg:col-span-6">
            <span className="eyebrow text-start">{eyebrow}</span>
            <h2 className="mt-4 text-h1 text-start text-[var(--text-primary)]">
              {title}
            </h2>
            <div className="mt-6 space-y-4">
              {Array.isArray(paragraphsRaw) && paragraphsRaw.map((paragraph: string, idx: number) => (
                <p key={idx} className="text-body text-start text-[var(--text-secondary)]">
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

fs.writeFileSync(standardsPath, fixedStandardsCode, 'utf-8');
console.log('✅ PlatformStandardsSection.tsx успешно восстановлен со своими ключами [platform.standards]!');


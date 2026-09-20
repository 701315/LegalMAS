// frontend/src/components/marketing/demo/DemoHeroSection.tsx
import React from "react";
import { useTranslation } from "react-i18next";

const DemoHeroSection: React.FC = () => {
  const { t } = useTranslation("marketing");

  return (
    <section className="border-b border-[var(--border-color)] pb-14 pt-12 lg:pb-20 lg:pt-16">
      {/* RTL FIX: Добавлен text-start для корректного выравнивания бейджа */}
      <div className="badge text-start">
        {t("demo.hero.eyebrow")}
      </div>
      
      {/* RTL FIX: Добавлен text-start для корректного выравнивания заголовка в RTL */}
      <h1 className="mt-8 max-w-4xl text-display text-[var(--text-primary)] sm:text-6xl text-display text-start whitespace-pre-line">
        {t("demo.hero.title")}
      </h1>
      
      {/* RTL FIX: Добавлен text-start для корректного выравнивания описания в RTL */}
      <p className="mt-6 max-w-2xl text-base leading-8 text-[var(--text-secondary)] text-start">
        {t("demo.hero.description")}
      </p>
    </section>
  );
};

export default DemoHeroSection;


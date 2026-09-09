// frontend/src/components/marketing/demo/DemoWhatYouSeeSection.tsx
import React from "react";
import { useTranslation } from "react-i18next";
// Импортируйте иконки, которые использовались в оригинальном demoContent.ts.
// Здесь приведены типичные иконки для LegalTech — замените при необходимости.
import { FileSearch, ShieldAlert, Link2, Workflow, type LucideIcon } from "lucide-react";

// RTL FIX: Маппинг стабильных ID из JSON на компоненты иконок.
// ВАЖНО: Замените иконки ниже на те, что были в вашем оригинальном demoContent.ts, если они отличаются.
const ICON_MAP: Record<string, LucideIcon> = {
  document_analysis: FileSearch,
  risk_detection: ShieldAlert,
  source_linking: Link2,
  workflow_automation: Workflow,
};

const DemoWhatYouSeeSection: React.FC = () => {
  const { t } = useTranslation("marketing");

  // RTL FIX: Защита от сбоев при получении массива из i18n
  const itemsRaw = t("demo.whatYouSee.items", { returnObjects: true });
  const items = Array.isArray(itemsRaw) ? itemsRaw : [];

  return (
    <section className="mt-12">
      <p className="eyebrow text-start">
        {t("demo.whatYouSee.eyebrow")}
      </p>
      <h2 className="section-title !mt-4 text-start">
        {t("demo.whatYouSee.title")}
      </h2>
      <div className="mt-8 grid gap-4 md:grid-cols-2">
        {items.map((item) => {
          // Получаем компонент иконки по стабильному ID, с фоллбеком на FileSearch
          const IconComponent = ICON_MAP[item.id] || FileSearch;
          
          return (
            <div 
              key={item.id} 
              className="rounded-xl border border-[var(--border-color)] bg-white p-7 text-start"
            >
              <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-[var(--border-color)] bg-[var(--bg-surface)]">
                <IconComponent className="h-5 w-5 text-[var(--text-secondary)]" />
              </div>
              <h3 className="mt-6 text-xl font-semibold tracking-tight text-[var(--text-primary)]">
                {item.title}
              </h3>
              <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
                {item.description}
              </p>
            </div>
          );
        })}
      </div>
    </section>
  );
};

export default DemoWhatYouSeeSection;



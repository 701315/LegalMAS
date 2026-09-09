import React from "react";
import { useTranslation } from "react-i18next";
// Импортируйте здесь те иконки, которые использовались в оригинальном demoContent.ts
import { Scale, ShieldCheck, FileSearch, type LucideIcon } from "lucide-react";

// RTL FIX: Маппинг стабильных ID из JSON на компоненты иконок.
// JSON не может хранить React-компоненты, поэтому мы разделяем данные и представление.
// ВАЖНО: Замените Scale, ShieldCheck, FileSearch на реальные иконки из вашего старого demoContent.ts, если они отличаются.
const ICON_MAP: Record<string, LucideIcon> = {
  legal: Scale,
  compliance: ShieldCheck,
  audit: FileSearch,
};

const DemoAudienceSection: React.FC = () => {
  const { t } = useTranslation('marketing');

  // RTL FIX: Защита от сбоев при получении массива из i18n
  const itemsRaw = t('demo.audience.items', { returnObjects: true });
  const items = Array.isArray(itemsRaw) ? itemsRaw : [];

  return (
    <section className="mt-12">
      <div className="rounded-2xl border border-[var(--border-color)] bg-[var(--bg-surface)] p-7 lg:p-9">
        <h2 className="text-h2 text-[var(--text-primary)] lg:text-4xl text-start">
          {t('demo.audience.title')}
        </h2>
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          {items.map((item) => {
            // Получаем компонент иконки по стабильному ID, с фоллбеком на Scale
            const IconComponent = ICON_MAP[item.id] || Scale;
            
            return (
              <div 
                key={item.id} 
                className="rounded-xl border border-[var(--border-color)] bg-white p-6 text-start"
              >
                <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-[var(--border-color)] bg-[var(--bg-base)]">
                  <IconComponent className="h-5 w-5 text-[var(--text-secondary)]" />
                </div>
                <h3 className="mt-5 text-h3 font-semibold text-[var(--text-primary)]">
                  {item.title}
                </h3>
                <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
                  {item.description}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
};

export default DemoAudienceSection;
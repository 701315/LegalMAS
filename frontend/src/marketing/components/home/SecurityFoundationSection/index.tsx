// src/marketing/components/home/SecurityFoundationSection/index.tsx
import React from "react";
import { Link } from "react-router-dom";
import { 
  ArrowRight, 
  ShieldCheck, 
  Lock, 
  Users, 
  History, 
  Activity, 
  Settings2 
} from "lucide-react";
import { useTranslation } from "react-i18next";

// Иконки вынесены отдельно, чтобы сопоставить их с данными из i18n по индексу
const SECURITY_ICONS = [
  <ShieldCheck key="shield" strokeWidth={1.2} className="h-7 w-7" />,
  <Lock key="lock" strokeWidth={1.2} className="h-7 w-7" />,
  <Users key="users" strokeWidth={1.2} className="h-7 w-7" />,
  <History key="history" strokeWidth={1.2} className="h-7 w-7" />,
  <Activity key="activity" strokeWidth={1.2} className="h-7 w-7" />,
  <Settings2 key="settings" strokeWidth={1.2} className="h-7 w-7" />
];

const SecurityFoundationSection: React.FC = () => {
  const { t, i18n } = useTranslation("marketing");
  const isRTL = i18n.language === "ar";

  // Безопасное получение массивов из i18n
  const teasersRaw = t("home.securityFoundation.teasers", { returnObjects: true });
  const teasers = Array.isArray(teasersRaw) 
    ? teasersRaw 
    : [];
    
  const paragraphsRaw = t("home.securityFoundation.paragraphs", { returnObjects: true });
  const paragraphs = Array.isArray(paragraphsRaw) 
    ? paragraphsRaw 
    : [t("home.securityFoundation.paragraphs")];

  const ctaLabel = t("home.securityFoundation.ctaLabel");

  return (
    <section
      id="security"
      className="relative flex min-h-screen items-center bg-[var(--bg-base)] py-20 lg:py-28 border-y border-[var(--border-color)] scroll-mt-0"
      data-header-theme="light"
    >
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid items-center gap-12 lg:grid-cols-12 lg:gap-20">
          
          {/* ── Левая колонка: 6 тезисов ── */}
          <div className="lg:col-span-7">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-12 gap-y-12 lg:gap-y-16">
              {teasers.map((item, i) => (
                <div key={i} className="flex flex-col group">
                  <div className="mb-5 text-[var(--accent-primary)] transition-transform duration-500 group-hover:-translate-y-1">
                    {SECURITY_ICONS[i]}
                  </div>
                  <h3 className="text-h3 font-medium text-[var(--text-primary)] mb-2">
                    {item.title}
                  </h3>
                  <p className="text-body-sm leading-relaxed text-[var(--text-secondary)] max-w-[280px]">
                    {item.desc}
                  </p>
                </div>
              ))}
            </div>
          </div>

          {/* ── Правая колонка: Текст ── */}
          <div className="flex flex-col justify-center lg:col-span-5 lg:sticky lg:top-32">
            <span className="eyebrow">{t("home.securityFoundation.eyebrow") || "Security"}</span>

            <h2 className="text-h2 !mt-2 text-[var(--text-primary)] whitespace-pre-line">
              {t("home.securityFoundation.title") || "Security built into the architecture"}
            </h2>

            <div className="mt-8 flex flex-col gap-6">
              {paragraphs.map((paragraph, index) => (
                <p key={index} className="text-body leading-relaxed text-[var(--text-secondary)]">
                  {paragraph}
                </p>
              ))}
            </div>

            <Link to="/security" className="cta-link mt-12 inline-flex items-center gap-2">
              {ctaLabel}
              {/* RTL FIX: разворот стрелки для арабского языка */}
              <ArrowRight 
                className="h-3.5 w-3.5" 
                style={{ 
                  transform: isRTL ? "rotate(180deg)" : "none",
                  transition: "transform 0.2s ease"
                }} 
              />
            </Link>
          </div>

        </div>
      </div>
    </section>
  );
};

export default SecurityFoundationSection;
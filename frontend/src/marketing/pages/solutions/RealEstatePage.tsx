import React from "react";
import { useTranslation } from "react-i18next";
import { ArrowRight } from "lucide-react";
import SiteHeader from "../../components/shared/SiteHeader";
import MarketingPageFooter from "../../components/shared/MarketingPageFooter";
import Reveal, { RevealItem } from "../../motion/Reveal";
import { useContactModal } from "../../context/ContactModalContext";

const RealEstatePage: React.FC = () => {
  const { openContactModal } = useContactModal();

  return (
    <div className="min-h-screen bg-base text-primary">
      <SiteHeader />
      <main style={{ paddingTop: 68 }}>
        <HeroSection onDemo={openContactModal} />
        <RiskSection />
        <HowItHelpsSection />
        <CTASection onDemo={openContactModal} />
      </main>
      <MarketingPageFooter />
    </div>
  );
};

export default RealEstatePage;

function HeroSection({ onDemo }: { onDemo: () => void }) {
  const { t, i18n } = useTranslation("marketing");
  const isRTL = i18n.language === "ar";

  const paragraphsRaw = t("solutions.realEstate.hero.paragraphs", { returnObjects: true });
  const paragraphs = Array.isArray(paragraphsRaw) ? paragraphsRaw : [];

  return (
    <section data-header-theme="light" className="bg-base">
      <div className="mx-auto w-full px-6 py-28 lg:px-8 lg:py-40" style={{ maxWidth: "var(--container-max-width)" }}>
        <Reveal>
          <div className="max-w-4xl">
            <RevealItem>
              <p className="eyebrow text-start">{t("solutions.realEstate.hero.eyebrow")}</p>
            </RevealItem>
            <RevealItem>
              {/* ИСПРАВЛЕНО: Заменен инлайн-стиль fontSize на семантический класс text-display */}
              <h1 className="mt-6 text-display text-start">
                {t("solutions.realEstate.hero.title")}
              </h1>
            </RevealItem>
            {paragraphs.map((p, i) => (
              <RevealItem key={i}>
                {/* ИСПРАВЛЕНО: Убраны дублирующие leading и color, так как text-body уже содержит их */}
                <p className="mt-6 text-body text-start">
                  {p}
                </p>
              </RevealItem>
            ))}
            <div className="mt-10">
              <button onClick={onDemo} className="cta-primary">
                {t("solutions.realEstate.hero.buttonLabel")}
                {/* RTL FIX: Разворот стрелки для арабского языка */}
                <ArrowRight 
                  className="h-3.5 w-3.5 ml-2" 
                  style={{ transform: isRTL ? "rotate(180deg)" : "none", transition: "transform 0.2s ease" }} 
                />
              </button>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function RiskSection() {
  const { t } = useTranslation("marketing");

  const itemsRaw = t("solutions.realEstate.risks.items", { returnObjects: true });
  const risks = Array.isArray(itemsRaw) ? itemsRaw : [];

  return (
    <section data-header-theme="light" className="bg-surface">
      <div className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32" style={{ maxWidth: "var(--container-max-width)" }}>
        <Reveal>
          <div className="max-w-4xl">
            <RevealItem>
              {/* ИСПРАВЛЕНО: text-h2 заменен на text-h2 для строгой семантики */}
              <h2 className="text-h2 text-start">{t("solutions.realEstate.risks.title")}</h2>
            </RevealItem>
            <div className="mt-12 grid gap-8 sm:grid-cols-3">
              {risks.map((item) => (
                <RevealItem key={item.id}>
                  <div className="rounded-xl border border-border bg-card p-6 h-full text-start">
                    {/* ИСПРАВЛЕНО: text-[var(--text-primary)] заменен на text-primary */}
                    <h3 className="text-h3 font-medium text-primary">{item.title}</h3>
                    <p className="mt-3 text-body-sm">{item.text}</p>
                  </div>
                </RevealItem>
              ))}
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function HowItHelpsSection() {
  const { t } = useTranslation("marketing");

  const benefitsRaw = t("solutions.realEstate.howItHelps.benefits", { returnObjects: true });
  const benefits = Array.isArray(benefitsRaw) ? benefitsRaw : [];

  return (
    <section data-header-theme="light" className="bg-base">
      <div className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32" style={{ maxWidth: "var(--container-max-width)" }}>
        <Reveal>
          <div className="max-w-4xl">
            <RevealItem>
              <h2 className="text-h2 text-start">{t("solutions.realEstate.howItHelps.title")}</h2>
            </RevealItem>
            <RevealItem>
              {/* ИСПРАВЛЕНО: Убраны дублирующие leading и color */}
              <p className="mt-6 text-body text-start">
                {t("solutions.realEstate.howItHelps.intro")}
              </p>
            </RevealItem>
            <div className="mt-12 grid gap-6 sm:grid-cols-2">
              {benefits.map((item) => (
                <RevealItem key={item.id}>
                  <div className="rounded-xl border border-border bg-card p-6 text-start">
                    {/* ИСПРАВЛЕНО: text-[var(--text-primary)] заменен на text-primary */}
                    <p className="text-body-sm text-primary">{item.text}</p>
                  </div>
                </RevealItem>
              ))}
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function CTASection({ onDemo }: { onDemo: () => void }) {
  const { t, i18n } = useTranslation("marketing");
  const isRTL = i18n.language === "ar";

  return (
    <section data-header-theme="light" className="bg-base">
      <div className="mx-auto w-full px-6 py-28 lg:px-8 lg:py-40" style={{ maxWidth: "var(--container-max-width)" }}>
        <Reveal>
          <div className="mx-auto max-w-[720px] text-center">
            <RevealItem>
              {/* ИСПРАВЛЕНО: bg-[var(--text-faint)] заменен на bg-faint */}
              <div className="mx-auto mb-10 h-px w-4 bg-faint" />
            </RevealItem>
            <RevealItem>
              <h2 className="text-h2">{t("solutions.realEstate.cta.title")}</h2>
            </RevealItem>
            <div className="mt-10">
              <button onClick={onDemo} className="cta-primary inline-flex items-center justify-center">
                {t("solutions.realEstate.cta.buttonLabel")}
                {/* RTL FIX: Разворот стрелки для арабского языка */}
                <ArrowRight 
                  className="h-3.5 w-3.5 ml-2" 
                  style={{ transform: isRTL ? "rotate(180deg)" : "none", transition: "transform 0.2s ease" }} 
                />
              </button>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useTranslation } from "react-i18next";
import SiteHeader from "../../components/shared/SiteHeader";
import MarketingPageFooter from "../../components/shared/MarketingPageFooter";
import PathCrumb from "../../components/platform/primitives/PathCrumb";
import Reveal, { RevealItem } from "../../motion/Reveal";
import { useContactModal } from "../../context/ContactModalContext";
import {
  ArrowRight,
  FileSearch,
  TrendingUp,
  Layers,
  CheckCircle2,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";

// RTL FIX: Маппинг строковых ID иконок из JSON в компоненты Lucide
const ICON_MAP: Record<string, LucideIcon> = {
  Layers,
  ShieldCheck,
  FileSearch,
  TrendingUp,
};

const ease: [number, number, number, number] = [0.22, 1, 0.36, 1];

const LawFirmsPage: React.FC = () => {
  const { openContactModal } = useContactModal();

  return (
    <div className="min-h-screen bg-base text-primary selection:bg-accent selection:text-white">
      <SiteHeader />

      <main style={{ paddingTop: 68 }}>
        <HeroSection onDemo={openContactModal} />
        <HowSteloomHelpsSection />
        <ScenariosSection />
        <CapabilitiesSection />
        <CTASection onDemo={openContactModal} />
      </main>

      <MarketingPageFooter />
    </div>
  );
};

export default LawFirmsPage;

function HeroSection({ onDemo }: { onDemo: () => void }) {
  const prefersReduced = useReducedMotion() ?? false;
  const { t, i18n } = useTranslation("marketing");
  const isRTL = i18n.language === "ar";

  return (
    <section data-header-theme="light" className="bg-base">
      <div
        className="mx-auto w-full px-6 pb-24 pt-20 lg:px-8 lg:pb-32 lg:pt-28"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <RevealItem>
            <PathCrumb 
              root={t("solutions.lawFirms.hero.eyebrowRoot")} 
              leaf={t("solutions.lawFirms.hero.eyebrowLeaf")} 
            />
          </RevealItem>

          <RevealItem>
            <div className="mt-12 lg:w-1/2">
              <p className="text-body text-start">
                {t("solutions.lawFirms.hero.intro")}
              </p>
            </div>
          </RevealItem>

          <RevealItem>
            <motion.div
              initial={prefersReduced ? undefined : { opacity: 0, y: 20 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.3, ease }}
              className="mt-16 relative overflow-hidden rounded-none border border-border bg-card shadow-sm"
            >
              <img
                src="/lo-1.jpg"
                alt="Law Firm Workspace"
                className="block h-auto w-full object-cover"
              />
            </motion.div>
          </RevealItem>

          <RevealItem>
            {/* ИСПРАВЛЕНО: Заменен инлайн-стиль fontSize на семантический класс text-display */}
            <h1 className="mt-20 lg:mt-32 text-display max-w-6xl whitespace-pre-line">
              {t("solutions.lawFirms.hero.titlePart1")}
              <br />
              <span className="italic font-light text-accent">
                {t("solutions.lawFirms.hero.titlePart2")}
              </span>
            </h1>
          </RevealItem>

          <RevealItem>
            <div className="mt-10">
              <button onClick={onDemo} className="cta-primary">
                {t("solutions.lawFirms.hero.buttonLabel")}
                {/* RTL FIX: Разворот стрелки для арабского языка */}
                <ArrowRight 
                  className="h-3.5 w-3.5" 
                  style={{ transform: isRTL ? "rotate(180deg)" : "none", transition: "transform 0.2s ease" }} 
                />
              </button>
            </div>
          </RevealItem>
        </Reveal>
      </div>
    </section>
  );
}

function HowSteloomHelpsSection() {
  const { t } = useTranslation("marketing");

  const itemsRaw = t("solutions.lawFirms.results.items", { returnObjects: true });
  const results = Array.isArray(itemsRaw) ? itemsRaw : [];

  return (
    <section data-header-theme="light" className="bg-base border-t border-border/50">
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <div className="max-w-2xl">
            <RevealItem>
              <p className="text-eyebrow mb-4 text-start">
                {t("solutions.lawFirms.results.eyebrow")}
              </p>
            </RevealItem>
          </div>

          <div className="mt-16 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
            {results.slice(0, 3).map((item) => (
              <RevealItem key={item.id}>
                <div className="flex flex-col h-full">
                  <div className="h-48 w-full overflow-hidden border border-border/40 bg-surface">
                    <img
                      src={item.image}
                      alt={item.title}
                      className="block h-full w-full object-cover"
                    />
                  </div>
                  <div className="pt-6 text-start">
                    <h3 className="text-h3 italic">
                      {item.title}
                    </h3>
                    <p className="mt-3 text-body-sm">
                      {item.text}
                    </p>
                  </div>
                </div>
              </RevealItem>
            ))}
          </div>

          <div className="mt-24 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
            {results.slice(3).map((item) => (
              <RevealItem key={item.id}>
                <div className="flex flex-col h-full">
                  <div className="h-48 w-full overflow-hidden border border-border/40 bg-surface">
                    <img
                      src={item.image}
                      alt={item.title}
                      className="block h-full w-full object-cover"
                    />
                  </div>
                  <div className="pt-6 text-start">
                    <h3 className="text-h3 italic">
                      {item.title}
                    </h3>
                    <p className="mt-3 text-body-sm">
                      {item.text}
                    </p>
                  </div>
                </div>
              </RevealItem>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function ScenariosSection() {
  const { t } = useTranslation("marketing");

  const itemsRaw = t("solutions.lawFirms.scenarios.items", { returnObjects: true });
  const scenarios = Array.isArray(itemsRaw) ? itemsRaw : [];

  return (
    <section
      data-header-theme="dark"
      className="relative overflow-hidden border-t border-white/10 text-white"
    >
      <div
        className="absolute inset-0 bg-center bg-cover bg-no-repeat"
        style={{ backgroundImage: 'url("/lf-2-2.png")' }}
      />
      <div className="absolute inset-0 bg-[#111111]/78" />
      <div className="absolute inset-0 bg-gradient-to-b from-black/20 via-black/35 to-black/55" />

      <div
        className="relative mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <p className="text-eyebrow uppercase tracking-[0.12em] text-white/55 font-medium mb-4 text-start">
            {t("solutions.lawFirms.scenarios.eyebrow")}
          </p>

          <h2 className="font-serif text-h2 tracking-[-0.02em] text-white mb-16 text-start">
            {t("solutions.lawFirms.scenarios.title")}
          </h2>

          <div className="space-y-0">
            {scenarios.map((item) => (
              <RevealItem key={item.id}>
                <div className="grid grid-cols-1 md:grid-cols-12 gap-8 py-8 border-t border-white/12">
                  <div className="md:col-span-4">
                    <h3 className="font-serif text-h3 tracking-tight text-white italic text-start">
                      {item.title}
                    </h3>
                  </div>
                  <div className="md:col-span-8">
                    {/* ИСПРАВЛЕНО: Убран избыточный leading-[1.7], так как text-body-sm уже содержит line-height */}
                    <p className="text-body-sm text-white/72 font-light max-w-2xl text-start">
                      {item.text}
                    </p>
                  </div>
                </div>
              </RevealItem>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function CapabilitiesSection() {
  const { t } = useTranslation("marketing");

  const itemsRaw = t("solutions.lawFirms.capabilities.items", { returnObjects: true });
  const capabilities = Array.isArray(itemsRaw) ? itemsRaw : [];

  return (
    <section data-header-theme="light" className="bg-base border-t border-border/50">
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <p className="text-eyebrow mb-4 text-start">
            {t("solutions.lawFirms.capabilities.eyebrow")}
          </p>
          <h2 className="font-serif text-h2 tracking-[-0.02em] text-primary mb-16 max-w-none text-start">
            {t("solutions.lawFirms.capabilities.title")}
          </h2>
          <div className="mt-16">
            {capabilities.map((item, index) => {
              const IconComponent = ICON_MAP[item.icon] || Layers;
              const bulletsRaw = t(`solutions.lawFirms.capabilities.items.${index}.bullets`, { returnObjects: true });
              const bullets = Array.isArray(bulletsRaw) ? bulletsRaw : [];

              return (
                <RevealItem key={item.id}>
                  <div className="grid grid-cols-1 md:grid-cols-12 gap-8 py-10 border-t border-border/60">
                    <div className="md:col-span-4 flex items-center gap-4">
                      <IconComponent className="h-5 w-5 text-accent opacity-50 flex-shrink-0" />
                      <h3 className="text-h3 italic text-start">
                        {item.title}
                      </h3>
                    </div>
                    <div className="md:col-span-8">
                      <ul className="space-y-3">
                        {bullets.map((bullet, bIndex) => (
                          <li key={`${item.id}-bullet-${bIndex}`} className="flex items-start gap-3 text-start">
                            <CheckCircle2 className="mt-1 h-4 w-4 text-accent opacity-50 flex-shrink-0" />
                            <span className="text-body-sm">
                              {bullet}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </RevealItem>
              );
            })}
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function CTASection({ onDemo }: { onDemo: () => void }) {
  const { t, i18n } = useTranslation("marketing");
  const isRTL = i18n.language === "ar";

  const paragraphsRaw = t("solutions.lawFirms.cta.paragraphs", { returnObjects: true });
  const paragraphs = Array.isArray(paragraphsRaw) ? paragraphsRaw : [];

  return (
    <section
      data-header-theme="light"
      className="bg-base py-28 lg:py-40 border-t border-border"
    >
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <div
            className="mx-auto flex flex-col items-center text-center"
            style={{ maxWidth: 720 }}
          >
            {/* ИСПРАВЛЕНО: bg-[#D6D0C7] заменен на bg-faint */}
            <div className="h-px w-16 bg-faint" aria-hidden="true" />
            <h2 className="mt-10 text-h1 whitespace-pre-line">
              {t("solutions.lawFirms.cta.titlePart1")}
              <br />
              <span className="italic font-light opacity-60 text-accent">
                {t("solutions.lawFirms.cta.titlePart2")}
              </span>
            </h2>
            {/* ИСПРАВЛЕНО: Убран избыточный leading-[1.75], так как text-body уже содержит его */}
            <div className="mt-7 space-y-5 text-body text-secondary">
              {paragraphs.map((p, i) => (
                <p key={i} className="text-start">{p}</p>
              ))}
            </div>
            <div className="mt-10">
              <button onClick={onDemo} className="cta-primary">
                {t("solutions.lawFirms.cta.buttonLabel")}
                {/* RTL FIX: Разворот стрелки для арабского языка */}
                <ArrowRight 
                  className="h-3.5 w-3.5" 
                  style={{ transform: isRTL ? "rotate(180deg)" : "none", transition: "transform 0.2s ease" }} 
                />
              </button>
            </div>
            <p className="mt-8 text-eyebrow text-muted">
              {t("solutions.lawFirms.cta.meta")}
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
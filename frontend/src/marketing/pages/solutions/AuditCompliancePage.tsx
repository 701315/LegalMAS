import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useTranslation } from "react-i18next";
import SiteHeader from "../../components/shared/SiteHeader";
import MarketingPageFooter from "../../components/shared/MarketingPageFooter";
import Reveal, { RevealItem } from "../../motion/Reveal";
import { useContactModal } from "../../context/ContactModalContext";
import {
  ArrowRight,
  FolderSearch,
  CheckCircle2,
  AlertTriangle,
  Scale,
  ClipboardCheck,
  BarChart3,
  ListChecks,
  FileWarning,
  ScanSearch,
  type LucideIcon,
} from "lucide-react";

// RTL FIX: Маппинг строковых ID иконок из JSON в компоненты Lucide
const ICON_MAP: Record<string, LucideIcon> = {
  FolderSearch,
  ListChecks,
  ClipboardCheck,
  Scale,
  AlertTriangle,
  BarChart3,
  FileWarning,
  ScanSearch,
};

const ease: [number, number, number, number] = [0.22, 1, 0.36, 1];

const AuditCompliancePage: React.FC = () => {
  const { openContactModal } = useContactModal();
  const prefersReduced = useReducedMotion() ?? false;

  return (
    <div className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)] selection:bg-[var(--color-accent)] selection:text-white">
      <SiteHeader />

      <main style={{ paddingTop: 68 }}>
        <HeroSection onDemo={openContactModal} prefersReduced={prefersReduced} />
        <AuditRoutinesIntroSection />
        <VisualCardsSection />
        <CapabilitiesSection />
        <SignalsSection />
        <CTASection onDemo={openContactModal} />
      </main>

      <MarketingPageFooter />
    </div>
  );
};

export default AuditCompliancePage;

function HeroSection({
  onDemo,
  prefersReduced,
}: {
  onDemo: () => void;
  prefersReduced: boolean;
}) {
  const { t, i18n } = useTranslation("marketing");
  const isRTL = i18n.language === "ar";

  // RTL FIX: Зеркалирование градиента для арабского языка
  const gradientStyle = {
    background: isRTL
      ? "linear-gradient(270deg, #1A1917 0%, rgba(26,25,23,0.96) 28%, rgba(26,25,23,0.58) 62%, transparent 100%)"
      : "linear-gradient(90deg, #1A1917 0%, rgba(26,25,23,0.96) 28%, rgba(26,25,23,0.58) 62%, transparent 100%)",
  };

  return (
    <section
      className="relative flex min-h-[68dvh] items-center overflow-hidden bg-[#1A1917]"
      data-header-theme="dark"
    >
      <div className="absolute inset-0 z-0">
        <motion.img
          src="/in-1-4.png"
          alt="Среда внутреннего аудита и контроля"
          className="h-full w-full object-cover object-center opacity-35 lg:opacity-55"
          initial={prefersReduced ? undefined : { scale: 1.02, opacity: 0 }}
          animate={prefersReduced ? undefined : { scale: 1, opacity: 0.55 }}
          transition={{ duration: 1.5, ease }}
        />
        <div className="absolute inset-0" style={gradientStyle} />
      </div>

      <div
        className="relative z-10 mx-auto w-full px-6 py-20 lg:px-8 lg:py-24"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid gap-12 lg:grid-cols-12 lg:gap-16">
          <div className="lg:col-span-7 xl:col-span-6">
            <motion.div
              initial={prefersReduced ? undefined : { opacity: 0, y: 12 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.05, ease }}
            >
              <div className="flex items-center gap-2 text-meta uppercase">
                <span className="text-[var(--text-secondary)]">{t("solutions.internalAudit.hero.eyebrowCategory")}</span>
                <span className="text-white/40" aria-hidden="true">/</span>
                <span className="text-[var(--text-secondary)]">{t("solutions.internalAudit.hero.eyebrowScenario")}</span>
              </div>
            </motion.div>

            <motion.h1
              className="mt-10 font-serif text-display !text-white whitespace-pre-line"
              initial={prefersReduced ? undefined : { opacity: 0, y: 14 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.22, ease }}
            >
              {t("solutions.internalAudit.hero.titlePart1")}
              <br />
              <span className="italic font-normal text-[var(--accent-primary)] brightness-125">
                {t("solutions.internalAudit.hero.titlePart2")}
              </span>
            </motion.h1>

            <motion.p
              className="mt-8 max-w-xl text-base leading-relaxed !text-[#D6D0C7] font-medium text-start"
              initial={prefersReduced ? undefined : { opacity: 0, y: 12 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.38, ease }}
            >
              {t("solutions.internalAudit.hero.description")}
            </motion.p>

            <motion.div
              className="mt-10"
              initial={prefersReduced ? undefined : { opacity: 0 }}
              animate={prefersReduced ? undefined : { opacity: 1 }}
              transition={{ delay: 0.52 }}
            >
              <button onClick={onDemo} className="cta-primary">
                {t("solutions.internalAudit.hero.buttonLabel")}
                {/* RTL FIX: Разворот стрелки для арабского языка */}
                <ArrowRight 
                  className="h-3.5 w-3.5" 
                  style={{ transform: isRTL ? "rotate(180deg)" : "none", transition: "transform 0.2s ease" }} 
                />
              </button>
            </motion.div>
          </div>
        </div>
      </div>
    </section>
  );
}

function AuditRoutinesIntroSection() {
  const { t } = useTranslation("marketing");

  const paragraphsRaw = t("solutions.internalAudit.intro.paragraphs", { returnObjects: true });
  const paragraphs = Array.isArray(paragraphsRaw) ? paragraphsRaw : [];

  return (
    <section className="bg-[var(--bg-base)] border-t border-[var(--border-color)]/50">
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-28"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <div className="grid grid-cols-1 gap-10 lg:grid-cols-12 lg:gap-16">
            <div className="lg:col-span-5">
              <p className="text-eyebrow mb-4 text-start">
                {t("solutions.internalAudit.intro.eyebrow")}
              </p>
              <h2 className="text-h1 whitespace-pre-line text-start">
                {t("solutions.internalAudit.intro.titlePart1")}
                <br />
                <span className="italic font-normal text-[var(--accent-primary)]">
                  {t("solutions.internalAudit.intro.titlePart2")}
                </span>
              </h2>
            </div>

            <div className="lg:col-span-7">
              <div className="space-y-6 text-body leading-relaxed text-[var(--text-secondary)]">
                {paragraphs.map((p, i) => (
                  <p key={i} className="text-start">{p}</p>
                ))}
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function VisualCardsSection() {
  const { t } = useTranslation("marketing");
  
  const cardsRaw = t("solutions.internalAudit.visualCards", { returnObjects: true });
  const cards = Array.isArray(cardsRaw) ? cardsRaw : [];

  return (
    <section className="bg-[var(--bg-base)] border-t border-[var(--border-color)]/50">
      <div
        className="mx-auto w-full px-6 py-20 lg:px-8 lg:py-24"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-3 lg:gap-10 items-stretch">
          {cards.map((card, index) => (
            <Reveal key={card.id} delay={index * 0.08}>
              <article className="group h-full">
                <div className="flex h-full flex-col overflow-hidden border border-[var(--border-color)]/50 bg-[var(--bg-surface)]">
                  <div className="relative aspect-[4/3] overflow-hidden bg-[#EFEAE2]">
                    <img
                      src={card.image}
                      alt={card.alt}
                      className="h-full w-full object-cover object-center transition-transform duration-700 ease-[cubic-bezier(0.22,1,0.36,1)] group-hover:scale-[1.03]"
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-[#1A1917]/12 via-transparent to-transparent" />
                  </div>

                  <div className="flex flex-1 flex-col px-6 py-7 lg:px-7 lg:py-8 bg-[var(--bg-surface)] text-start">
                    <h2 className="text-h2 font-serif italic text-[var(--text-primary)] text-start mb-3 leading-tight">
                  {card.title}
                </h2>
                    <p className="mt-4 text-body-sm text-start">
                      {card.text}
                    </p>
                  </div>
                </div>
              </article>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

function CapabilitiesSection() {
  const { t } = useTranslation("marketing");

  const itemsRaw = t("solutions.internalAudit.capabilities.items", { returnObjects: true });
  const capabilities = Array.isArray(itemsRaw) ? itemsRaw : [];

  return (
    <section className="bg-[var(--bg-base)] border-t border-[var(--border-color)]/50" data-header-theme="light">
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <div className="max-w-2xl mb-16">
            <p className="text-eyebrow mb-4 text-start">
              {t("solutions.internalAudit.capabilities.eyebrow")}
            </p>
            <h2 className="text-h1 whitespace-pre-line text-start">
              {t("solutions.internalAudit.capabilities.titlePart1")}
              <br />
              <span className="italic font-normal text-[var(--accent-primary)]">
                {t("solutions.internalAudit.capabilities.titlePart2")}
              </span>
            </h2>
          </div>
        </Reveal>

        <div className="mt-16">
          {capabilities.map((item, index) => {
            const IconComponent = ICON_MAP[item.icon] || FolderSearch;
            const bulletsRaw = t(`solutions.internalAudit.capabilities.items.${index}.bullets`, { returnObjects: true });
            const bullets = Array.isArray(bulletsRaw) ? bulletsRaw : [];

            return (
              <Reveal key={item.id} delay={index * 0.05}>
                <div className="grid grid-cols-1 md:grid-cols-12 gap-8 py-10 border-t border-[var(--border-color)]/60">
                  <div className="md:col-span-4">
                    <div className="flex items-center gap-3">
                      <IconComponent className="h-5 w-5 text-[var(--accent-primary)] opacity-50 flex-shrink-0" />
                      <h2 className="text-h3 font-serif italic text-[var(--text-primary)] text-start">
                        {item.title}
                      </h2>
                    </div>
                  </div>

                  <div className="md:col-span-8">
                    <ul className="space-y-4">
                      {bullets.map((bullet, bIndex) => (
                        <li key={`${item.id}-bullet-${bIndex}`} className="flex items-start gap-3 text-start">
                          <CheckCircle2 className="h-4 w-4 text-[var(--accent-primary)] opacity-50 flex-shrink-0 mt-1" />
                          <span className="text-body-sm">
                            {bullet}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </Reveal>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function SignalsSection() {
  const { t } = useTranslation("marketing");

  const signalsRaw = t("solutions.internalAudit.signals.items", { returnObjects: true });
  const signals = Array.isArray(signalsRaw) ? signalsRaw : [];

  return (
    <section className="bg-[var(--bg-base)] border-t border-[var(--border-color)]/50">
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-28"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <div className="grid grid-cols-1 gap-12 lg:grid-cols-12 lg:gap-16">
            <div className="lg:col-span-4">
              <p className="text-eyebrow mb-4 text-start">
                {t("solutions.internalAudit.signals.eyebrow")}
              </p>
              <h2 className="text-h1 text-start">
                {t("solutions.internalAudit.signals.title")}
              </h2>
              <p className="mt-5 text-body-sm leading-relaxed text-[var(--text-secondary)] max-w-md text-start">
                {t("solutions.internalAudit.signals.description")}
              </p>
            </div>

            <div className="lg:col-span-8">
              <div className="grid gap-x-10 gap-y-6 md:grid-cols-2">
                {signals.map((item) => {
                  const IconComponent = ICON_MAP[item.icon] || FileWarning;
                  return (
                    <RevealItem key={item.id}>
                      <div className="flex items-start gap-3 border-t border-[var(--border-color)]/60 pt-5 text-start">
                        <IconComponent className="h-4 w-4 text-[var(--accent-primary)] opacity-60 flex-shrink-0 mt-1" />
                        <p className="text-body-sm">
                          {item.text}
                        </p>
                      </div>
                    </RevealItem>
                  );
                })}
              </div>
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

  const paragraphsRaw = t("solutions.internalAudit.cta.paragraphs", { returnObjects: true });
  const paragraphs = Array.isArray(paragraphsRaw) ? paragraphsRaw : [];

  return (
    <section
      className="relative bg-[var(--bg-base)] py-28 lg:py-40 border-t border-[var(--border-color)]"
      data-header-theme="light"
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
            <div className="h-px w-16 bg-[#D6D0C7]" aria-hidden="true" />

            <h2 className="mt-10 text-h1 whitespace-pre-line">
              {t("solutions.internalAudit.cta.titlePart1")}
              <br />
              <span className="italic font-normal text-[var(--accent-primary)]">
                {t("solutions.internalAudit.cta.titlePart2")}
              </span>
            </h2>

            <div className="mt-7 space-y-5 text-body leading-relaxed text-[var(--text-secondary)]">
              {paragraphs.map((p, i) => (
                <p key={i} className="text-start">{p}</p>
              ))}
            </div>

            <div className="mt-10">
              <button onClick={onDemo} className="cta-primary">
                {t("solutions.internalAudit.cta.buttonLabel")}
                {/* RTL FIX: Разворот стрелки для арабского языка */}
                <ArrowRight 
                  className="h-3.5 w-3.5" 
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



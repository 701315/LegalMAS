import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useTranslation } from "react-i18next";
import SiteHeader from "../../components/shared/SiteHeader";
import MarketingPageFooter from "../../components/shared/MarketingPageFooter";
import PathCrumb from "../../components/platform/primitives/PathCrumb";
import Reveal from '../../motion/Reveal';
import { useContactModal } from "../../context/ContactModalContext";
import {
  ArrowRight,
  ClipboardCheck,
  FileSearch,
  History,
  Layers,
  GitCompare,
  ShieldCheck,
  CheckCircle2,
  type LucideIcon,
} from "lucide-react";

// RTL FIX: Маппинг строковых ID иконок из JSON в компоненты Lucide
const ICON_MAP: Record<string, LucideIcon> = {
  ClipboardCheck,
  FileSearch,
  History,
  Layers,
  GitCompare,
  ShieldCheck,
};

const ease: [number, number, number, number] = [0.22, 1, 0.36, 1];

const InternalAuditPage: React.FC = () => {
  const { openContactModal } = useContactModal();
  const prefersReduced = useReducedMotion() ?? false;

  return (
    <div className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)] selection:bg-[var(--color-accent)] selection:text-white">
      <SiteHeader />

      <main style={{ paddingTop: 68 }}>
        <HeroSection prefersReduced={prefersReduced} />
        <ThreePillarsSection />
        <CapabilitiesSection />
        <CTASection onDemo={openContactModal} />
      </main>

      <MarketingPageFooter />
    </div>
  );
};

export default InternalAuditPage;

function HeroSection({ prefersReduced }: { prefersReduced: boolean }) {
  const { t } = useTranslation("marketing");

  return (
    <section className="relative overflow-hidden bg-[var(--bg-base)]">
      <div
        className="mx-auto w-full px-6 pb-24 pt-20 lg:px-8 lg:pb-32 lg:pt-28"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <motion.div
          initial={prefersReduced ? undefined : { opacity: 0, y: 12 }}
          animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
          transition={{ duration: 0.55, delay: 0.05, ease }}
        >
          <PathCrumb 
            root={t("solutions.internalAuditPage.hero.eyebrowRoot")} 
            leaf={t("solutions.internalAuditPage.hero.eyebrowLeaf")} 
          />
        </motion.div>

        <motion.div
          initial={prefersReduced ? undefined : { opacity: 0, y: 16 }}
          animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.15, ease }}
          className="mt-8 relative overflow-hidden rounded-none border border-[var(--border-color)] bg-white shadow-sm"
        >
          <img
            src="/ia-1.jpg"
            alt="Internal Audit Traceability"
            className="w-full h-auto object-cover"
            style={{ maxHeight: 280 }}
          />
        </motion.div>

        <motion.div
          className="mt-12 lg:w-[55%]"
          initial={prefersReduced ? undefined : { opacity: 0, y: 12 }}
          animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
          transition={{ duration: 0.55, delay: 0.3, ease }}
        >
          <p className="text-body leading-relaxed text-[var(--text-secondary)] text-start">
            {t("solutions.internalAuditPage.hero.intro")}
          </p>
        </motion.div>

        <motion.h1
          className="mt-20 lg:mt-32 text-display max-w-6xl whitespace-pre-line"
          initial={prefersReduced ? undefined : { opacity: 0, y: 14 }}
          animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.45, ease }}
        >
          {t("solutions.internalAuditPage.hero.titlePart1")}
          <br />
          <span className="italic font-normal text-[var(--accent-primary)]">
            {t("solutions.internalAuditPage.hero.titlePart2")}
          </span>
        </motion.h1>
      </div>
    </section>
  );
}

function ThreePillarsSection() {
  const { t } = useTranslation("marketing");

  const pillarsRaw = t("solutions.internalAuditPage.pillars", { returnObjects: true });
  const pillars = Array.isArray(pillarsRaw) ? pillarsRaw : [];

  return (
    <section className="bg-[var(--bg-base)] border-t border-[var(--border-color)]/50 py-16 lg:py-24">
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 md:gap-12 divide-y md:divide-y-0 md:divide-x divide-[var(--border-color)]">
          {pillars.map((item, index) => {
            const IconComponent = ICON_MAP[item.icon] || ClipboardCheck;
            return (
              <div
                key={item.id || index}
                className="pt-8 md:pt-0 md:px-8 lg:px-12 flex flex-col items-start text-start first:pl-0 first:pt-0 last:pr-0"
              >
                <div className="h-40 w-full bg-[var(--bg-surface)] rounded-none mb-8 flex items-center justify-center border border-[var(--border-color)]">
                  <IconComponent className="h-10 w-10 text-[var(--accent-primary)] opacity-40" />
                </div>
                <h2 className="text-h2 font-serif italic text-[var(--text-primary)] mb-4 leading-tight">
                  {item.title}
                </h2>
                <p className="text-body leading-relaxed text-[var(--text-secondary)]">
                  {item.text}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function CapabilitiesSection() {
  const { t } = useTranslation("marketing");

  const itemsRaw = t("solutions.internalAuditPage.capabilities.items", { returnObjects: true });
  const capabilities = Array.isArray(itemsRaw) ? itemsRaw : [];

  return (
    <section className="bg-[var(--bg-base)] border-t border-[var(--border-color)]/50">
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <div className="max-w-2xl mb-16">
            <p className="text-eyebrow mb-4 text-start">
              {t("solutions.internalAuditPage.capabilities.eyebrow")}
            </p>
            <h2 className="text-h1 whitespace-pre-line text-start">
              {t("solutions.internalAuditPage.capabilities.titlePart1")}
              <br />
              <span className="italic font-normal text-[var(--accent-primary)]">
                {t("solutions.internalAuditPage.capabilities.titlePart2")}
              </span>
            </h2>
          </div>
        </Reveal>

        <div className="mt-16">
          {capabilities.map((item, index) => {
            const IconComponent = ICON_MAP[item.icon] || Layers;
            const bulletsRaw = t(`solutions.internalAuditPage.capabilities.items.${index}.bullets`, { returnObjects: true });
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

function CTASection({ onDemo }: { onDemo: () => void }) {
  const { t, i18n } = useTranslation("marketing");
  const isRTL = i18n.language === "ar";

  const paragraphsRaw = t("solutions.internalAuditPage.cta.paragraphs", { returnObjects: true });
  const paragraphs = Array.isArray(paragraphsRaw) ? paragraphsRaw : [];

  return (
    <section
      className="relative"
      style={{ background: '#FAF8F5' }}
      data-header-theme="light"
    >
      <div
        className="mx-auto w-full px-6 py-28 lg:px-8 lg:py-40"
        style={{ maxWidth: 'var(--container-max-width)' }}
      >
        <Reveal>
          <div
            className="mx-auto flex flex-col items-center text-center"
            style={{ maxWidth: 720 }}
          >
            <div className="h-px w-16 bg-[#D6D0C7]" aria-hidden="true" />

            <h2 className="mt-10 text-h1 whitespace-pre-line">
              {t("solutions.internalAuditPage.cta.titlePart1")}
              <br />
              <span className="italic font-light opacity-60 text-[var(--accent-primary)]">
                {t("solutions.internalAuditPage.cta.titlePart2")}
              </span>
            </h2>

            <div className="mt-7 space-y-5" style={{ maxWidth: 620 }}>
              {paragraphs.map((p, i) => (
                <p key={i} className="text-body leading-relaxed text-[var(--text-secondary)] text-start">
                  {p}
                </p>
              ))}
            </div>

            <div className="mt-10 flex items-center justify-center">
              <button
                type="button"
                onClick={onDemo}
                className="cta-primary"
              >
                {t("solutions.internalAuditPage.cta.buttonLabel")}
                {/* RTL FIX: Разворот стрелки для арабского языка */}
                <ArrowRight 
                  className="h-3.5 w-3.5" 
                  style={{ transform: isRTL ? "rotate(180deg)" : "none", transition: "transform 0.2s ease" }} 
                />
              </button>
            </div>

            <p className="mt-8 text-eyebrow leading-normal text-[var(--text-muted)]">
              {t("solutions.internalAuditPage.cta.meta")}
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
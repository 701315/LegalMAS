import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useTranslation } from "react-i18next";
import SiteHeader from "../../components/shared/SiteHeader";
import MarketingPageFooter from "../../components/shared/MarketingPageFooter";
import PathCrumb from "../../components/platform/primitives/PathCrumb";
import Reveal from '../../motion/Reveal';
import { useContactModal } from "../../context/ContactModalContext";
import { 
  ArrowRight, ShieldCheck, Zap, History, Building2, 
  CheckCircle2, AlertTriangle, Scale, ClipboardCheck,
  type LucideIcon,
} from "lucide-react";

// RTL FIX: Маппинг строковых ID иконок из JSON в компоненты Lucide
const ICON_MAP: Record<string, LucideIcon> = {
  ShieldCheck,
  Zap,
  History,
  Building2,
  AlertTriangle,
  Scale,
  ClipboardCheck,
};

const ease: [number, number, number, number] = [0.22, 1, 0.36, 1];

const CompliancePage: React.FC = () => {
  const { openContactModal } = useContactModal();
  const prefersReduced = useReducedMotion() ?? false;

  return (
    <div className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)] selection:bg-[var(--color-accent)] selection:text-white">
      <SiteHeader />

      <main style={{ paddingTop: 68 }}>
        <HeroSection onDemo={openContactModal} prefersReduced={prefersReduced} />
        <BriefBlocksSection />
        <CapabilitiesSection />
        <CTASection onDemo={openContactModal} />
      </main>

      <MarketingPageFooter />
    </div>
  );
};

export default CompliancePage;

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
      ? "linear-gradient(270deg, #1A1917 0%, rgba(26,25,23,0.95) 25%, rgba(26,25,23,0.4) 60%, transparent 100%)"
      : "linear-gradient(90deg, #1A1917 0%, rgba(26,25,23,0.95) 25%, rgba(26,25,23,0.4) 60%, transparent 100%)",
  };

  return (
    <section 
      className="relative flex min-h-[85dvh] items-center overflow-hidden bg-[#1A1917]"
      data-header-theme="dark"
    >
      <div className="absolute inset-0 z-0">
        <motion.img 
          src="/compl-1.png" 
          alt="Compliance Infrastructure" 
          className="h-full w-full object-cover object-center opacity-40 lg:opacity-60"
          initial={prefersReduced ? undefined : { scale: 1.02, opacity: 0 }}
          animate={prefersReduced ? undefined : { scale: 1, opacity: 0.6 }}
          transition={{ duration: 1.5, ease }}
        />
        <div className="absolute inset-0" style={gradientStyle} />
      </div>

      <div
        className="relative z-10 mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid gap-12 lg:grid-cols-12 lg:gap-16">
          <div className="lg:col-span-8 xl:col-span-7">
            <motion.div
              initial={prefersReduced ? undefined : { opacity: 0, y: 12 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.05, ease }}
            >
              <PathCrumb 
                root={t("solutions.compliance.hero.eyebrowRoot")} 
                leaf={t("solutions.compliance.hero.eyebrowLeaf")} 
              />
            </motion.div>

            <motion.div
              className="mt-12 max-w-xl"
              initial={prefersReduced ? undefined : { opacity: 0, y: 12 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.22, ease }}
            >
              <p className="text-body leading-[1.75] text-white/70 font-light text-start">
                {t("solutions.compliance.hero.description")}
              </p>
            </motion.div>

            <motion.h1
              className="mt-12 font-serif text-display leading-[1.05] tracking-[-0.03em] text-[var(--text-inverse)] whitespace-pre-line"
              initial={prefersReduced ? undefined : { opacity: 0, y: 14 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.4, ease }}
            >
              {t("solutions.compliance.hero.titlePart1")}
              <br />
              <span className="italic font-light text-[var(--accent-primary)] brightness-125">
                {t("solutions.compliance.hero.titlePart2")}
              </span>
            </motion.h1>

            <motion.div className="mt-12" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.6 }}>
              <button onClick={onDemo} className="cta-primary">
                {t("solutions.compliance.hero.buttonLabel")}
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

function BriefBlocksSection() {
  const { t } = useTranslation("marketing");

  const blocksRaw = t("solutions.compliance.briefBlocks", { returnObjects: true });
  const blocks = Array.isArray(blocksRaw) ? blocksRaw : [];

  return (
    <section className="bg-[var(--bg-base)] border-t border-[var(--border-color)]/50">
      <div className="mx-auto w-full px-6 lg:px-8" style={{ maxWidth: "var(--container-max-width)" }}>
        <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-[#E8E4DD]/60">
          {blocks.map((block, index) => {
            const IconComponent = ICON_MAP[block.icon] || ShieldCheck;
            return (
              <div 
                key={block.id} 
                className="py-16 md:px-8 lg:px-12 flex flex-col items-center text-center first:pl-0 last:pr-0"
              >
                <Reveal delay={index * 0.1}>
                  <div className="h-48 w-full bg-[var(--bg-surface)] rounded-none mb-8 flex items-center justify-center border border-[var(--border-color)]/40">
                    <IconComponent className="h-12 w-12 text-[var(--accent-primary)] opacity-30" />
                  </div>
                  <p className="text-body-sm text-start">
                    <strong className="text-[var(--text-primary)] block mb-2 font-serif italic text-lg tracking-tight">
                      {block.title}
                    </strong>
                    {block.text}
                  </p>
                </Reveal>
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

  const itemsRaw = t("solutions.compliance.capabilities.items", { returnObjects: true });
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
              {t("solutions.compliance.capabilities.eyebrow")}
            </p>
            <h2 className="text-h2 whitespace-pre-line text-start">
              {t("solutions.compliance.capabilities.titlePart1")}
              <br />
              <span className="italic font-light text-[var(--accent-primary)]">
                {t("solutions.compliance.capabilities.titlePart2")}
              </span>
            </h2>
          </div>
        </Reveal>

        <div className="mt-16">
          {capabilities.map((item, index) => {
            const IconComponent = ICON_MAP[item.icon] || Building2;
            const bulletsRaw = t(`solutions.compliance.capabilities.items.${index}.bullets`, { returnObjects: true });
            const bullets = Array.isArray(bulletsRaw) ? bulletsRaw : [];

            return (
              <Reveal key={item.id} delay={index * 0.05}>
                <div className="grid grid-cols-1 md:grid-cols-12 gap-8 py-10 border-t border-[var(--border-color)]/60">
                  <div className="md:col-span-4">
                    <div className="flex items-center gap-3">
                      <IconComponent className="h-5 w-5 text-[var(--accent-primary)] opacity-50 flex-shrink-0" />
                      <h3 className="text-h3 italic text-start">
                        {item.title}
                      </h3>
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

  const paragraphsRaw = t("solutions.compliance.cta.paragraphs", { returnObjects: true });
  const paragraphs = Array.isArray(paragraphsRaw) ? paragraphsRaw : [];

  return (
    <section className="relative bg-[var(--bg-base)] py-28 lg:py-40 border-t border-[var(--border-color)]" data-header-theme="light">
      <div className="mx-auto w-full px-6 lg:px-8" style={{ maxWidth: 'var(--container-max-width)' }}>
        <Reveal>
          <div className="mx-auto flex flex-col items-center text-center" style={{ maxWidth: 720 }}>
            <div className="h-px w-16 bg-[#D6D0C7]" aria-hidden="true" />
            <h2 className="mt-10 text-h1 whitespace-pre-line">
              {t("solutions.compliance.cta.titlePart1")}
              <br />
              <span className="italic font-light opacity-60 text-[var(--accent-primary)]">
                {t("solutions.compliance.cta.titlePart2")}
              </span>
            </h2>
            <div className="mt-7 space-y-5 text-body leading-[1.75] text-[var(--text-secondary)]">
              {paragraphs.map((p, i) => (
                <p key={i} className="text-start">{p}</p>
              ))}
            </div>
            <div className="mt-10">
              <button onClick={onDemo} className="cta-primary">
                {t("solutions.compliance.cta.buttonLabel")}
                {/* RTL FIX: Разворот стрелки для арабского языка */}
                <ArrowRight 
                  className="h-3.5 w-3.5" 
                  style={{ transform: isRTL ? "rotate(180deg)" : "none", transition: "transform 0.2s ease" }} 
                />
              </button>
            </div>
            <p className="mt-8 text-eyebrow leading-[1.6] text-[var(--text-muted)]">
              {t("solutions.compliance.cta.meta")}
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  );
}


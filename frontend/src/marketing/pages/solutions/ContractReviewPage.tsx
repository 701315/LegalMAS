import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useTranslation } from "react-i18next";
import SiteHeader from "../../components/shared/SiteHeader";
import MarketingPageFooter from "../../components/shared/MarketingPageFooter";
import PathCrumb from "../../components/platform/primitives/PathCrumb";
import Reveal from '../../motion/Reveal';
import { useContactModal } from "../../context/ContactModalContext";
import { ArrowRight, Library, AlertTriangle, Link as LinkIcon, type LucideIcon } from "lucide-react";

// RTL FIX: Маппинг строковых ID иконок из JSON в компоненты Lucide
const ICON_MAP: Record<string, LucideIcon> = {
  Library,
  AlertTriangle,
  Link: LinkIcon,
};

const ease: [number, number, number, number] = [0.22, 1, 0.36, 1];

const ContractReviewPage: React.FC = () => {
  const { openContactModal } = useContactModal();
  const prefersReduced = useReducedMotion() ?? false;

  return (
    <div className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)] selection:bg-[var(--color-accent)] selection:text-white">
      <SiteHeader />

      <main style={{ paddingTop: 68 }}>
        <HeroSection onDemo={openContactModal} prefersReduced={prefersReduced} />
        <ThreeBlocksSection />
        <CTASection onDemo={openContactModal} />
      </main>

      <MarketingPageFooter />
    </div>
  );
};

export default ContractReviewPage;

function HeroSection({
  onDemo,
  prefersReduced,
}: {
  onDemo: () => void;
  prefersReduced: boolean;
}) {
  const { t, i18n } = useTranslation("marketing");
  const isRTL = i18n.language === "ar";

  return (
    <section className="relative overflow-hidden bg-[var(--bg-base)]">
      <div
        className="mx-auto w-full px-6 pb-24 pt-20 lg:px-8 lg:pb-32 lg:pt-28"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        {/* 1.1 PathCrumb */}
        <motion.div
          initial={prefersReduced ? undefined : { opacity: 0, y: 12 }}
          animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
          transition={{ duration: 0.55, delay: 0.05, ease }}
          className="mb-12 lg:mb-16"
        >
          <PathCrumb 
            root={t("solutions.contractReview.hero.eyebrowRoot")} 
            leaf={t("solutions.contractReview.hero.eyebrowLeaf")} 
          />
        </motion.div>

        {/* 1.2 Grid Layout: Текст (1/3) и Картинка (2/3) */}
        <div className="grid gap-12 lg:grid-cols-12 lg:gap-16 items-start">
          
          {/* Левая колонка (1/3) */}
          <div className="lg:col-span-4">
            <motion.div
              initial={prefersReduced ? undefined : { opacity: 0, y: 12 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.22, ease }}
            >
              <p className="text-body text-start">
                {t("solutions.contractReview.hero.description")}
              </p>
              
              <div className="pt-8">
                <button onClick={onDemo} className="cta-primary">
                  {t("solutions.contractReview.hero.buttonLabel")}
                  {/* RTL FIX: Разворот стрелки для арабского языка */}
                  <ArrowRight 
                    className="h-3.5 w-3.5" 
                    style={{ transform: isRTL ? "rotate(180deg)" : "none", transition: "transform 0.2s ease" }} 
                  />
                </button>
              </div>
            </motion.div>
          </div>

          {/* Правая колонка (2/3) — Картинка cr-1.jpg */}
          <div className="lg:col-span-8">
            <motion.div
              initial={prefersReduced ? undefined : { opacity: 0, y: 20 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.4, ease }}
              className="relative overflow-hidden rounded-none border border-[var(--border-color)] bg-white shadow-sm"
            >
              <img 
                src="/cr-1.jpg" 
                alt="Contract Review Workspace" 
                className="w-full h-auto object-cover"
              />
            </motion.div>
          </div>
        </div>

        {/* 1.3 Large Serif Statement */}
        <motion.h1
          className="mt-20 lg:mt-32 text-display max-w-6xl whitespace-pre-line"
          initial={prefersReduced ? undefined : { opacity: 0, y: 14 }}
          animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.6, ease }}
        >
          {t("solutions.contractReview.hero.titlePart1")}
          <br />
          <span className="italic font-light text-[var(--accent-primary)]">
            {t("solutions.contractReview.hero.titlePart2")}
          </span>
        </motion.h1>
      </div>
    </section>
  );
}

function ThreeBlocksSection() {
  const { t } = useTranslation("marketing");

  const blocksRaw = t("solutions.contractReview.briefBlocks", { returnObjects: true });
  const blocks = Array.isArray(blocksRaw) ? blocksRaw : [];

  return (
    <section className="bg-[var(--bg-base)] border-t border-[var(--border-color)]/50">
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-[#E8E4DD]/60">
          {blocks.map((block, index) => {
            const IconComponent = ICON_MAP[block.icon] || Library;
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

function CTASection({ onDemo }: { onDemo: () => void }) {
  const { t, i18n } = useTranslation("marketing");
  const isRTL = i18n.language === "ar";

  const paragraphsRaw = t("solutions.contractReview.cta.paragraphs", { returnObjects: true });
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
              {t("solutions.contractReview.cta.titlePart1")}
              <br /> 
              <span className="italic font-light opacity-60 text-[var(--accent-primary)]">
                {t("solutions.contractReview.cta.titlePart2")}
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
                {t("solutions.contractReview.cta.buttonLabel")}
                {/* RTL FIX: Разворот стрелки для арабского языка */}
                <ArrowRight 
                  className="h-3.5 w-3.5" 
                  style={{ transform: isRTL ? "rotate(180deg)" : "none", transition: "transform 0.2s ease" }} 
                />
              </button>
            </div>
            <p className="mt-8 text-eyebrow leading-normal text-[var(--text-muted)]">
              {t("solutions.contractReview.cta.meta")}
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  );
}


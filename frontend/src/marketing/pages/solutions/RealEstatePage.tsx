// src/marketing/pages/solutions/RealEstatePage.tsx

import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useTranslation } from "react-i18next";
import { ArrowRight, ShieldAlert, FileSearch, CheckCircle2, Layers, Cpu, ShieldCheck, MapPin } from "lucide-react";

import SiteHeader from "../../components/shared/SiteHeader";
import MarketingPageFooter from "../../components/shared/MarketingPageFooter";
import { useContactModal } from "../../context/ContactModalContext";

const ease: [number, number, number, number] = [0.16, 1, 0.3, 1];

const RealEstatePage: React.FC = () => {
  const { openContactModal } = useContactModal();

  return (
    <div className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)] selection:bg-[var(--accent-primary)] selection:text-white">
      <SiteHeader />

      <main style={{ paddingTop: 68 }}>
        <HeroSection />
        <RisksSection />
        <IntelligenceCapabilitiesSection />
        <CTASection onDemo={openContactModal} />
      </main>

      <MarketingPageFooter />
    </div>
  );
};

export default RealEstatePage;

/* ─────────────────────────────────────────────────────────────────────────────
   1. HERO SECTION
───────────────────────────────────────────────────────────────────────────── */
function HeroSection() {
  const prefersReduced = useReducedMotion() ?? false;
  const { t } = useTranslation("marketing");

  return (
    <section data-theme="dark" data-header-theme="dark" className="relative overflow-hidden bg-[#1A1917] border-b border-white/10">
      <div
        className="relative z-10 mx-auto w-full px-6 pb-20 pt-16 lg:px-8 lg:pb-28 lg:pt-24"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <motion.div
          initial={prefersReduced ? undefined : { opacity: 0, y: 15 }}
          animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease }}
        >
          <div className="inline-flex items-baseline gap-2 text-meta font-medium uppercase mb-8">
            <span className="text-white/60">Solutions</span>
            <span className="text-white/30" aria-hidden="true">/</span>
            <span className="text-[var(--accent-primary)] brightness-110">
              {t("solutions.realEstate.hero.eyebrow")}
            </span>
          </div>
        </motion.div>

        <div className="mt-6 grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-16 items-center">
          <div className="lg:col-span-5">
            <motion.h1
              className="text-display max-w-xl whitespace-pre-line text-start !text-white"
              initial={prefersReduced ? undefined : { opacity: 0, y: 15 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.1, ease }}
            >
              {t("solutions.realEstate.hero.title")}
            </motion.h1>

            <motion.div
              className="mt-8 space-y-6 text-body leading-relaxed !text-[#D6D0C7] text-start max-w-xl"
              initial={prefersReduced ? undefined : { opacity: 0, y: 15 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.2, ease }}
            >
              <p>{t("solutions.realEstate.hero.p1")}</p>
              <p>{t("solutions.realEstate.hero.p2")}</p>
            </motion.div>
          </div>

          <motion.div
            initial={prefersReduced ? undefined : { opacity: 0, scale: 0.98 }}
            animate={prefersReduced ? undefined : { opacity: 1, scale: 1 }}
            transition={{ duration: 0.8, delay: 0.2, ease }}
            className="lg:col-span-7 relative overflow-hidden rounded-lg border border-white/10 bg-white/5 shadow-2xl flex items-center justify-center p-2"
          >
            <div className="absolute inset-0 bg-gradient-to-tr from-[#1A1917]/40 via-transparent to-transparent z-10 pointer-events-none" />
            <img
              src="/realestate.png"
              alt="Real Estate Analysis Verification"
              className="block w-full h-auto object-cover rounded shadow-lg relative z-0"
            />
          </motion.div>
        </div>
      </div>
    </section>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   2. RISKS SECTION
───────────────────────────────────────────────────────────────────────────── */
function RisksSection() {
  const { t } = useTranslation("marketing");
  
  const risks = [
    {
      id: "encumbrances",
      icon: ShieldAlert,
      title: t("solutions.realEstate.risks.i1.title"),
      text: t("solutions.realEstate.risks.i1.text")
    },
    {
      id: "outdated_data",
      icon: MapPin,
      title: t("solutions.realEstate.risks.i2.title"),
      text: t("solutions.realEstate.risks.i2.text")
    },
    {
      id: "verification_complexity",
      icon: FileSearch,
      title: t("solutions.realEstate.risks.i3.title"),
      text: t("solutions.realEstate.risks.i3.text")
    }
  ];

  return (
    <section className="bg-[var(--bg-base)] py-24 lg:py-32 border-t border-[var(--border-color)]/50">
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          className="mb-16"
        >
          <p className="text-eyebrow mb-4 text-start">{t("solutions.realEstate.risks.eyebrow")}</p>
          <h2 className="text-h1 text-start text-[var(--text-primary)]">
            {t("solutions.realEstate.risks.title")}
          </h2>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 md:gap-12 divide-y md:divide-y-0 md:divide-x divide-[var(--border-color)]">
          {risks.map((item, index) => {
            const Icon = item.icon;
            return (
              <motion.div
                key={item.id}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-50px" }}
                transition={{ delay: index * 0.1, duration: 0.5 }}
                className="pt-8 md:pt-0 md:px-8 lg:px-12 flex flex-col items-start text-start first:pl-0 first:pt-0 last:pr-0"
              >
                <div className="h-16 w-16 bg-[var(--bg-surface)] rounded-full mb-6 flex items-center justify-center border border-[var(--border-color)]">
                  <Icon className="h-7 w-7 text-[var(--accent-primary)] opacity-70" />
                </div>
                <h2 className="text-h2 font-serif italic text-[var(--text-primary)] mb-4 leading-tight">
                  {item.title}
                </h2>
                <p className="text-body leading-relaxed text-[var(--text-secondary)]">
                  {item.text}
                </p>
              </motion.div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   3. HOW IT HELPS SECTION
───────────────────────────────────────────────────────────────────────────── */
function IntelligenceCapabilitiesSection() {
  const { t } = useTranslation("marketing");

  const capabilities = [
    {
      icon: Cpu,
      title: t("solutions.realEstate.helps.cap1.title"),
      text: t("solutions.realEstate.helps.cap1.text")
    },
    {
      icon: Layers,
      title: t("solutions.realEstate.helps.cap2.title"),
      text: t("solutions.realEstate.helps.cap2.text")
    },
    {
      icon: ShieldCheck,
      title: t("solutions.realEstate.helps.cap3.title"),
      text: t("solutions.realEstate.helps.cap3.text")
    },
    {
      icon: CheckCircle2,
      title: t("solutions.realEstate.helps.cap4.title"),
      text: t("solutions.realEstate.helps.cap4.text")
    }
  ];

  return (
    <section data-theme="dark" data-header-theme="dark" className="bg-[#1A1917] py-24 lg:py-32 text-white border-t border-white/10">
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-16 lg:gap-24 items-center">
          <motion.div 
            className="lg:col-span-5"
            initial={{ opacity: 0, x: -20 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ duration: 0.6 }}
          >
            <p className="eyebrow !text-[var(--accent-primary)] brightness-110 mb-4 text-start">
              {t("solutions.realEstate.helps.eyebrow")}
            </p>
            <h2 className="text-h1 !text-white mb-6 text-start">
              {t("solutions.realEstate.helps.title")}
            </h2>
            <p className="text-body !text-[#D6D0C7] text-start leading-relaxed">
              {t("solutions.realEstate.helps.intro")}
            </p>
          </motion.div>

          <div className="lg:col-span-7">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              {capabilities.map((cap, index) => {
                const Icon = cap.icon;
                return (
                  <motion.div
                    key={index}
                    initial={{ opacity: 0, y: 15 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-50px" }}
                    transition={{ delay: index * 0.1, duration: 0.5 }}
                    className="p-6 border border-white/10 bg-white/5 rounded-none backdrop-blur-sm flex flex-col items-start text-start"
                  >
                    <Icon className="h-6 w-6 text-[var(--accent-primary)] mb-4 flex-shrink-0" />
                    <h3 className="text-h3 font-serif italic !text-white mb-2 leading-snug">
                      {cap.title}
                    </h3>
                    <p className="text-body-sm !text-[#D6D0C7] leading-relaxed">
                      {cap.text}
                    </p>
                  </motion.div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   4. CTA SECTION
───────────────────────────────────────────────────────────────────────────── */
function CTASection({ onDemo }: { onDemo: () => void }) {
  const { t, i18n } = useTranslation("marketing");
  const isRTL = i18n.language === "ar";

  return (
    <section className="relative py-28 lg:py-36 border-t border-[var(--border-color)] bg-[var(--bg-base)]">
      <div
        className="mx-auto w-full px-6 lg:px-8 text-center"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <motion.div 
          className="mx-auto flex flex-col items-center text-center" 
          style={{ maxWidth: 820 }}
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
        >
          <div className="h-px w-16 bg-[#D6D0C7]" aria-hidden="true" />

          <p className="eyebrow mt-10 text-start text-[var(--accent-primary)] uppercase tracking-widest font-bold">
            {t("solutions.realEstate.cta.eyebrow")}
          </p>

          <h2 className="mt-4 text-h1 whitespace-pre-line text-[var(--text-primary)] leading-tight">
            {t("solutions.realEstate.cta.title")}
          </h2>

          <p className="mt-6 text-body text-[var(--text-secondary)] leading-relaxed max-w-2xl text-center">
            {t("solutions.realEstate.cta.description")}
          </p>

          <div className="mt-10">
            <button onClick={onDemo} className="cta-primary">
              {t("solutions.realEstate.cta.buttonLabel")}
              <ArrowRight
                className="h-3.5 w-3.5 ml-2"
                style={{ transform: isRTL ? "rotate(180deg)" : "none", transition: "transform 0.2s ease" }}
              />
            </button>
          </div>
        </motion.div>
      </div>
    </section>
  );
}

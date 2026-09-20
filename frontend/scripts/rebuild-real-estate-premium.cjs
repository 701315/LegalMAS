const fs = require('fs');
const path = require('path');

const pagePath = path.join(__dirname, '../src/marketing/pages/solutions/RealEstatePage.tsx');

const productionCode = `// src/marketing/pages/solutions/RealEstatePage.tsx

import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useTranslation } from "react-i18next";
import { ArrowRight, ShieldAlert, FileSearch, CheckCircle2, Layers, Cpu, ShieldCheck, MapPin } from "lucide-react";

import SiteHeader from "../../components/shared/SiteHeader";
import MarketingPageFooter from "../../components/shared/MarketingPageFooter";
import PathCrumb from "../../components/platform/primitives/PathCrumb";
import ContactModal from "../../components/home/ContactModal";

const ease: [number, number, number, number] = [0.16, 1, 0.3, 1];

const RealEstatePage: React.FC = () => {
  const [contactModalOpen, setContactModalOpen] = React.useState(false);

  const openContactModal = () => setContactModalOpen(true);
  const closeContactModal = () => setContactModalOpen(false);

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

      <ContactModal open={contactModalOpen} onClose={closeContactModal} />
    </div>
  );
};

export default RealEstatePage;

/* ─────────────────────────────────────────────────────────────────────────────
   1. HERO SECTION (Dark Theme + realestate.png)
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
              Asset Intelligence & Title Verification
            </span>
          </div>
        </motion.div>

        <div className="mt-6 grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-16 items-center">
          {/* Текстовый блок (5 колонок) */}
          <div className="lg:col-span-5">
            <motion.h1
              className="text-display max-w-xl whitespace-pre-line text-start !text-white"
              initial={prefersReduced ? undefined : { opacity: 0, y: 15 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.1, ease }}
            >
              Real Estate & Property Rights Intelligence
            </motion.h1>

            <motion.div
              className="mt-8 space-y-6 text-body leading-relaxed !text-[#D6D0C7] text-start max-w-xl"
              initial={prefersReduced ? undefined : { opacity: 0, y: 15 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.2, ease }}
            >
              <p>
                In large-scale commercial real estate transactions and asset-heavy M&A deals, undetected title defects and unrecorded encumbrances can critically jeopardize deal value. Steloom automatically extracts addresses, cadastral IDs, land plot specs, and lease terms buried in unstructured Data Rooms.
              </p>
              <p>
                Every identified property asset is instantly reconciled with primary state registry records (EGRN, DLD, Land Registries) to verify title continuity, identify active mortgages, and surface hidden liabilities before the deal closes.
              </p>
            </motion.div>
          </div>

          {/* Изображение (7 колонок) */}
          <motion.div
            initial={prefersReduced ? undefined : { opacity: 0, scale: 0.98 }}
            animate={prefersReduced ? undefined : { opacity: 1, scale: 1 }}
            transition={{ duration: 0.8, delay: 0.2, ease }}
            className="lg:col-span-7 relative overflow-hidden rounded-lg border border-white/10 bg-white/5 shadow-2xl flex items-center justify-center p-2"
          >
            <div className="absolute inset-0 bg-gradient-to-tr from-[#1A1917]/40 via-transparent to-transparent z-10 pointer-events-none" />
            <img
              src="/realestate.png"
              alt="Real Estate and Rights Analysis Verification"
              className="block w-full h-auto object-cover rounded shadow-lg relative z-0"
            />
          </motion.div>
        </div>
      </div>
    </section>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   2. RISKS SECTION (Light Theme, 3 Columns)
───────────────────────────────────────────────────────────────────────────── */
function RisksSection() {
  const risks = [
    {
      id: "encumbrances",
      icon: ShieldAlert,
      title: "Hidden Encumbrances & Easements",
      text: "Pledges, third-party rights, and historical easements buried in annexes or historical title deeds routinely escape manual sampling, exposing the buyer to post-transaction litigation."
    },
    {
      id: "outdated_data",
      icon: MapPin,
      title: "Title & Registry Discrepancies",
      text: "Contractual descriptions frequently contradict current state registry data due to unrecorded zoning changes, illegal subdivisions, or outdated cadastral IDs."
    },
    {
      id: "verification_complexity",
      icon: FileSearch,
      title: "Manual Verification Bottlenecks",
      text: "Cross-referencing hundreds of contractual assets against fresh state registry extracts consumes hundreds of billable hours and delays deal closing."
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
          <p className="text-eyebrow mb-4 text-start">Property Risk Exposure</p>
          <h2 className="text-h1 text-start text-[var(--text-primary)]">
            Asset Verification & Legal Risks
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
   3. HOW IT HELPS SECTION (Dark Theme)
───────────────────────────────────────────────────────────────────────────── */
function IntelligenceCapabilitiesSection() {
  const capabilities = [
    {
      icon: Cpu,
      title: "Automated Cadastral & Asset Extraction",
      text: "Instant extraction of property boundaries, cadastral registration IDs, square footage, and usage designations across foreign or multi-jurisdictional agreements."
    },
    {
      icon: Layers,
      title: "Real-Time Registry Reconciliation",
      text: "Direct cross-matching of extracted property assets against official registries (EGRN, DLD, Land Registries) to flag active encumbrances, litigation, or arrests."
    },
    {
      icon: ShieldCheck,
      title: "Title Chain & Zoning Continuity Analysis",
      text: "Tracing historical ownership transfers and legal permitted use compliance to safeguard acquisition integrity and post-close development rights."
    },
    {
      icon: CheckCircle2,
      title: "Unified Property Dossier & Source Links",
      text: "Generating an interactive property ledger with direct deep-links to original contract paragraphs and official registry snapshots for seamless legal review."
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
              Unified Property Registry
            </p>
            <h2 className="text-h1 !text-white mb-6 text-start">
              Automate Commercial Real Estate Due Diligence
            </h2>
            <p className="text-body !text-[#D6D0C7] text-start leading-relaxed">
              The platform equips investment and legal teams with an interactive property analysis ledger—matching contractual commitments against live registry data with verifiable source citations.
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
  const { i18n } = useTranslation("marketing");
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
            Institutional Property Intelligence
          </p>

          <h2 className="mt-4 text-h1 whitespace-pre-line text-[var(--text-primary)] leading-tight">
            Streamline Real Estate Portfolio Due Diligence
          </h2>

          <p className="mt-6 text-body text-[var(--text-secondary)] leading-relaxed max-w-2xl text-center">
            Transform sprawling real estate documentation into a structured asset ledger. Empower your investment and legal teams to verify title continuity, identify undisclosed encumbrances, and accelerate closing cycles with absolute confidence.
          </p>

          <div className="mt-10">
            <button onClick={onDemo} className="cta-primary">
              Request a demonstration
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
`;

fs.writeFileSync(pagePath, productionCode, 'utf-8');
console.log('✅ RealEstatePage.tsx: Страница недвижимости полностью переработана! Темный Hero, крутые тексты, h2 заголовки и картинка realestate.png вставлены.');

const fs = require('fs');
const path = require('path');

const pagePath = path.join(__dirname, '../src/marketing/pages/solutions/CounterpartiesPage.tsx');

const productionCode = `// src/marketing/pages/solutions/CounterpartiesPage.tsx

import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useTranslation } from "react-i18next";
import { ArrowRight, Network, ShieldAlert, FileSearch, CheckCircle2, Layers, Cpu, ShieldCheck } from "lucide-react";

import SiteHeader from "../../components/shared/SiteHeader";
import MarketingPageFooter from "../../components/shared/MarketingPageFooter";
import PathCrumb from "../../components/platform/primitives/PathCrumb";
import ContactModal from "../../components/home/ContactModal";

const ease: [number, number, number, number] = [0.16, 1, 0.3, 1];

const CounterpartiesPage: React.FC = () => {
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

      <ContactModal isOpen={contactModalOpen} onClose={closeContactModal} />
    </div>
  );
};

export default CounterpartiesPage;

/* ─────────────────────────────────────────────────────────────────────────────
   1. HERO SECTION
───────────────────────────────────────────────────────────────────────────── */
function HeroSection() {
  const prefersReduced = useReducedMotion() ?? false;
  const { t } = useTranslation("marketing");

  return (
    <section data-header-theme="light" className="bg-[var(--bg-base)] border-b border-[var(--border-color)]/50">
      <div
        className="mx-auto w-full px-6 pb-20 pt-16 lg:px-8 lg:pb-28 lg:pt-24"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <motion.div
          initial={prefersReduced ? undefined : { opacity: 0, y: 15 }}
          animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease }}
        >
          <PathCrumb
            root="Solutions"
            leaf={t("solutions.counterparties.hero.eyebrow", "Asset Intelligence & Counterparty Review")}
          />
        </motion.div>

        <div className="mt-10 grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-16 items-center">
          {/* Текстовый блок (5 колонок) */}
          <div className="lg:col-span-5">
            <motion.h1
              className="text-display max-w-xl whitespace-pre-line text-start"
              initial={prefersReduced ? undefined : { opacity: 0, y: 15 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.1, ease }}
            >
              {t("solutions.counterparties.hero.title", "Counterparty & Related Party Intelligence")}
            </motion.h1>

            <motion.div
              className="mt-8 space-y-6 text-body leading-relaxed text-[var(--text-secondary)] text-start max-w-xl"
              initial={prefersReduced ? undefined : { opacity: 0, y: 15 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.2, ease }}
            >
              <p>
                {t("solutions.counterparties.hero.p1", "In complex M&A, cross-border restructuring, and corporate financing, undisclosed affiliations create severe legal and financial liabilities. Steloom automatically extracts, reconciles, and maps every corporate entity, officer, and related party buried across your deal room.")}
              </p>
              <p>
                {t("solutions.counterparties.hero.p2", "Legal and deal teams immediately see where each party appears, their exact contractual role, nominee involvement, and cumulative risk exposure across the entire transaction portfolio.")}
              </p>
            </motion.div>
          </div>

          {/* Изображение (7 колонок) */}
          <motion.div
            initial={prefersReduced ? undefined : { opacity: 0, scale: 0.98 }}
            animate={prefersReduced ? undefined : { opacity: 1, scale: 1 }}
            transition={{ duration: 0.8, delay: 0.2, ease }}
            className="lg:col-span-7 relative overflow-hidden border border-[var(--border-color)]/50 bg-[var(--bg-surface)] shadow-md"
          >
            <img
              src="/counterpaties picture.png"
              alt="Counterparty & Related Party Verification Network"
              className="block w-full h-auto object-cover"
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
  const { t } = useTranslation("marketing");
  
  const risks = [
    {
      id: "affiliation",
      icon: Network,
      title: t("solutions.counterparties.risks.i1.title", "Hidden Affiliation & UBO Chains"),
      text: t("solutions.counterparties.risks.i1.text", "Complex holding structures, nominee shareholders, and off-balance-sheet vehicles hidden inside schedules and side letters remain invisible during standard manual sampling.")
    },
    {
      id: "sanctions",
      icon: ShieldAlert,
      title: t("solutions.counterparties.risks.i2.title", "Dynamic Sanctions & PEP Exposure"),
      text: t("solutions.counterparties.risks.i2.text", "Manually cross-referencing hundreds of counterparties, directors, and signers against shifting international sanction lists and PEP databases creates critical compliance bottlenecks.")
    },
    {
      id: "fragmentation",
      icon: FileSearch,
      title: t("solutions.counterparties.risks.i3.title", "Unmapped Portfolio Exposure"),
      text: t("solutions.counterparties.risks.i3.text", "Cross-guarantees, parent indemnity clauses, and pending litigation liabilities are fragmented across hundreds of agreements without a centralized exposure ledger.")
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
          <p className="text-eyebrow mb-4 text-start">Operational Risks & Blind Spots</p>
          <h2 className="text-h1 text-start text-[var(--text-primary)]">
            {t("solutions.counterparties.risks.title", "Party Identification & Compliance Friction")}
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
  const { t } = useTranslation("marketing");

  const capabilities = [
    {
      icon: Cpu,
      title: "Full-Spectrum Entity & UBO Extraction",
      text: "Automatic recognition of legal names, tax IDs, beneficial owners, and key officers across foreign-language contracts, corporate charters, and court filings."
    },
    {
      icon: Layers,
      title: "Cross-Deal Exposure Heatmap",
      text: "Aggregating cumulative financial liabilities, parent company guarantees, and cross-default caps for every party across the entire Data Room."
    },
    {
      icon: ShieldCheck,
      title: "Continuous Screening & Registry Snapshots",
      text: "Enriching company profiles with real-time sanctions screening, insolvency status, litigation history, and corporate registry verification."
    },
    {
      icon: CheckCircle2,
      title: "Direct Source Provenance & Audit Dossiers",
      text: "Every extracted relationship, liability, or affiliation flag is linked directly to the primary clause in the original contract for instant legal verification."
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
              Connected Asset Intelligence
            </p>
            <h2 className="text-h1 !text-white mb-6 text-start">
              {t("solutions.counterparties.helps.title", "How Steloom Uncovers Related Party Networks")}
            </h2>
            <p className="text-body !text-[#D6D0C7] text-start leading-relaxed">
              {t("solutions.counterparties.helps.intro", "The platform establishes a unified relational layer across your agreement repository. Every entity is mapped into a dynamic registry dossier with verifiable evidence from primary sources.")}
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
    <section className="relative py-24 lg:py-32 border-t border-[var(--border-color)] bg-[var(--bg-base)]">
      <div
        className="mx-auto w-full px-6 lg:px-8 text-center"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <motion.div 
          className="mx-auto flex flex-col items-center text-center" 
          style={{ maxWidth: 760 }}
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
        >
          <div className="h-px w-16 bg-[#D6D0C7]" aria-hidden="true" />

          <p className="eyebrow mt-8 text-start text-[var(--accent-primary)]">
            Counterparty Risk Automation
          </p>

          <h2 className="mt-4 text-h1 whitespace-pre-line text-[var(--text-primary)]">
            {t("solutions.counterparties.cta.title", "Eliminate Blind Spots in Corporate Intelligence")}
          </h2>

          <p className="mt-6 text-body text-[var(--text-secondary)] leading-relaxed max-w-2xl">
            Transform raw legal documentation into a verifiable counterparty network. Empower your deal teams to identify hidden liabilities early, verify ownership structures, and safeguard transaction value.
          </p>

          <div className="mt-10">
            <button onClick={onDemo} className="cta-primary">
              {t("solutions.counterparties.cta.buttonLabel", "Request a demonstration")}
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
console.log('✅ CounterpartiesPage.tsx: Переписан редактором высокого уровня!');

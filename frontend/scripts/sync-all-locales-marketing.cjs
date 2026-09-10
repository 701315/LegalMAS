const fs = require('fs');
const path = require('path');

const LOCALES_DIR = path.join(__dirname, '../public/locales');
const LANGUAGES = ['en', 'ru', 'ar', 'tr'];
const SOLUTIONS_DIR = path.join(__dirname, '../src/marketing/pages/solutions');

console.log('\n===============================================================');
console.log('🌐 СИНХРОНИЗАЦИЯ ВСЕХ 4 СЛОВАРЕЙ (EN, RU, AR, TR)');
console.log('===============================================================\n');

// Новые эталонные структуры ключей (на базе английского)
const counterpartiesData = {
  hero: {
    eyebrow: "Asset Intelligence & Counterparty Review",
    title: "Counterparty & Related Party Intelligence",
    p1: "In complex M&A, cross-border restructuring, and corporate financing, undisclosed affiliations create severe legal and financial liabilities. Steloom automatically extracts, reconciles, and maps every corporate entity, officer, and related party buried across your deal room.",
    p2: "Legal and deal teams immediately see where each party appears, their exact contractual role, nominee involvement, and cumulative risk exposure across the entire transaction portfolio.",
    buttonLabel: "Request a demonstration"
  },
  risks: {
    eyebrow: "Operational Risks & Blind Spots",
    title: "Party Identification & Compliance Friction",
    i1: {
      title: "Hidden Affiliation & UBO Chains",
      text: "Complex holding structures, nominee shareholders, and off-balance-sheet vehicles hidden inside schedules and side letters remain invisible during standard manual sampling."
    },
    i2: {
      title: "Dynamic Sanctions & PEP Exposure",
      text: "Manually cross-referencing hundreds of counterparties, directors, and signers against shifting international sanction lists and PEP databases creates critical compliance bottlenecks."
    },
    i3: {
      title: "Unmapped Portfolio Exposure",
      text: "Cross-guarantees, parent indemnity clauses, and pending litigation liabilities are fragmented across hundreds of agreements without a centralized exposure ledger."
    }
  },
  helps: {
    eyebrow: "Connected Asset Intelligence",
    title: "How Steloom Uncovers Related Party Networks",
    intro: "The platform establishes a unified relational layer across your agreement repository. Every entity is mapped into a dynamic registry dossier with verifiable evidence from primary sources.",
    cap1: {
      title: "Full-Spectrum Entity & UBO Extraction",
      text: "Automatic recognition of legal names, tax IDs, beneficial owners, and key officers across foreign-language contracts, corporate charters, and court filings."
    },
    cap2: {
      title: "Cross-Deal Exposure Heatmap",
      text: "Aggregating cumulative financial liabilities, parent company guarantees, and cross-default caps for every party across the entire Data Room."
    },
    cap3: {
      title: "Continuous Screening & Registry Snapshots",
      text: "Enriching company profiles with real-time sanctions screening, insolvency status, litigation history, and corporate registry verification."
    },
    cap4: {
      title: "Direct Source Provenance & Audit Dossiers",
      text: "Every extracted relationship, liability, or affiliation flag is linked directly to the primary clause in the original contract for instant legal verification."
    }
  },
  cta: {
    eyebrow: "Institutional Risk & Compliance Infrastructure",
    title: "Bring Institutional Precision to Entity & UBO Verification",
    description: "Legacy manual sampling leaves M&A deal teams and compliance officers exposed to hidden liabilities, circular affiliations, and unmapped portfolio exposure. Steloom replaces guesswork with a unified entity intelligence layer—extracting beneficial ownership networks, automating sanctions screening, and quantifying cross-contract risk directly from primary source documentation.",
    buttonLabel: "Request a demonstration"
  }
};

const realEstateData = {
  hero: {
    eyebrow: "Asset Intelligence & Title Verification",
    title: "Real Estate & Property Rights Intelligence",
    p1: "In large-scale commercial real estate transactions and asset-heavy M&A deals, undetected title defects and unrecorded encumbrances can critically jeopardize deal value. Steloom automatically extracts addresses, cadastral IDs, land plot specs, and lease terms buried in unstructured Data Rooms.",
    p2: "Every identified property asset is instantly reconciled with primary state registry records (EGRN, DLD, Land Registries) to verify title continuity, identify active mortgages, and surface hidden liabilities before the deal closes.",
    buttonLabel: "Request a demonstration"
  },
  risks: {
    eyebrow: "Property Risk Exposure",
    title: "Asset Verification & Legal Risks",
    i1: {
      title: "Hidden Encumbrances & Easements",
      text: "Pledges, third-party rights, and historical easements buried in annexes or historical title deeds routinely escape manual sampling, exposing the buyer to post-transaction litigation."
    },
    i2: {
      title: "Title & Registry Discrepancies",
      text: "Contractual descriptions frequently contradict current state registry data due to unrecorded zoning changes, illegal subdivisions, or outdated cadastral IDs."
    },
    i3: {
      title: "Manual Verification Bottlenecks",
      text: "Cross-referencing hundreds of contractual assets against fresh state registry extracts consumes hundreds of billable hours and delays deal closing."
    }
  },
  helps: {
    eyebrow: "Unified Property Registry",
    title: "Automate Commercial Real Estate Due Diligence",
    intro: "The platform equips investment and legal teams with an interactive property analysis ledger—matching contractual commitments against live registry data with verifiable source citations.",
    cap1: {
      title: "Automated Cadastral & Asset Extraction",
      text: "Instant extraction of property boundaries, cadastral registration IDs, square footage, and usage designations across foreign or multi-jurisdictional agreements."
    },
    cap2: {
      title: "Real-Time Registry Reconciliation",
      text: "Direct cross-matching of extracted property assets against official registries (EGRN, DLD, Land Registries) to flag active encumbrances, litigation, or arrests."
    },
    cap3: {
      title: "Title Chain & Zoning Continuity Analysis",
      text: "Tracing historical ownership transfers and legal permitted use compliance to safeguard acquisition integrity and post-close development rights."
    },
    cap4: {
      title: "Unified Property Dossier & Source Links",
      text: "Generating an interactive property ledger with direct deep-links to original contract paragraphs and official registry snapshots for seamless legal review."
    }
  },
  cta: {
    eyebrow: "Institutional Property Intelligence",
    title: "Streamline Real Estate Portfolio Due Diligence",
    description: "Transform sprawling real estate documentation into a structured asset ledger. Empower your investment and legal teams to verify title continuity, identify undisclosed encumbrances, and accelerate closing cycles with absolute confidence.",
    buttonLabel: "Request a demonstration"
  }
};

// Функция глубокого применения структуры
function mergeStructure(target, source) {
  for (const key in source) {
    if (typeof source[key] === 'object' && source[key] !== null && !Array.isArray(source[key])) {
      if (!target[key] || typeof target[key] !== 'object') target[key] = {};
      mergeStructure(target[key], source[key]);
    } else {
      if (target[key] === undefined) {
        target[key] = source[key];
      }
    }
  }
}

// 1. Синхронизируем все 4 языковых файла
LANGUAGES.forEach(lang => {
  const file = path.join(LOCALES_DIR, lang, 'marketing.json');
  if (fs.existsSync(file)) {
    const dict = JSON.parse(fs.readFileSync(file, 'utf-8'));
    if (!dict.solutions) dict.solutions = {};

    mergeStructure(dict.solutions, {
      counterparties: counterpartiesData,
      realEstate: realEstateData
    });

    // Оправляем cta.eyebrow для corporateLegal и lawFirms
    if (!dict.solutions.corporateLegal) dict.solutions.corporateLegal = {};
    if (!dict.solutions.corporateLegal.cta) dict.solutions.corporateLegal.cta = {};
    if (!dict.solutions.corporateLegal.cta.eyebrow) dict.solutions.corporateLegal.cta.eyebrow = "Corporate Legal Automation";

    if (!dict.solutions.lawFirms) dict.solutions.lawFirms = {};
    if (!dict.solutions.lawFirms.cta) dict.solutions.lawFirms.cta = {};
    if (!dict.solutions.lawFirms.cta.eyebrow) dict.solutions.lawFirms.cta.eyebrow = "Law Firm Practice Automation";

    fs.writeFileSync(file, JSON.stringify(dict, null, 2), 'utf-8');
    console.log(`✅ ${lang}/marketing.json: Структура полностью синхронизирована!`);
  } else {
    console.log(`⚠️ Файл не найден: ${file}`);
  }
});

// 2. Обновляем CounterpartiesPage.tsx для 100% i18n
const cpPath = path.join(SOLUTIONS_DIR, 'CounterpartiesPage.tsx');
if (fs.existsSync(cpPath)) {
  const cpCode = `// src/marketing/pages/solutions/CounterpartiesPage.tsx

import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useTranslation } from "react-i18next";
import { ArrowRight, Network, ShieldAlert, FileSearch, CheckCircle2, Layers, Cpu, ShieldCheck } from "lucide-react";

import SiteHeader from "../../components/shared/SiteHeader";
import MarketingPageFooter from "../../components/shared/MarketingPageFooter";
import PathCrumb from "../../components/platform/primitives/PathCrumb";
import { useContactModal } from "../../context/ContactModalContext";

const ease: [number, number, number, number] = [0.16, 1, 0.3, 1];

const CounterpartiesPage: React.FC = () => {
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
            leaf={t("solutions.counterparties.hero.eyebrow")}
          />
        </motion.div>

        <div className="mt-10 grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-16 items-center">
          <div className="lg:col-span-5">
            <motion.h1
              className="text-display max-w-xl whitespace-pre-line text-start"
              initial={prefersReduced ? undefined : { opacity: 0, y: 15 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.1, ease }}
            >
              {t("solutions.counterparties.hero.title")}
            </motion.h1>

            <motion.div
              className="mt-8 space-y-6 text-body leading-relaxed text-[var(--text-secondary)] text-start max-w-xl"
              initial={prefersReduced ? undefined : { opacity: 0, y: 15 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.2, ease }}
            >
              <p>{t("solutions.counterparties.hero.p1")}</p>
              <p>{t("solutions.counterparties.hero.p2")}</p>
            </motion.div>
          </div>

          <motion.div
            initial={prefersReduced ? undefined : { opacity: 0, scale: 0.98 }}
            animate={prefersReduced ? undefined : { opacity: 1, scale: 1 }}
            transition={{ duration: 0.8, delay: 0.2, ease }}
            className="lg:col-span-7 relative overflow-hidden border border-[var(--border-color)]/50 bg-[var(--bg-surface)] shadow-md"
          >
            <img
              src="/counterpaties picture.png"
              alt="Counterparty Verification Network"
              className="block w-full h-auto object-cover"
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
      id: "affiliation",
      icon: Network,
      title: t("solutions.counterparties.risks.i1.title"),
      text: t("solutions.counterparties.risks.i1.text")
    },
    {
      id: "sanctions",
      icon: ShieldAlert,
      title: t("solutions.counterparties.risks.i2.title"),
      text: t("solutions.counterparties.risks.i2.text")
    },
    {
      id: "fragmentation",
      icon: FileSearch,
      title: t("solutions.counterparties.risks.i3.title"),
      text: t("solutions.counterparties.risks.i3.text")
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
          <p className="text-eyebrow mb-4 text-start">{t("solutions.counterparties.risks.eyebrow")}</p>
          <h2 className="text-h1 text-start text-[var(--text-primary)]">
            {t("solutions.counterparties.risks.title")}
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
      title: t("solutions.counterparties.helps.cap1.title"),
      text: t("solutions.counterparties.helps.cap1.text")
    },
    {
      icon: Layers,
      title: t("solutions.counterparties.helps.cap2.title"),
      text: t("solutions.counterparties.helps.cap2.text")
    },
    {
      icon: ShieldCheck,
      title: t("solutions.counterparties.helps.cap3.title"),
      text: t("solutions.counterparties.helps.cap3.text")
    },
    {
      icon: CheckCircle2,
      title: t("solutions.counterparties.helps.cap4.title"),
      text: t("solutions.counterparties.helps.cap4.text")
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
              {t("solutions.counterparties.helps.eyebrow")}
            </p>
            <h2 className="text-h1 !text-white mb-6 text-start">
              {t("solutions.counterparties.helps.title")}
            </h2>
            <p className="text-body !text-[#D6D0C7] text-start leading-relaxed">
              {t("solutions.counterparties.helps.intro")}
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
            {t("solutions.counterparties.cta.eyebrow")}
          </p>

          <h2 className="mt-4 text-h1 whitespace-pre-line text-[var(--text-primary)] leading-tight">
            {t("solutions.counterparties.cta.title")}
          </h2>

          <p className="mt-6 text-body text-[var(--text-secondary)] leading-relaxed max-w-2xl text-center">
            {t("solutions.counterparties.cta.description")}
          </p>

          <div className="mt-10">
            <button onClick={onDemo} className="cta-primary">
              {t("solutions.counterparties.cta.buttonLabel")}
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

  fs.writeFileSync(cpPath, cpCode, 'utf-8');
  console.log('✅ CounterpartiesPage.tsx: Переведён на ключи i18n!');
}

// 3. Обновляем RealEstatePage.tsx для 100% i18n
const rePath = path.join(SOLUTIONS_DIR, 'RealEstatePage.tsx');
if (fs.existsSync(rePath)) {
  const reCode = `// src/marketing/pages/solutions/RealEstatePage.tsx

import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useTranslation } from "react-i18next";
import { ArrowRight, ShieldAlert, FileSearch, CheckCircle2, Layers, Cpu, ShieldCheck, MapPin } from "lucide-react";

import SiteHeader from "../../components/shared/SiteHeader";
import MarketingPageFooter from "../../components/shared/MarketingPageFooter";
import PathCrumb from "../../components/platform/primitives/PathCrumb";
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
`;

  fs.writeFileSync(rePath, reCode, 'utf-8');
  console.log('✅ RealEstatePage.tsx: Переведён на ключи i18n!');
}

console.log('\n===============================================================\n');

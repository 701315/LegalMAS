const fs = require('fs');
const path = require('path');

const pagePath = path.join(__dirname, '../src/marketing/pages/solutions/CounterpartiesPage.tsx');

const fullCode = `// src/marketing/pages/solutions/CounterpartiesPage.tsx

import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useTranslation } from "react-i18next";
import { ArrowRight, Network, ShieldAlert, FileSearch, CheckCircle2, Database } from "lucide-react";

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
        <HeroSection onDemo={openContactModal} />
        <RisksSection />
        <HowItHelpsSection />
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
function HeroSection({ onDemo }: { onDemo: () => void }) {
  const prefersReduced = useReducedMotion() ?? false;
  const { t, i18n } = useTranslation("marketing");
  const isRTL = i18n.language === "ar";

  return (
    <section data-header-theme="light" className="bg-[var(--bg-base)] border-b border-[var(--border-color)]/50">
      <div
        className="mx-auto w-full px-6 pb-24 pt-20 lg:px-8 lg:pb-32 lg:pt-28"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <motion.div
          initial={prefersReduced ? undefined : { opacity: 0, y: 15 }}
          animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease }}
        >
          <PathCrumb
            root="Solutions"
            leaf={t("solutions.counterparties.hero.eyebrow", "Advanced Analysis")}
          />
        </motion.div>

        <div className="mt-12 grid grid-cols-1 lg:grid-cols-[1.2fr_1fr] gap-12 lg:gap-20 items-center">
          <div>
            <motion.h1
              className="text-display max-w-2xl whitespace-pre-line text-start"
              initial={prefersReduced ? undefined : { opacity: 0, y: 15 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.1, ease }}
            >
              {t("solutions.counterparties.hero.title", "Counterparty and Related Party Verification")}
            </motion.h1>

            <motion.div
              className="mt-8 space-y-6 text-body leading-relaxed text-[var(--text-secondary)] text-start max-w-xl"
              initial={prefersReduced ? undefined : { opacity: 0, y: 15 }}
              animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.2, ease }}
            >
              <p>
                {t("solutions.counterparties.hero.p1", "Steloom automatically identifies counterparties in the text, tables, and appendices of deal documents, forms a unified registry, and enriches company profiles via external and internal sources.")}
              </p>
              <p>
                {t("solutions.counterparties.hero.p2", "The team sees in which contracts and in what role the counterparty appears, and can assess the aggregate exposure in the context of the entire deal.")}
              </p>
            </motion.div>

            <motion.div
              className="mt-10 text-start"
              initial={prefersReduced ? undefined : { opacity: 0 }}
              animate={prefersReduced ? undefined : { opacity: 1 }}
              transition={{ duration: 0.6, delay: 0.3, ease }}
            >
              <button onClick={onDemo} className="cta-primary">
                {t("solutions.counterparties.hero.buttonLabel", "Request a demonstration")}
                <ArrowRight
                  className="h-3.5 w-3.5 ml-2"
                  style={{ transform: isRTL ? "rotate(180deg)" : "none", transition: "transform 0.2s ease" }}
                />
              </button>
            </motion.div>
          </div>

          <motion.div
            initial={prefersReduced ? undefined : { opacity: 0, scale: 0.98 }}
            animate={prefersReduced ? undefined : { opacity: 1, scale: 1 }}
            transition={{ duration: 0.8, delay: 0.2, ease }}
            className="hidden lg:block relative overflow-hidden bg-[var(--bg-surface)] border border-[var(--border-color)]/50 aspect-square"
          >
             <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-[#F5EBE7]/50 via-transparent to-transparent opacity-70" />
             <div className="absolute inset-0 flex items-center justify-center">
                <Network className="w-40 h-40 text-[var(--accent-primary)] opacity-20" strokeWidth={1} />
             </div>
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
      title: t("solutions.counterparties.risks.i1.title", "Hidden Affiliation"),
      text: t("solutions.counterparties.risks.i1.text", "The difficulty of manually identifying ownership chains and ultimate beneficial owners (UBO) in large Data Rooms.")
    },
    {
      id: "sanctions",
      icon: ShieldAlert,
      title: t("solutions.counterparties.risks.i2.title", "Sanctions Risks"),
      text: t("solutions.counterparties.risks.i2.text", "The need to check hundreds of individuals against international lists that are constantly updated.")
    },
    {
      id: "fragmentation",
      icon: FileSearch,
      title: t("solutions.counterparties.risks.i3.title", "Data Fragmentation"),
      text: t("solutions.counterparties.risks.i3.text", "Information about counterparties' financial indicators and litigation is often detached from the texts of the contracts themselves.")
    }
  ];

  return (
    <section className="bg-[var(--bg-base)] py-24 lg:py-32">
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
          <h2 className="text-h1 text-start text-[var(--text-primary)]">
            {t("solutions.counterparties.risks.title", "Party Identification Risks")}
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
function HowItHelpsSection() {
  const { t } = useTranslation("marketing");

  const features = [
    t("solutions.counterparties.helps.b1", "Automatic identification of entities across the entire document package"),
    t("solutions.counterparties.helps.b2", "Risk aggregation: sanctions, bankruptcy, litigation, ownership"),
    t("solutions.counterparties.helps.b3", "Counterparty card with financial and legal context"),
    t("solutions.counterparties.helps.b4", "Prioritization of critical counterparties for escalation")
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
            <h2 className="text-h1 !text-white mb-6 text-start">
              {t("solutions.counterparties.helps.title", "How Steloom Solves These Tasks")}
            </h2>
            <p className="text-body !text-[#D6D0C7] text-start leading-relaxed">
              {t("solutions.counterparties.helps.intro", "The platform forms a connected analysis layer: each identified counterparty receives a Registry Snapshot with data from global and local registries.")}
            </p>
          </motion.div>

          <div className="lg:col-span-7">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              {features.map((feature, index) => (
                <motion.div
                  key={index}
                  initial={{ opacity: 0, y: 15 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: "-50px" }}
                  transition={{ delay: index * 0.1, duration: 0.5 }}
                  className="p-6 border border-white/10 bg-white/5 rounded-none backdrop-blur-sm flex flex-col items-start text-start"
                >
                  <CheckCircle2 className="h-6 w-6 text-[var(--accent-primary)] mb-4 flex-shrink-0" />
                  <h3 className="text-body font-medium !text-white leading-snug">
                    {feature}
                  </h3>
                </motion.div>
              ))}
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
          style={{ maxWidth: 720 }}
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
        >
          <div className="h-px w-16 bg-[#D6D0C7]" aria-hidden="true" />

          <h2 className="mt-10 text-h1 whitespace-pre-line text-[var(--text-primary)]">
            {t("solutions.counterparties.cta.title", "Automate KYC and Party Verification")}
          </h2>

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

fs.writeFileSync(pagePath, fullCode, 'utf-8');
console.log('✅ CounterpartiesPage.tsx: Страница полностью переписана по стандартам премиум-продакшена!');

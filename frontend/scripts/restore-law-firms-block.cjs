const fs = require('fs');
const path = require('path');

const lawPath = path.join(__dirname, '../src/marketing/pages/solutions/LawFirmsPage.tsx');

if (fs.existsSync(lawPath)) {
  const fullCode = `// src/marketing/pages/solutions/LawFirmsPage.tsx

import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useTranslation } from "react-i18next";
import {
  ArrowRight,
  Scale,
  Zap,
  ShieldCheck,
  FileCheck2,
  Building2,
  Search,
  FileText,
  Layers,
  CheckCircle2,
  Briefcase,
  ExternalLink,
} from "lucide-react";

import SiteHeader from "../../../components/shared/SiteHeader";
import MarketingPageFooter from "../../../components/shared/MarketingPageFooter";
import PathCrumb from "../../../components/platform/primitives/PathCrumb";
import ContactModal from "../../../components/home/ContactModal";

const ease: [number, number, number, number] = [0.16, 1, 0.3, 1];

const ICON_MAP: Record<string, React.ElementType> = {
  Zap,
  ShieldCheck,
  FileCheck2,
  Building2,
  Search,
  FileText,
  Layers,
  Briefcase,
  Scale,
};

const LawFirmsPage: React.FC = () => {
  const [contactModalOpen, setContactModalOpen] = React.useState(false);

  const openContactModal = () => setContactModalOpen(true);
  const closeContactModal = () => setContactModalOpen(false);

  return (
    <div className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)] selection:bg-[var(--accent-primary)] selection:text-white">
      <SiteHeader />

      <main style={{ paddingTop: 68 }}>
        <HeroSection onDemo={openContactModal} />
        <HowSteloomHelpsSection />
        <ScenariosSection />
        <CapabilitiesSection />
        <CTASection onDemo={openContactModal} />
      </main>

      <MarketingPageFooter />

      <ContactModal isOpen={contactModalOpen} onClose={closeContactModal} />
    </div>
  );
};

export default LawFirmsPage;

/* ─────────────────────────────────────────────────────────────────────────────
   1. HERO SECTION
───────────────────────────────────────────────────────────────────────────── */
function HeroSection({ onDemo }: { onDemo: () => void }) {
  const prefersReduced = useReducedMotion() ?? false;
  const { t, i18n } = useTranslation("marketing");
  const isRTL = i18n.language === "ar";

  return (
    <section data-header-theme="light" className="bg-[var(--bg-base)]">
      <div
        className="mx-auto w-full px-6 pb-24 pt-20 lg:px-8 lg:pb-32 lg:pt-28"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <PathCrumb
          root={t("solutions.lawFirms.hero.eyebrowRoot")}
          leaf={t("solutions.lawFirms.hero.eyebrowLeaf")}
        />

        <div className="mt-12 lg:w-1/2">
          <p className="text-body text-start">
            {t("solutions.lawFirms.hero.intro")}
          </p>
        </div>

        <motion.div
          initial={prefersReduced ? undefined : { opacity: 0, y: 20 }}
          animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.3, ease }}
          className="mt-16 relative overflow-hidden rounded-none border border-[var(--border-color)] bg-white shadow-sm"
        >
          <img
            src="/lo-1.jpg"
            alt="Law Firm Workspace"
            className="block h-auto w-full object-cover"
          />
        </motion.div>

        <h1 className="mt-20 lg:mt-32 text-display max-w-6xl whitespace-pre-line text-start">
          {t("solutions.lawFirms.hero.titlePart1")}
          <br />
          <span className="italic font-normal text-[var(--accent-primary)]">
            {t("solutions.lawFirms.hero.titlePart2")}
          </span>
        </h1>

        <div className="mt-10">
          <button onClick={onDemo} className="cta-primary">
            {t("solutions.lawFirms.hero.buttonLabel")}
            <ArrowRight
              className="h-3.5 w-3.5 ml-2"
              style={{ transform: isRTL ? "rotate(180deg)" : "none", transition: "transform 0.2s ease" }}
            />
          </button>
        </div>
      </div>
    </section>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   2. HOW STELOOM HELPS (Speed and Coverage, Quality, Traceability)
───────────────────────────────────────────────────────────────────────────── */
function HowSteloomHelpsSection() {
  const { t } = useTranslation("marketing");

  const blocksRaw = t("solutions.lawFirms.briefBlocks", { returnObjects: true });
  const blocks = Array.isArray(blocksRaw) ? blocksRaw : [];

  return (
    <section className="bg-[var(--bg-base)] border-t border-[var(--border-color)]/50 py-16 lg:py-24">
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 md:gap-12 divide-y md:divide-y-0 md:divide-x divide-[var(--border-color)]">
          {blocks.map((block, index) => {
            const IconComponent = ICON_MAP[block.icon] || Scale;
            return (
              <div
                key={block.id || index}
                className="pt-8 md:pt-0 md:px-8 lg:px-12 flex flex-col items-start text-start first:pl-0 first:pt-0 last:pr-0"
              >
                <div className="h-40 w-full bg-[var(--bg-surface)] rounded-none mb-8 flex items-center justify-center border border-[var(--border-color)]">
                  <IconComponent className="h-10 w-10 text-[var(--accent-primary)] opacity-40" />
                </div>
                <h2 className="text-h2 font-serif italic text-[var(--text-primary)] mb-4 leading-tight">
                  {block.title}
                </h2>
                <p className="text-body leading-relaxed text-[var(--text-secondary)]">
                  {block.text}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   3. APPLICATION SCENARIOS (Dark Theme with White Titles)
───────────────────────────────────────────────────────────────────────────── */
function ScenariosSection() {
  const { t } = useTranslation("marketing");

  const scenariosRaw = t("solutions.lawFirms.scenarios.items", { returnObjects: true });
  const scenarios = Array.isArray(scenariosRaw) ? scenariosRaw : [];

  return (
    <section data-theme="dark" data-header-theme="dark" className="bg-[#1A1917] py-24 lg:py-32 text-white border-t border-white/10">
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <p className="eyebrow !text-[var(--accent-primary)] brightness-110 mb-4 text-start">
          {t("solutions.lawFirms.scenarios.eyebrow")}
        </p>
        <h2 className="text-h1 !text-white mb-16 text-start">
          {t("solutions.lawFirms.scenarios.title")}
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 lg:gap-12">
          {scenarios.map((item, index) => (
            <div
              key={item.id || index}
              className="p-8 lg:p-10 border border-white/10 bg-white/5 rounded-none backdrop-blur-sm"
            >
              <h3 className="text-h3 font-serif italic !text-white mb-4 text-start">
                {item.title}
              </h3>
              <p className="text-body !text-[#D6D0C7] text-start leading-relaxed">
                {item.text}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   4. CAPABILITIES SECTION
───────────────────────────────────────────────────────────────────────────── */
function CapabilitiesSection() {
  const { t } = useTranslation("marketing");

  const itemsRaw = t("solutions.lawFirms.capabilities.items", { returnObjects: true });
  const capabilities = Array.isArray(itemsRaw) ? itemsRaw : [];

  return (
    <section className="bg-[var(--bg-base)] border-t border-[var(--border-color)]/50 py-24 lg:py-32">
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="max-w-2xl mb-16">
          <p className="text-eyebrow mb-4 text-start">
            {t("solutions.lawFirms.capabilities.eyebrow")}
          </p>
          <h2 className="text-h1 text-[var(--text-primary)] mb-16 max-w-none text-start">
            {t("solutions.lawFirms.capabilities.title")}
          </h2>
        </div>

        <div className="mt-16">
          {capabilities.map((item, index) => {
            const IconComponent = ICON_MAP[item.icon] || Briefcase;
            const bulletsRaw = t(\`solutions.lawFirms.capabilities.items.\${index}.bullets\`, { returnObjects: true });
            const bullets = Array.isArray(bulletsRaw) ? bulletsRaw : [];

            return (
              <div key={item.id || index} className="grid grid-cols-1 md:grid-cols-12 gap-8 py-10 border-t border-[var(--border-color)]/60">
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
                      <li key={\`\${item.id}-bullet-\${bIndex}\`} className="flex items-start gap-3 text-start">
                        <CheckCircle2 className="h-4 w-4 text-[var(--accent-primary)] opacity-50 flex-shrink-0 mt-1" />
                        <span className="text-body-sm">
                          {bullet}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   5. CTA SECTION
───────────────────────────────────────────────────────────────────────────── */
function CTASection({ onDemo }: { onDemo: () => void }) {
  const { t, i18n } = useTranslation("marketing");
  const isRTL = i18n.language === "ar";

  const paragraphsRaw = t("solutions.lawFirms.cta.paragraphs", { returnObjects: true });
  const paragraphs = Array.isArray(paragraphsRaw) ? paragraphsRaw : [];

  return (
    <section className="relative py-24 lg:py-32 border-t border-[var(--border-color)] bg-[var(--bg-base)]">
      <div
        className="mx-auto w-full px-6 lg:px-8 text-center"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="mx-auto flex flex-col items-center text-center" style={{ maxWidth: 720 }}>
          <h2 className="mt-10 text-h1 whitespace-pre-line">
            {t("solutions.lawFirms.cta.titlePart1")}
            <br />
            <span className="italic font-normal text-[var(--accent-primary)]">
              {t("solutions.lawFirms.cta.titlePart2")}
            </span>
          </h2>

          <div className="mt-7 space-y-5 text-body text-[var(--text-secondary)]">
            {paragraphs.map((p, i) => (
              <p key={i}>{p}</p>
            ))}
          </div>

          <div className="mt-10">
            <button onClick={onDemo} className="cta-primary">
              {t("solutions.lawFirms.cta.buttonLabel")}
              <ArrowRight
                className="h-3.5 w-3.5 ml-2"
                style={{ transform: isRTL ? "rotate(180deg)" : "none", transition: "transform 0.2s ease" }}
              />
            </button>
          </div>

          <p className="mt-8 text-eyebrow text-[var(--text-muted)]">
            {t("solutions.lawFirms.cta.eyebrow")}
          </p>
        </div>
      </div>
    </section>
  );
}
`;

  fs.writeFileSync(lawPath, fullCode, 'utf-8');
  console.log('✅ LawFirmsPage.tsx: Файл полностью восстановлен и обновлён!');
}

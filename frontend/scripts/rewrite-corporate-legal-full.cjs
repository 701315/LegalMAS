const fs = require('fs');
const path = require('path');

const corpPath = path.join(__dirname, '../src/marketing/pages/solutions/CorporateLegalPage.tsx');

const fullCode = `// src/marketing/pages/solutions/CorporateLegalPage.tsx

import React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useTranslation } from "react-i18next";
import { ArrowRight, CheckCircle2, ShieldCheck, Zap, Scale, Layers } from "lucide-react";

import SiteHeader from "../../components/shared/SiteHeader";
import MarketingPageFooter from "../../components/shared/MarketingPageFooter";
import PathCrumb from "../../components/platform/primitives/PathCrumb";
import ContactModal from "../../components/home/ContactModal";
import Reveal, { RevealItem } from "../../components/shared/Reveal";

const ICON_MAP: Record<string, React.ElementType> = {
  Zap,
  ShieldCheck,
  Scale,
  Layers,
};

const CorporateLegalPage: React.FC = () => {
  const [contactModalOpen, setContactModalOpen] = React.useState(false);

  const openContactModal = () => setContactModalOpen(true);
  const closeContactModal = () => setContactModalOpen(false);

  return (
    <div className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)] selection:bg-[var(--accent-primary)] selection:text-white">
      <SiteHeader />

      <main style={{ paddingTop: 68 }}>
        <HeroSection />
        <PressureSection />
        <OutcomesSection />
        <ScenariosSection />
        <CapabilitiesSection />
        <CTASection onDemo={openContactModal} />
      </main>

      <MarketingPageFooter />

      <ContactModal isOpen={contactModalOpen} onClose={closeContactModal} />
    </div>
  );
};

export default CorporateLegalPage;

/* ─────────────────────────────────────────────────────────────────────────────
   1. HERO SECTION
───────────────────────────────────────────────────────────────────────────── */
function HeroSection() {
  const prefersReduced = useReducedMotion() ?? false;
  const { t } = useTranslation("marketing");

  const paragraphsRaw = t("solutions.corporateLegal.hero.paragraphs", { returnObjects: true });
  const paragraphs = Array.isArray(paragraphsRaw) ? paragraphsRaw : [];

  return (
    <section data-header-theme="light" className="bg-[var(--bg-base)]">
      <div
        className="mx-auto w-full px-6 pb-24 pt-20 lg:px-8 lg:pb-32 lg:pt-28"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <RevealItem>
            <PathCrumb
              root={t("solutions.corporateLegal.hero.eyebrowRoot")}
              leaf={t("solutions.corporateLegal.hero.eyebrowLeaf")}
            />
          </RevealItem>

          <div className="mt-12 grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-10 lg:gap-12 items-start">
            <RevealItem>
              <motion.div
                initial={prefersReduced ? undefined : { opacity: 0, y: 20 }}
                animate={prefersReduced ? undefined : { opacity: 1, y: 0 }}
                transition={{ duration: 0.8, delay: 0.2 }}
                className="overflow-hidden rounded-none border border-[var(--border-color)] bg-white shadow-sm"
              >
                <img
                  src="/in-1.jpg"
                  alt="Corporate legal team workspace"
                  className="block w-full h-full min-h-[420px] lg:min-h-[540px] object-cover"
                />
              </motion.div>
            </RevealItem>

            <div className="flex flex-col justify-start">
              {paragraphs.map((p, i) => (
                <RevealItem key={i}>
                  <p className="text-body text-start">
                    {p}
                  </p>
                </RevealItem>
              ))}
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   2. PRESSURE SECTION (3 H2 titles: Business waits..., Varying levels..., Hard to maintain...)
───────────────────────────────────────────────────────────────────────────── */
function PressureSection() {
  const { t } = useTranslation("marketing");

  const itemsRaw = t("solutions.corporateLegal.pressure.items", { returnObjects: true });
  const items = Array.isArray(itemsRaw) ? itemsRaw : [];

  return (
    <section data-header-theme="light" className="bg-[var(--bg-base)] border-t border-[var(--border-color)]/50">
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <div className="max-w-2xl">
            <RevealItem>
              <p className="text-eyebrow mb-4 text-start">
                {t("solutions.corporateLegal.pressure.eyebrow")}
              </p>
            </RevealItem>
          </div>

          <div className="mt-16 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((item) => (
              <RevealItem key={item.id}>
                <div className="flex flex-col h-full">
                  <div className="pt-0 text-start">
                    <h2 className="text-h3 font-serif italic text-[var(--text-primary)] text-start">
                      {item.title}
                    </h2>
                    <p className="mt-3 text-body leading-relaxed text-[var(--text-secondary)] text-start">
                      {item.text}
                    </p>
                  </div>
                </div>
              </RevealItem>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   3. OUTCOMES SECTION (6 H2 titles: Speed for internal..., Unified standard..., Traceable findings...)
───────────────────────────────────────────────────────────────────────────── */
function OutcomesSection() {
  const { t } = useTranslation("marketing");

  const itemsRaw = t("solutions.corporateLegal.outcomes.items", { returnObjects: true });
  const outcomes = Array.isArray(itemsRaw) ? itemsRaw : [];

  return (
    <section data-header-theme="light" className="bg-[var(--bg-base)] border-t border-[var(--border-color)]/50">
      <div
        className="mx-auto w-full px-6 py-24 lg:px-8 lg:py-32"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <Reveal>
          <div className="max-w-2xl">
            <RevealItem>
              <p className="text-eyebrow mb-4 text-start">
                {t("solutions.corporateLegal.outcomes.eyebrow")}
              </p>
            </RevealItem>
          </div>

          <div className="mt-16 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
            {outcomes.slice(0, 3).map((item) => (
              <RevealItem key={item.id}>
                <div className="flex flex-col h-full">
                  <div className="h-48 w-full overflow-hidden border border-[var(--border-color)]/40 bg-[var(--bg-surface)]">
                    <img
                      src={item.image}
                      alt={item.title}
                      className="block h-full w-full object-cover"
                    />
                  </div>
                  <div className="pt-6 text-start">
                    <h2 className="text-h3 font-serif italic text-[var(--text-primary)] text-start">
                      {item.title}
                    </h2>
                    <p className="mt-3 text-body leading-relaxed text-[var(--text-secondary)] text-start">
                      {item.text}
                    </p>
                  </div>
                </div>
              </RevealItem>
            ))}
          </div>

          <div className="mt-24 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
            {outcomes.slice(3).map((item) => (
              <RevealItem key={item.id}>
                <div className="flex flex-col h-full">
                  <div className="h-48 w-full overflow-hidden border border-[var(--border-color)]/40 bg-[var(--bg-surface)]">
                    <img
                      src={item.image}
                      alt={item.title}
                      className="block h-full w-full object-cover"
                    />
                  </div>
                  <div className="pt-6 text-start">
                    <h2 className="text-h3 font-serif italic text-[var(--text-primary)] text-start">
                      {item.title}
                    </h2>
                    <p className="mt-3 text-body leading-relaxed text-[var(--text-secondary)] text-start">
                      {item.text}
                    </p>
                  </div>
                </div>
              </RevealItem>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   4. SCENARIOS SECTION (Dark Theme)
───────────────────────────────────────────────────────────────────────────── */
function ScenariosSection() {
  const { t } = useTranslation("marketing");

  const scenariosRaw = t("solutions.corporateLegal.scenarios.items", { returnObjects: true });
  const scenarios = Array.isArray(scenariosRaw) ? scenariosRaw : [];

  return (
    <section data-theme="dark" data-header-theme="dark" className="bg-[#1A1917] py-24 lg:py-32 text-white border-t border-white/10">
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <p className="eyebrow !text-[var(--accent-primary)] brightness-110 mb-4 text-start">
          {t("solutions.corporateLegal.scenarios.eyebrow")}
        </p>
        <h2 className="text-h1 !text-white mb-16 text-start">
          {t("solutions.corporateLegal.scenarios.title")}
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
   5. CAPABILITIES SECTION
───────────────────────────────────────────────────────────────────────────── */
function CapabilitiesSection() {
  const { t } = useTranslation("marketing");

  const itemsRaw = t("solutions.corporateLegal.capabilities.items", { returnObjects: true });
  const capabilities = Array.isArray(itemsRaw) ? itemsRaw : [];

  return (
    <section className="bg-[var(--bg-base)] border-t border-[var(--border-color)]/50 py-24 lg:py-32">
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="max-w-2xl mb-16">
          <p className="text-eyebrow mb-4 text-start">
            {t("solutions.corporateLegal.capabilities.eyebrow")}
          </p>
          <h2 className="text-h1 text-[var(--text-primary)] mb-16 max-w-none text-start">
            {t("solutions.corporateLegal.capabilities.title")}
          </h2>
        </div>

        <div className="mt-16">
          {capabilities.map((item, index) => {
            const bulletsRaw = t(\`solutions.corporateLegal.capabilities.items.\${index}.bullets\`, { returnObjects: true });
            const bullets = Array.isArray(bulletsRaw) ? bulletsRaw : [];

            return (
              <div key={item.id || index} className="grid grid-cols-1 md:grid-cols-12 gap-8 py-10 border-t border-[var(--border-color)]/60">
                <div className="md:col-span-4">
                  <h2 className="text-h3 font-serif italic text-[var(--text-primary)] text-start">
                    {item.title}
                  </h2>
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
   6. CTA SECTION
───────────────────────────────────────────────────────────────────────────── */
function CTASection({ onDemo }: { onDemo: () => void }) {
  const { t, i18n } = useTranslation("marketing");
  const isRTL = i18n.language === "ar";

  const paragraphsRaw = t("solutions.corporateLegal.cta.paragraphs", { returnObjects: true });
  const paragraphs = Array.isArray(paragraphsRaw) ? paragraphsRaw : [];

  return (
    <section className="relative py-24 lg:py-32 border-t border-[var(--border-color)] bg-[var(--bg-base)]">
      <div
        className="mx-auto w-full px-6 lg:px-8 text-center"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="mx-auto flex flex-col items-center text-center" style={{ maxWidth: 720 }}>
          <h2 className="mt-10 text-h1 whitespace-pre-line">
            {t("solutions.corporateLegal.cta.titlePart1")}
            <br />
            <span className="italic font-normal text-[var(--accent-primary)]">
              {t("solutions.corporateLegal.cta.titlePart2")}
            </span>
          </h2>

          <div className="mt-7 space-y-5 text-body text-[var(--text-secondary)]">
            {paragraphs.map((p, i) => (
              <p key={i}>{p}</p>
            ))}
          </div>

          <div className="mt-10">
            <button onClick={onDemo} className="cta-primary">
              {t("solutions.corporateLegal.cta.buttonLabel")}
              <ArrowRight
                className="h-3.5 w-3.5 ml-2"
                style={{ transform: isRTL ? "rotate(180deg)" : "none", transition: "transform 0.2s ease" }}
              />
            </button>
          </div>

          <p className="mt-8 text-eyebrow text-[var(--text-muted)]">
            {t("solutions.corporateLegal.cta.eyebrow")}
          </p>
        </div>
      </div>
    </section>
  );
}
`;

fs.writeFileSync(corpPath, fullCode, 'utf-8');
console.log('✅ CorporateLegalPage.tsx: Полностью переписан с корректными импортами и семантическими h2!');

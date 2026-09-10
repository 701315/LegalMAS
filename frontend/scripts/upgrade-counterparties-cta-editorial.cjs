const fs = require('fs');
const path = require('path');

const pagePath = path.join(__dirname, '../src/marketing/pages/solutions/CounterpartiesPage.tsx');

if (fs.existsSync(pagePath)) {
  let content = fs.readFileSync(pagePath, 'utf-8');

  const updatedCTASection = `function CTASection({ onDemo }: { onDemo: () => void }) {
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
            {t("solutions.counterparties.cta.eyebrow", "Institutional Risk & Compliance Infrastructure")}
          </p>

          <h2 className="mt-4 text-h1 whitespace-pre-line text-[var(--text-primary)] leading-tight">
            {t("solutions.counterparties.cta.title", "Bring Institutional Precision to Entity & UBO Verification")}
          </h2>

          <p className="mt-6 text-body text-[var(--text-secondary)] leading-relaxed max-w-2xl text-center">
            {t(
              "solutions.counterparties.cta.description",
              "Legacy manual sampling leaves M&A deal teams and compliance officers exposed to hidden liabilities, circular affiliations, and unmapped portfolio exposure. Steloom replaces guesswork with a unified entity intelligence layer—extracting beneficial ownership networks, automating sanctions screening, and quantifying cross-contract risk directly from primary source documentation."
            )}
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
}`;

  content = content.replace(/function CTASection\([^)]*\)\s*\{[\s\S]*?\n\}/, updatedCTASection);

  fs.writeFileSync(pagePath, content, 'utf-8');
  console.log('✅ CounterpartiesPage.tsx: Финальный CTA-блок полностью переписан на институциональном уровне!');
}

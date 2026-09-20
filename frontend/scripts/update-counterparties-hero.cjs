const fs = require('fs');
const path = require('path');

const pagePath = path.join(__dirname, '../src/marketing/pages/solutions/CounterpartiesPage.tsx');

if (fs.existsSync(pagePath)) {
  let content = fs.readFileSync(pagePath, 'utf-8');

  // 1. Обновляем HeroSection: увеличиваем ширину колонки с картинкой и убираем блок с кнопкой
  const updatedHero = `function HeroSection() {
  const prefersReduced = useReducedMotion() ?? false;
  const { t } = useTranslation("marketing");

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

        <div className="mt-12 grid grid-cols-1 lg:grid-cols-12 gap-12 lg:gap-16 items-center">
          {/* Левая текстовая колонка (5 колонок из 12) */}
          <div className="lg:col-span-5">
            <motion.h1
              className="text-display max-w-xl whitespace-pre-line text-start"
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
          </div>

          {/* Правая колонка с крупным изображением (7 колонок из 12) */}
          <motion.div
            initial={prefersReduced ? undefined : { opacity: 0, scale: 0.98 }}
            animate={prefersReduced ? undefined : { opacity: 1, scale: 1 }}
            transition={{ duration: 0.8, delay: 0.2, ease }}
            className="lg:col-span-7 relative overflow-hidden border border-[var(--border-color)]/50 bg-[var(--bg-surface)] shadow-md"
          >
            <img
              src="/counterpaties picture.png"
              alt="Counterparty Verification"
              className="block w-full h-auto object-cover"
            />
          </motion.div>
        </div>
      </div>
    </section>
  );
}`;

  content = content.replace(/function HeroSection\([^)]*\)\s*\{[\s\S]*?\n\}/, updatedHero);
  content = content.replace(/<HeroSection onDemo=\{openContactModal\} \/>/, '<HeroSection />');

  fs.writeFileSync(pagePath, content, 'utf-8');
  console.log('✅ CounterpartiesPage.tsx: Кнопка удалена из Hero, а изображение сделано крупнее!');
}

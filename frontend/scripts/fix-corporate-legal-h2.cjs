const fs = require('fs');
const path = require('path');

const corpPath = path.join(__dirname, '../src/marketing/pages/solutions/CorporateLegalPage.tsx');

if (fs.existsSync(corpPath)) {
  let content = fs.readFileSync(corpPath, 'utf-8');

  // Переписываем PressureSection с h2
  const updatedPressure = `function PressureSection() {
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
}`;

  // Переписываем OutcomesSection с h2
  const updatedOutcomes = `function OutcomesSection() {
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
}`;

  content = content.replace(/function PressureSection\(\) \{[\s\S]*?\n\}/, updatedPressure);
  content = content.replace(/function OutcomesSection\(\) \{[\s\S]*?\n\}/, updatedOutcomes);

  fs.writeFileSync(corpPath, content, 'utf-8');
  console.log('✅ CorporateLegalPage.tsx: Все 9 заголовков успешно переведены в h2!');
}

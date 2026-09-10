const fs = require('fs');
const path = require('path');

const lawPath = path.join(__dirname, '../src/marketing/pages/solutions/LawFirmsPage.tsx');

if (fs.existsSync(lawPath)) {
  let content = fs.readFileSync(lawPath, 'utf-8');

  // 1. Обновляем HowSteloomHelpsSection (Speed and Coverage, Quality and Reduced Misses, Traceability and Provability) -> h2
  const cleanHelpsSection = `function HowSteloomHelpsSection() {
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
}`;

  content = content.replace(/function HowSteloomHelpsSection\(\) \{[\s\S]*?\n\}/, cleanHelpsSection);

  // 2. Обновляем ScenariosSection (Application Scenarios): Белый заголовок секции и белые заголовки карточек
  const cleanScenariosSection = `function ScenariosSection() {
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
}`;

  content = content.replace(/function ScenariosSection\(\) \{[\s\S]*?\n\}/, cleanScenariosSection);

  fs.writeFileSync(lawPath, content, 'utf-8');
  console.log('✅ LawFirmsPage.tsx: Заголовки карточек переведены в h2, а блок Application Scenarios полностью сделан белым!');
}

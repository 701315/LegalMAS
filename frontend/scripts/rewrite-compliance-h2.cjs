const fs = require('fs');
const path = require('path');

const compPath = path.join(__dirname, '../src/marketing/pages/solutions/CompliancePage.tsx');

if (fs.existsSync(compPath)) {
  let content = fs.readFileSync(compPath, 'utf-8');

  // 1. Переписываем BriefBlocksSection
  const cleanBrief = `function BriefBlocksSection() {
  const { t } = useTranslation("marketing");

  const blocksRaw = t("solutions.compliance.briefBlocks", { returnObjects: true });
  const blocks = Array.isArray(blocksRaw) ? blocksRaw : [];

  return (
    <section className="bg-[var(--bg-base)] border-t border-[var(--border-color)]/50 py-16 lg:py-24">
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 md:gap-12 divide-y md:divide-y-0 md:divide-x divide-[var(--border-color)]">
          {blocks.map((block, index) => {
            const IconComponent = ICON_MAP[block.icon] || ShieldCheck;
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

  content = content.replace(/function BriefBlocksSection\(\) \{[\s\S]*?\n\}/, cleanBrief);

  // 2. В CapabilitiesSection меняем <h3 className="text-h3 italic text-start"> на <h2 ...>
  content = content.replace(
    /<h3 className="text-h3 italic text-start">\s*\{item\.title\}\s*<\/h3>/g,
    `<h2 className="text-h3 font-serif italic text-[var(--text-primary)] text-start">
                  {item.title}
                </h2>`
  );

  fs.writeFileSync(compPath, content, 'utf-8');
  console.log('✅ CompliancePage.tsx: Все 7 заголовков переведены в семантические h2!');
}

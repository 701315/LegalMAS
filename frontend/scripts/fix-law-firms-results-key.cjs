const fs = require('fs');
const path = require('path');

const lawPath = path.join(__dirname, '../src/marketing/pages/solutions/LawFirmsPage.tsx');

if (fs.existsSync(lawPath)) {
  let content = fs.readFileSync(lawPath, 'utf-8');

  const updatedSection = `function HowSteloomHelpsSection() {
  const { t } = useTranslation("marketing");

  const eyebrow = t("solutions.lawFirms.results.eyebrow");
  const blocksRaw = t("solutions.lawFirms.results.items", { returnObjects: true });
  const blocks = Array.isArray(blocksRaw) ? blocksRaw : [];

  return (
    <section className="bg-[var(--bg-base)] border-t border-[var(--border-color)]/50 py-16 lg:py-24">
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        {eyebrow && (
          <p className="eyebrow mb-12 text-start">{eyebrow}</p>
        )}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 md:gap-12 divide-y md:divide-y-0 md:divide-x divide-[var(--border-color)]">
          {blocks.map((block, index) => {
            const IconComponent = ICON_MAP[block.icon] || Scale;
            return (
              <div
                key={block.id || index}
                className="pt-8 md:pt-0 md:px-8 lg:px-12 flex flex-col items-start text-start first:pl-0 first:pt-0 last:pr-0"
              >
                <div className="h-40 w-full bg-[var(--bg-surface)] rounded-none mb-8 flex items-center justify-center border border-[var(--border-color)] overflow-hidden">
                  {block.image ? (
                    <img src={block.image} alt={block.title} className="h-full w-full object-cover opacity-80" />
                  ) : (
                    <IconComponent className="h-10 w-10 text-[var(--accent-primary)] opacity-40" />
                  )}
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

  content = content.replace(/function HowSteloomHelpsSection\(\) \{[\s\S]*?\n\}/, updatedSection);

  fs.writeFileSync(lawPath, content, 'utf-8');
  console.log('✅ LawFirmsPage.tsx: Функция HowSteloomHelpsSection перевязана на верный ключ results.items!');
}

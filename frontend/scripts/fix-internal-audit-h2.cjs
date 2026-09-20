const fs = require('fs');
const path = require('path');

const iaPath = path.join(__dirname, '../src/marketing/pages/solutions/InternalAuditPage.tsx');

if (fs.existsSync(iaPath)) {
  let content = fs.readFileSync(iaPath, 'utf-8');

  const cleanPillars = `function ThreePillarsSection() {
  const { t } = useTranslation("marketing");

  const pillarsRaw = t("solutions.internalAuditPage.pillars", { returnObjects: true });
  const pillars = Array.isArray(pillarsRaw) ? pillarsRaw : [];

  return (
    <section className="bg-[var(--bg-base)] border-t border-[var(--border-color)]/50 py-16 lg:py-24">
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 md:gap-12 divide-y md:divide-y-0 md:divide-x divide-[var(--border-color)]">
          {pillars.map((item, index) => {
            const IconComponent = ICON_MAP[item.icon] || ClipboardCheck;
            return (
              <div
                key={item.id || index}
                className="pt-8 md:pt-0 md:px-8 lg:px-12 flex flex-col items-start text-start first:pl-0 first:pt-0 last:pr-0"
              >
                <div className="h-40 w-full bg-[var(--bg-surface)] rounded-none mb-8 flex items-center justify-center border border-[var(--border-color)]">
                  <IconComponent className="h-10 w-10 text-[var(--accent-primary)] opacity-40" />
                </div>
                <h2 className="text-h2 font-serif italic text-[var(--text-primary)] mb-4 leading-tight">
                  {item.title}
                </h2>
                <p className="text-body leading-relaxed text-[var(--text-secondary)]">
                  {item.text}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}`;

  content = content.replace(/function ThreePillarsSection\(\) \{[\s\S]*?\n\}/, cleanPillars);

  fs.writeFileSync(iaPath, content, 'utf-8');
  console.log('✅ InternalAuditPage.tsx: Заголовки "Unified Checklist", "Audit Trail" и "Period Comparison" переведены в семантические h2!');
}

const fs = require('fs');
const path = require('path');

// 1. MaDueDiligencePage.tsx
const maPath = path.join(__dirname, '../src/marketing/pages/solutions/MaDueDiligencePage.tsx');
if (fs.existsSync(maPath)) {
  let content = fs.readFileSync(maPath, 'utf-8');
  content = content.replace(
    /function ThreeBlocksSection\(\) \{[\s\S]*?\n\}/,
    `function ThreeBlocksSection() {
  const { t } = useTranslation("marketing");

  const blocksRaw = t("solutions.maDueDiligence.threeBlocks", { returnObjects: true });
  const blocks = Array.isArray(blocksRaw) ? blocksRaw : [];

  return (
    <section className="bg-[var(--bg-base)] border-t border-[var(--border-color)]/50">
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-[#E8E4DD]/60">
          {blocks.map((item, index) => {
            const IconComponent = ICON_MAP[item.icon] || Database;
            return (
              <div
                key={item.id}
                className="py-16 md:px-8 lg:px-12 flex flex-col items-start text-start first:pl-0 last:pr-0"
              >
                <Reveal delay={index * 0.1}>
                  <div className="h-48 w-full bg-[var(--bg-surface)] rounded-none mb-8 flex items-center justify-center border border-[var(--border-color)]/40">
                    <IconComponent className="h-12 w-12 text-[var(--accent-primary)] opacity-30" />
                  </div>
                  <h2 className="text-h3 lg:text-h2 font-serif italic text-[var(--text-primary)] mb-3 tracking-tight">
                    {item.title}
                  </h2>
                  <p className="text-body text-[var(--text-secondary)] leading-relaxed">
                    {item.text}
                  </p>
                </Reveal>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}`
  );
  fs.writeFileSync(maPath, content, 'utf-8');
  console.log('✅ MaDueDiligencePage.tsx: ThreeBlocksSection полностью обновлен с крупными h2!');
}

// 2. ContractReviewPage.tsx
const crPath = path.join(__dirname, '../src/marketing/pages/solutions/ContractReviewPage.tsx');
if (fs.existsSync(crPath)) {
  let content = fs.readFileSync(crPath, 'utf-8');
  content = content.replace(
    /function ThreeBlocksSection\(\) \{[\s\S]*?\n\}/,
    `function ThreeBlocksSection() {
  const { t } = useTranslation("marketing");

  const blocksRaw = t("solutions.contractReview.briefBlocks", { returnObjects: true });
  const blocks = Array.isArray(blocksRaw) ? blocksRaw : [];

  return (
    <section className="bg-[var(--bg-base)] border-t border-[var(--border-color)]/50">
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-[#E8E4DD]/60">
          {blocks.map((block, index) => {
            const IconComponent = ICON_MAP[block.icon] || Library;
            return (
              <div
                key={block.id}
                className="py-16 md:px-8 lg:px-12 flex flex-col items-start text-start first:pl-0 last:pr-0"
              >
                <Reveal delay={index * 0.1}>
                  <div className="h-48 w-full bg-[var(--bg-surface)] rounded-none mb-8 flex items-center justify-center border border-[var(--border-color)]/40">
                    <IconComponent className="h-12 w-12 text-[var(--accent-primary)] opacity-30" />
                  </div>
                  <h2 className="text-h3 lg:text-h2 font-serif italic text-[var(--text-primary)] mb-3 tracking-tight">
                    {block.title}
                  </h2>
                  <p className="text-body text-[var(--text-secondary)] leading-relaxed">
                    {block.text}
                  </p>
                </Reveal>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}`
  );
  fs.writeFileSync(crPath, content, 'utf-8');
  console.log('✅ ContractReviewPage.tsx: ThreeBlocksSection полностью обновлен с крупными h2!');
}

// 3. InternalAuditPage.tsx
const iaPath = path.join(__dirname, '../src/marketing/pages/solutions/InternalAuditPage.tsx');
if (fs.existsSync(iaPath)) {
  let content = fs.readFileSync(iaPath, 'utf-8');
  content = content.replace(
    /function ThreePillarsSection\(\) \{[\s\S]*?\n\}/,
    `function ThreePillarsSection() {
  const { t } = useTranslation("marketing");

  const pillarsRaw = t("solutions.internalAuditPage.pillars", { returnObjects: true });
  const pillars = Array.isArray(pillarsRaw) ? pillarsRaw : [];

  return (
    <section className="bg-[var(--bg-base)] border-t border-[var(--border-color)]/50">
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-[#E8E4DD]/60">
          {pillars.map((item, index) => {
            const IconComponent = ICON_MAP[item.icon] || ClipboardCheck;
            return (
              <div
                key={item.id}
                className="py-16 md:px-8 lg:px-12 flex flex-col items-start text-start first:pl-0 last:pr-0"
              >
                <Reveal delay={index * 0.1}>
                  <div className="h-48 w-full bg-[var(--bg-surface)] rounded-none mb-8 flex items-center justify-center border border-[var(--border-color)]/40">
                    <IconComponent className="h-12 w-12 text-[var(--accent-primary)] opacity-30" />
                  </div>
                  <h2 className="text-h3 lg:text-h2 font-serif italic text-[var(--text-primary)] mb-3 tracking-tight">
                    {item.title}
                  </h2>
                  <p className="text-body text-[var(--text-secondary)] leading-relaxed">
                    {item.text}
                  </p>
                </Reveal>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}`
  );
  fs.writeFileSync(iaPath, content, 'utf-8');
  console.log('✅ InternalAuditPage.tsx: ThreePillarsSection полностью обновлен с крупными h2!');
}

console.log('\n===============================================================\n');

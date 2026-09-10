const fs = require('fs');
const path = require('path');

console.log('\n===============================================================');
console.log('🔍 1. ПРОВЕРКА КЛАССОВ ТИПОГРАФИКИ В CSS-ФАЙЛАХ');
console.log('===============================================================\n');

const cssDir = path.join(__dirname, '../src');
function findCssFiles(dir) {
  let results = [];
  const list = fs.readdirSync(dir);
  for (const file of list) {
    const filePath = path.join(dir, file);
    const stat = fs.statSync(filePath);
    if (stat.isDirectory()) {
      results.push(...findCssFiles(filePath));
    } else if (file.endsWith('.css')) {
      results.push(filePath);
    }
  }
  return results;
}

const cssFiles = findCssFiles(cssDir);
cssFiles.forEach(file => {
  const content = fs.readFileSync(file, 'utf-8');
  const rel = path.relative(path.join(__dirname, '..'), file);
  if (content.includes('text-h1') || content.includes('text-h2') || content.includes('text-h3') || content.includes('text-display')) {
    console.log(`📄 Файл стилей: ${rel}`);
    const lines = content.split('\n');
    lines.forEach((line, i) => {
      if (line.includes('text-h1') || line.includes('text-h2') || line.includes('text-h3') || line.includes('text-display')) {
        console.log(`   Строка ${i + 1}: ${line.trim()}`);
      }
    });
    console.log('');
  }
});

console.log('===============================================================');
console.log('🛠️ 2. СИСТЕМНОЕ ИСПРАВЛЕНИЕ СТРУКТУРЫ СЕКЦИИ В MaDueDiligencePage.tsx');
console.log('===============================================================\n');

const pagePath = path.join(__dirname, '../src/marketing/pages/solutions/MaDueDiligencePage.tsx');
if (fs.existsSync(pagePath)) {
  let content = fs.readFileSync(pagePath, 'utf-8');

  // Полностью изолируем <h2> от любых родительских <p> или выравнивающих оберток
  const cleanSection = `function ThreeBlocksSection() {
  const { t } = useTranslation("marketing");

  const blocksRaw = t("solutions.maDueDiligence.threeBlocks", { returnObjects: true });
  const blocks = Array.isArray(blocksRaw) ? blocksRaw : [];

  return (
    <section className="bg-[var(--bg-base)] border-t border-[var(--border-color)]/50 py-16 lg:py-24">
      <div
        className="mx-auto w-full px-6 lg:px-8"
        style={{ maxWidth: "var(--container-max-width)" }}
      >
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 md:gap-12 divide-y md:divide-y-0 md:divide-x divide-[var(--border-color)]">
          {blocks.map((item, index) => {
            const IconComponent = ICON_MAP[item.icon] || Database;
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

  content = content.replace(/function ThreeBlocksSection\(\) \{[\s\S]*?\n\}/, cleanSection);
  fs.writeFileSync(pagePath, content, 'utf-8');
  console.log('✅ MaDueDiligencePage.tsx: ThreeBlocksSection переписана с прямым классом text-h2 без конфликтующих контейнеров!');
}

console.log('\n===============================================================\n');

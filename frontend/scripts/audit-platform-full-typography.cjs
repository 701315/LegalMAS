const fs = require('fs');
const path = require('path');

const PLATFORM_DIR = path.join(__dirname, '../src/marketing/components/platform');

function getAllFiles(dir) {
  let results = [];
  if (fs.existsSync(dir)) {
    const list = fs.readdirSync(dir);
    for (const file of list) {
      const filePath = path.join(dir, file);
      const stat = fs.statSync(filePath);
      if (stat.isDirectory()) {
        results.push(...getAllFiles(filePath));
      } else if (file.endsWith('.tsx') || file.endsWith('.ts')) {
        results.push(filePath);
      }
    }
  }
  return results;
}

const files = getAllFiles(PLATFORM_DIR);

console.log('\n===============================================================');
console.log('🔍 ПОЛНЫЙ АУДИТ ТИПОГРАФИКИ В ПАПКЕ PLATFORM');
console.log('===============================================================\n');

let issuesCount = 0;

files.forEach(file => {
  const content = fs.readFileSync(file, 'utf-8');
  const rel = path.relative(PLATFORM_DIR, file);

  console.log(`📂 Компонент: src/marketing/components/platform/${rel}`);

  // 1. Извлечение Eyebrows / Meta
  const eyebrows = content.match(/className=["']([^"']*(?:text-eyebrow|text-meta|eyebrow)[^"']*)["']/g) || [];
  if (eyebrows.length > 0) {
    console.log(`   🏷️  Eyebrow / Meta:`);
    eyebrows.forEach(e => console.log(`      • ${e}`));
  }

  // 2. Извлечение Заголовков
  const headings = content.match(/<(?:h[1-4]|p|span)[^>]*className=["']([^"']*(?:text-display|text-h1|text-h2|text-h3)[^"']*)["'][^>]*>/gi) || [];
  if (headings.length > 0) {
    console.log(`   👑 Заголовки (Headings):`);
    headings.forEach(h => {
      const cls = h.match(/className=["']([^"']+)["']/)?.[1] || '';
      const tag = h.match(/^<(\w+)/)?.[1] || '';
      console.log(`      • <${tag}> class="${cls}"`);
    });
  }

  // 3. Извлечение Основного Текста (Body)
  const bodyTexts = content.match(/<(?:p|div|span)[^>]*className=["']([^"']*(?:text-body|text-body-sm|section-desc|leading-)[^"']*)["'][^>]*>/gi) || [];
  if (bodyTexts.length > 0) {
    console.log(`   📝 Основной текст (Body):`);
    bodyTexts.forEach(b => {
      const cls = b.match(/className=["']([^"']+)["']/)?.[1] || '';
      const tag = b.match(/^<(\w+)/)?.[1] || '';
      console.log(`      • <${tag}> class="${cls}"`);
    });
  }

  // 4. Поиск хардкода или нестандартных размеров
  const hardcoded = content.match(/text-\[\d+px\]|text-\[\d+(\.\d+)?rem\]|leading-\[\d+(\.\d+)?\]/g) || [];
  if (hardcoded.length > 0) {
    console.log(`   ⚠️ ХАРДКОД/НЕСТАНДАРТНЫЕ РАЗМЕРЫ: ${[...new Set(hardcoded)].join(', ')}`);
    issuesCount++;
  }

  console.log('');
});

console.log('===============================================================');
if (issuesCount === 0) {
  console.log('✨ ВЕЛИКОЛЕПНО! Все компоненты Платформы выстроены по системным токенам.');
} else {
  console.log(`🎯 Найдено компонентов с хардкод-размерами: ${issuesCount}`);
}
console.log('===============================================================\n');

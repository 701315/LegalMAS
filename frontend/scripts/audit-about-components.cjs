const fs = require('fs');
const path = require('path');

const ABOUT_DIR = path.join(__dirname, '../src/marketing/components/about');

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

const files = getAllFiles(ABOUT_DIR);

console.log('\n===============================================================');
console.log('🔍 ПОЛНЫЙ АУДИТ ТИПОГРАФИКИ И СТРУКТУРЫ: РАЗДЕЛ О НАС (ABOUT)');
console.log('===============================================================\n');

if (files.length === 0) {
  console.log('⚠️ Файлы в папке src/marketing/components/about не найдены.');
} else {
  files.forEach(file => {
    const content = fs.readFileSync(file, 'utf-8');
    const rel = path.relative(ABOUT_DIR, file);

    console.log(`📂 Компонент: src/marketing/components/about/${rel}`);

    // 1. Eyebrow / Meta
    const eyebrows = content.match(/className=["']([^"']*(?:text-eyebrow|text-meta|eyebrow)[^"']*)["']/g) || [];
    if (eyebrows.length > 0) {
      console.log(`   🏷️  Eyebrow / Meta:`);
      eyebrows.forEach(e => console.log(`      • ${e}`));
    }

    // 2. Headings
    const headings = content.match(/<(?:h[1-6]|p|span|div)[^>]*className=["']([^"']*(?:text-display|text-h1|text-h2|text-h3|text-h4|text-[2345]xl)[^"']*)["'][^>]*>/gi) || [];
    if (headings.length > 0) {
      console.log(`   👑 Заголовки (Headings):`);
      headings.forEach(h => {
        const cls = h.match(/className=["']([^"']+)["']/)?.[1] || '';
        const tag = h.match(/^<(\w+)/)?.[1] || '';
        console.log(`      • <${tag}> class="${cls}"`);
      });
    }

    // 3. Body text
    const bodyTexts = content.match(/<(?:p|div|span)[^>]*className=["']([^"']*(?:text-body|text-body-sm|text-sm|text-base|text-lg|leading-)[^"']*)["'][^>]*>/gi) || [];
    if (bodyTexts.length > 0) {
      console.log(`   📝 Основной текст (Body):`);
      bodyTexts.forEach(b => {
        const cls = b.match(/className=["']([^"']+)["']/)?.[1] || '';
        const tag = b.match(/^<(\w+)/)?.[1] || '';
        console.log(`      • <${tag}> class="${cls}"`);
      });
    }

    // 4. Hardcoded check
    const hardcoded = content.match(/text-\[\d+px\]|text-\[\d+(\.\d+)?rem\]|leading-\[\d+(\.\d+)?\]/g) || [];
    if (hardcoded.length > 0) {
      console.log(`   ⚠️ ХАРДКОД / НЕСТАНДАРТНЫЕ РАЗМЕРЫ: ${[...new Set(hardcoded)].join(', ')}`);
    }

    console.log('');
  });
}

console.log('===============================================================\n');

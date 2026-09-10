const fs = require('fs');
const path = require('path');

const HOME_DIR = path.join(__dirname, '../src/marketing/components/home');

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

const files = getAllFiles(HOME_DIR);

console.log('\n===============================================================');
console.log('🔍 ПОЛНЫЙ АУДИТ ТИПОГРАФИКИ (ЗАГОЛОВКИ + ТЕКСТ) НА ГЛАВНОЙ');
console.log('===============================================================\n');

let issuesCount = 0;

files.forEach(file => {
  const content = fs.readFileSync(file, 'utf-8');
  const rel = path.relative(HOME_DIR, file);

  console.log(`📂 Секция: src/marketing/components/home/${rel}`);

  // 1. Извлечение Eyebrows (надзаголовков)
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

  // 3. Извлечение Основного Текста (Paragraphs / Body)
  const bodyTexts = content.match(/<(?:p|div|span)[^>]*className=["']([^"']*(?:text-body|text-body-sm|section-desc|leading-)[^"']*)["'][^>]*>/gi) || [];
  if (bodyTexts.length > 0) {
    console.log(`   📝 Основной текст (Body):`);
    bodyTexts.forEach(b => {
      const cls = b.match(/className=["']([^"']+)["']/)?.[1] || '';
      const tag = b.match(/^<(\w+)/)?.[1] || '';
      console.log(`      • <${tag}> class="${cls}"`);
    });
  }

  // 4. Поиск хардкода или отклонений
  const hardcoded = content.match(/text-\[\d+px\]|text-\[\d+(\.\d+)?rem\]|leading-\[\d+(\.\d+)?\]/g) || [];
  if (hardcoded.length > 0) {
    console.log(`   ⚠️ НЕСТАНДАРТНЫЕ/ХАРДКОД-РАЗМЕРЫ: ${[...new Set(hardcoded)].join(', ')}`);
    issuesCount++;
  }

  console.log('');
});

console.log('===============================================================');
if (issuesCount === 0) {
  console.log('✨ ОТЛИЧНО! Все элементы текста и заголовков используют системные токены.');
} else {
  console.log(`🎯 Найдено секций с отдельными хардкод-размерами текста: ${issuesCount}`);
}
console.log('===============================================================\n');

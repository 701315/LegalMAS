const fs = require('fs');
const path = require('path');

const SOLUTIONS_DIR = path.join(__dirname, '../src/marketing/pages/solutions');

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

const files = getAllFiles(SOLUTIONS_DIR);

console.log('\n===============================================================');
console.log('🔍 ПОЛНЫЙ АУДИТ ТИПОГРАФИКИ В РАЗДЕЛЕ SOLUTIONS');
console.log('===============================================================\n');

if (files.length === 0) {
  console.log('⚠️ Файлы в папке src/marketing/pages/solutions не найдены!');
}

let issuesCount = 0;

files.forEach(file => {
  const content = fs.readFileSync(file, 'utf-8');
  const rel = path.relative(SOLUTIONS_DIR, file);

  console.log(`📂 Файл: src/marketing/pages/solutions/${rel}`);

  // 1. Извлечение Eyebrows / Meta
  const eyebrows = content.match(/className=["']([^"']*(?:text-eyebrow|text-meta|eyebrow)[^"']*)["']/g) || [];
  if (eyebrows.length > 0) {
    console.log(`   🏷️  Eyebrow / Meta:`);
    eyebrows.forEach(e => console.log(`      • ${e}`));
  }

  // 2. Извлечение Заголовков (Headings)
  const headings = content.match(/<(?:h[1-4]|p|span|div)[^>]*className=["']([^"']*(?:text-display|text-h1|text-h2|text-h3|text-h4|font-serif)[^"']*)["'][^>]*>/gi) || [];
  if (headings.length > 0) {
    console.log(`   👑 Заголовки (Headings / Serif):`);
    headings.forEach(h => {
      const cls = h.match(/className=["']([^"']+)["']/)?.[1] || '';
      const tag = h.match(/^<(\w+)/)?.[1] || '';
      console.log(`      • <${tag}> class="${cls}"`);
    });
  }

  // 3. Извлечение Основного Текста (Body)
  const bodyTexts = content.match(/<(?:p|div|span|li)[^>]*className=["']([^"']*(?:text-body|text-body-sm|section-desc|leading-relaxed|leading-tight|text-base|text-sm)[^"']*)["'][^>]*>/gi) || [];
  if (bodyTexts.length > 0) {
    console.log(`   📝 Основной текст / Подписи:`);
    // Ограничиваем вывод уникальными или первыми 8 строками, чтобы не захламлять
    const sample = [...new Set(bodyTexts)].slice(0, 8);
    sample.forEach(b => {
      const cls = b.match(/className=["']([^"']+)["']/)?.[1] || '';
      const tag = b.match(/^<(\w+)/)?.[1] || '';
      console.log(`      • <${tag}> class="${cls}"`);
    });
    if (bodyTexts.length > 8) {
      console.log(`      ... и еще ${bodyTexts.length - 8} вхождений`);
    }
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
  console.log('✨ В структуре нет хардкодных px/rem размеров.');
} else {
  console.log(`🎯 Найдено файлов с нестандартными/хардкод размерами: ${issuesCount}`);
}
console.log('===============================================================\n');

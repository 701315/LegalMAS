const fs = require('fs');
const path = require('path');

// Ищем файлы переводов
const localesPath = path.join(__dirname, '../public/locales/en/marketing.json');
let locales = {};
if (fs.existsSync(localesPath)) {
  locales = JSON.parse(fs.readFileSync(localesPath, 'utf-8'));
} else {
  // Проверяем альтернативные пути
  const altPath = path.join(__dirname, '../src/locales/en/marketing.json');
  if (fs.existsSync(altPath)) locales = JSON.parse(fs.readFileSync(altPath, 'utf-8'));
}

const solutionsLocales = locales.solutions || {};

console.log('\n===============================================================');
console.log('🌐 КЛЮЧИ ПЕРЕВОДОВ SOLUTIONS В marketing.json:');
console.log('===============================================================\n');

Object.keys(solutionsLocales).forEach(key => {
  const item = solutionsLocales[key];
  console.log(`📌 Раздел: solutions.${key}`);
  if (item.hero) {
    console.log(`   • hero.title: "${item.hero.title || item.hero.titlePart1 || '—'}"`);
    console.log(`   • hero.eyebrowRoot/Leaf: "${item.hero.eyebrowRoot || ''} / ${item.hero.eyebrowLeaf || ''}"`);
  } else if (item.intro) {
    console.log(`   • intro.title: "${item.intro.title || item.intro.titlePart1 || '—'}"`);
  }
  console.log('');
});

console.log('===============================================================');
console.log('📄 СПИСОК ВСЕХ 9 ФАЙЛОВ SOLUTIONS В src/marketing/pages/solutions:');
console.log('===============================================================\n');

const PAGES_DIR = path.join(__dirname, '../src/marketing/pages/solutions');
const pageFiles = fs.readdirSync(PAGES_DIR).filter(f => f.endsWith('.tsx'));

pageFiles.forEach(file => {
  const content = fs.readFileSync(path.join(PAGES_DIR, file), 'utf-8');
  const headings = content.match(/<h[1-4][^>]*>[\s\S]*?<\/h[1-4]>/gi) || [];
  console.log(`📄 ${file}:`);
  headings.forEach(h => {
    const tag = h.match(/^<(\w+)/)[1];
    const cls = h.match(/className=["']([^"']+)["']/)?.[1] || '';
    const text = h.replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim().substring(0, 60);
    console.log(`   • <${tag} class="${cls}"> -> "${text}"`);
  });
  console.log('');
});

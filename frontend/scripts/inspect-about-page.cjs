const fs = require('fs');
const path = require('path');

const SRC_DIR = path.join(__dirname, '../src');

function findAboutPage(dir) {
  let results = [];
  if (!fs.existsSync(dir)) return results;
  const list = fs.readdirSync(dir);

  for (const item of list) {
    const fullPath = path.join(dir, item);
    const stat = fs.statSync(fullPath);

    if (stat.isDirectory()) {
      results.push(...findAboutPage(fullPath));
    } else if (item.toLowerCase().includes('about')) {
      results.push(fullPath);
    }
  }
  return results;
}

console.log('\n===============================================================');
console.log('🔎 ПОИСК ФАЙЛОВ ABOUT В ПРОЕКТЕ');
console.log('===============================================================\n');

const files = findAboutPage(SRC_DIR);

files.forEach(f => {
  const rel = path.relative(SRC_DIR, f);
  console.log(`📄 Файл: src/${rel}`);
  const content = fs.readFileSync(f, 'utf-8');
  const lines = content.split('\n');
  lines.forEach((line, idx) => {
    if (line.includes('cta') || line.includes('meta') || line.includes('about.')) {
      console.log(`   Строка ${idx + 1}: ${line.trim()}`);
    }
  });
  console.log('');
});

console.log('===============================================================\n');

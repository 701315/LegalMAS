const fs = require('fs');
const path = require('path');

const SRC_DIR = path.join(__dirname, '../src');
const LOCALES_DIR = path.join(__dirname, '../public/locales');

function searchFiles(dir) {
  let results = [];
  if (!fs.existsSync(dir)) return results;
  const list = fs.readdirSync(dir);
  for (const file of list) {
    const filePath = path.join(dir, file);
    const stat = fs.statSync(filePath);
    if (stat.isDirectory()) {
      results.push(...searchFiles(filePath));
    } else if (file.endsWith('.tsx') || file.endsWith('.ts') || file.endsWith('.json')) {
      const content = fs.readFileSync(filePath, 'utf-8');
      if (content.toLowerCase().includes('usually respond') || content.toLowerCase().includes('within one business day')) {
        results.push({ filePath, content });
      }
    }
  }
  return results;
}

console.log('\n===============================================================');
console.log('🔍 ПОИСК ФРАЗЫ "We usually respond within one business day."');
console.log('===============================================================\n');

const matches = searchFiles(SRC_DIR).concat(searchFiles(LOCALES_DIR));

matches.forEach(m => {
  const rel = path.relative(path.join(__dirname, '..'), m.filePath);
  console.log(`📄 Найден файл: ${rel}`);
});

console.log('\n===============================================================\n');

const fs = require('fs');
const path = require('path');

const SRC_DIR = path.join(__dirname, '../src');

function searchRouter(dir) {
  let results = [];
  const list = fs.readdirSync(dir);
  for (const file of list) {
    const filePath = path.join(dir, file);
    const stat = fs.statSync(filePath);
    if (stat.isDirectory()) {
      results.push(...searchRouter(filePath));
    } else if (file.endsWith('.tsx') || file.endsWith('.ts')) {
      const content = fs.readFileSync(filePath, 'utf-8');
      if (content.includes('/solutions/ma-due-diligence') || content.includes('MaDueDiligence')) {
        results.push({ filePath, content });
      }
    }
  }
  return results;
}

console.log('\n===============================================================');
console.log('🔍 ПРОВЕРКА РОУТЕРА ДЛЯ /solutions/ma-due-diligence');
console.log('===============================================================\n');

const matches = searchRouter(SRC_DIR);
matches.forEach(m => {
  const rel = path.relative(path.join(__dirname, '..'), m.filePath);
  console.log(`📄 Найден файл с роутом/импортом: ${rel}`);
});

console.log('\n===============================================================\n');

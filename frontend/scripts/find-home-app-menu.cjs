const fs = require('fs');
const path = require('path');

const HOME_DIR = path.join(__dirname, '../src/marketing/components/home');

function searchFiles(dir) {
  let results = [];
  if (!fs.existsSync(dir)) return results;
  const list = fs.readdirSync(dir);

  for (const item of list) {
    const fullPath = path.join(dir, item);
    const stat = fs.statSync(fullPath);

    if (stat.isDirectory()) {
      results.push(...searchFiles(fullPath));
    } else if (item.endsWith('.tsx') || item.endsWith('.ts')) {
      const content = fs.readFileSync(fullPath, 'utf-8');
      if (
        content.includes('BY DIRECTION') ||
        content.includes('Explore all use cases') ||
        content.includes('byDirection') ||
        content.includes('Checking contracts against standards')
      ) {
        results.push(fullPath);
      }
    }
  }
  return results;
}

console.log('\n===============================================================');
console.log('🔍 ПОИСК КОМПОНЕНТА ГЛАВНОЙ СТРАНИЦЫ С USE CASES');
console.log('===============================================================\n');

const files = searchFiles(HOME_DIR);
files.forEach(f => {
  console.log(`📄 Найден файл: ${path.relative(path.join(__dirname, '..'), f)}`);
});

console.log('\n===============================================================\n');

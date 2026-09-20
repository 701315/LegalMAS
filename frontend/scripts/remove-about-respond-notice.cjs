const fs = require('fs');
const path = require('path');

const SRC_DIR = path.join(__dirname, '../src');
const LOCALES_DIR = path.join(__dirname, '../public/locales');

function cleanInDir(dir) {
  if (!fs.existsSync(dir)) return;
  const list = fs.readdirSync(dir);

  for (const item of list) {
    const fullPath = path.join(dir, item);
    const stat = fs.statSync(fullPath);

    if (stat.isDirectory()) {
      cleanInDir(fullPath);
    } else if (item.endsWith('.tsx') || item.endsWith('.ts') || item.endsWith('.json')) {
      let content = fs.readFileSync(fullPath, 'utf-8');
      const original = content;

      // Заменяем фразу и её вариации
      content = content.replace(/We typically respond and schedule a meeting within one business day\./gi, '');
      content = content.replace(/We usually respond and schedule a meeting within one business day\./gi, '');
      content = content.replace(/typically respond and schedule/gi, '');

      if (content !== original) {
        fs.writeFileSync(fullPath, content, 'utf-8');
        console.log(`✅ ${path.relative(path.join(__dirname, '..'), fullPath)}: Фраза успешно удалена!`);
      }
    }
  }
}

console.log('\n===============================================================');
console.log('🧹 УДАЛЕНИЕ ФРАЗЫ "We typically respond and schedule..."');
console.log('===============================================================\n');

cleanInDir(SRC_DIR);
cleanInDir(LOCALES_DIR);

console.log('\n===============================================================\n');

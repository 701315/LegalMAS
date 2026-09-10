const fs = require('fs');
const path = require('path');

const LOCALES_DIR = path.join(__dirname, '../public/locales');

function cleanJsonInDir(dir) {
  if (!fs.existsSync(dir)) return;
  const list = fs.readdirSync(dir);

  for (const item of list) {
    const fullPath = path.join(dir, item);
    const stat = fs.statSync(fullPath);

    if (stat.isDirectory()) {
      cleanJsonInDir(fullPath);
    } else if (item.endsWith('.json')) {
      let content = fs.readFileSync(fullPath, 'utf-8');
      const original = content;

      // Очищаем ключи, содержащие эту фразу или ее переводы
      content = content.replace(/"eyebrow":\s*"We usually respond within one business day\."/gi, '"eyebrow": ""');
      content = content.replace(/"We usually respond within one business day\."/gi, '""');

      // Универсальная зачистка для всех языков (RU, DE, AR и т.д.)
      content = content.replace(/"eyebrow":\s*"Обычно мы отвечаем в течение одного рабочего дня\."/gi, '"eyebrow": ""');
      content = content.replace(/"eyebrow":\s*"Usually we respond within one business day\."/gi, '"eyebrow": ""');

      if (content !== original) {
        fs.writeFileSync(fullPath, content, 'utf-8');
        console.log(`✅ ${path.relative(LOCALES_DIR, fullPath)}: Фраза успешно удалена!`);
      }
    }
  }
}

console.log('\n===============================================================');
console.log('🧹 УДАЛЕНИЕ ФРАЗЫ "We usually respond within one business day."');
console.log('===============================================================\n');

cleanJsonInDir(LOCALES_DIR);

console.log('\n===============================================================\n');

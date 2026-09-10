const fs = require('fs');
const path = require('path');

const headerPath = path.join(__dirname, '../src/marketing/components/shared/SiteHeader.tsx');

if (fs.existsSync(headerPath)) {
  const content = fs.readFileSync(headerPath, 'utf-8');
  console.log('\n===============================================================');
  console.log('🔎 ПРОВЕРКА РЕНДЕРИНГА ПУНКТОВ МЕНЮ В SiteHeader.tsx');
  console.log('===============================================================\n');

  console.log('1. Импорты в начале файла:');
  console.log(content.split('\n').slice(0, 25).join('\n'));

  console.log('\n2. Рендеринг ссылок мегаменю:');
  const lines = content.split('\n');
  lines.forEach((line, i) => {
    if (line.includes('megaMenu') || line.includes('group') || line.includes('href') || line.includes('location')) {
      if (i > 280 && i < 350) {
        console.log(`[${i + 1}] ${line.trim()}`);
      }
    }
  });

  console.log('\n===============================================================\n');
}

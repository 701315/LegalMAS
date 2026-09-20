const fs = require('fs');
const path = require('path');

const corpPath = path.join(__dirname, '../src/marketing/pages/solutions/CorporateLegalPage.tsx');
const localesPath = path.join(__dirname, '../public/locales/en/marketing.json');

console.log('\n===============================================================');
console.log('🔎 АНАЛИЗ СТРУКТУРЫ CorporateLegalPage.tsx');
console.log('===============================================================\n');

if (fs.existsSync(corpPath)) {
  const content = fs.readFileSync(corpPath, 'utf-8');
  const fns = content.match(/function\s+\w+Section[\s\S]*?(?=\nfunction|\nexport|$)/g) || [];
  fns.forEach(fn => {
    const fnName = fn.match(/function\s+(\w+)/)?.[1] || '';
    console.log(`📌 Функция секции: ${fnName}`);
  });
}

if (fs.existsSync(localesPath)) {
  const json = JSON.parse(fs.readFileSync(localesPath, 'utf-8'));
  const corpLocales = json?.solutions?.corporateLegal || {};
  console.log('\n🌐 Ключи локализации solutions.corporateLegal:');
  console.log(Object.keys(corpLocales));
}

console.log('\n===============================================================\n');

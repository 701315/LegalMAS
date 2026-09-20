const fs = require('fs');
const path = require('path');

const corpPath = path.join(__dirname, '../src/marketing/pages/solutions/CorporateLegalPage.tsx');
const localesPath = path.join(__dirname, '../public/locales/en/marketing.json');

console.log('\n===============================================================');
console.log('🔍 ДЕТАЛЬНЫЙ АУДИТ СТРАНИЦЫ CORPORATE LEGAL');
console.log('===============================================================\n');

// 1. Проверяем локализацию
if (fs.existsSync(localesPath)) {
  const json = JSON.parse(fs.readFileSync(localesPath, 'utf-8'));
  const corpLocales = json?.solutions?.corporateLegal || {};
  console.log('🌐 1. ДАННЫЕ В marketing.json (solutions.corporateLegal):');
  console.log(JSON.stringify(corpLocales, null, 2).substring(0, 2000));
}

console.log('\n---------------------------------------------------------------\n');

// 2. Проверяем все заголовки и теги в файле CorporateLegalPage.tsx
if (fs.existsSync(corpPath)) {
  const content = fs.readFileSync(corpPath, 'utf-8');
  console.log('📄 2. ВСЕ ТЕГИ ЗАГОЛОВКОВ В CorporateLegalPage.tsx:\n');

  const lines = content.split('\n');
  lines.forEach((line, idx) => {
    if (
      line.includes('<h1') ||
      line.includes('<h2') ||
      line.includes('<h3') ||
      line.includes('title') ||
      line.includes('eyebrow')
    ) {
      console.log(`Строка ${idx + 1}: ${line.trim()}`);
    }
  });
}

console.log('\n===============================================================\n');

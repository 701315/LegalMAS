const fs = require('fs');
const path = require('path');

const pagePath = path.join(__dirname, '../src/marketing/pages/solutions/CompliancePage.tsx');

if (fs.existsSync(pagePath)) {
  let content = fs.readFileSync(pagePath, 'utf-8');
  const original = content;

  // Удаляем блок с cta.meta (обычно <p> с text-eyebrow)
  content = content.replace(
    /\s*<p[^>]*>\s*\{t\("solutions\.compliance\.cta\.meta"\)\}\s*<\/p>/g,
    ''
  );

  // На случай, если ключ выводится иначе
  content = content.replace(
    /\s*\{t\("solutions\.compliance\.cta\.meta"\)\}/g,
    ''
  );

  if (content !== original) {
    fs.writeFileSync(pagePath, content, 'utf-8');
    console.log('✅ CompliancePage.tsx: solutions.compliance.cta.meta удалён!');
  } else {
    console.log('⚠️ Точное совпадение не найдено, ищем строки с cta.meta...');
    const lines = content.split('\n');
    lines.forEach((line, i) => {
      if (line.includes('cta.meta') || line.includes('cta.meta')) {
        console.log(`Строка ${i + 1}: ${line.trim()}`);
      }
    });
  }
}

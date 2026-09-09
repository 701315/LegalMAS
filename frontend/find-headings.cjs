const fs = require('fs');
const path = require('path');

const MARKETING_DIR = path.join(__dirname, 'src/marketing');

function getAllFiles(dir) {
  let results = [];
  if (!fs.existsSync(dir)) return results;
  const list = fs.readdirSync(dir);
  for (const file of list) {
    const filePath = path.join(dir, file);
    const stat = fs.statSync(filePath);
    if (stat.isDirectory()) {
      results.push(...getAllFiles(filePath));
    } else if (file.endsWith('.tsx') || file.endsWith('.ts')) {
      results.push(filePath);
    }
  }
  return results;
}

const files = getAllFiles(MARKETING_DIR);
let findingsCount = 0;

console.log('\n🔍 СКАНИРОВАНИЕ ЗАГОЛОВКОВ И ХАРДКОД-ШРИФТОВ В MARKETING...\n');

files.forEach(file => {
  const content = fs.readFileSync(file, 'utf-8');
  const relativeName = path.relative(MARKETING_DIR, file);
  let hasFindings = false;
  let fileLog = `📄 Файл: src/marketing/${relativeName}\n`;

  // 1. Поиск тегов h1, h2, h3, h4
  const headings = content.match(/<h[1-4][^>]*className=["']([^"']+)["'][^>]*>/g) || [];
  headings.forEach(match => {
    const classNameMatch = match.match(/className=["']([^"']+)["']/);
    if (classNameMatch) {
      const classes = classNameMatch[1];
      if (!classes.includes('text-h1') && !classes.includes('text-h2') && !classes.includes('text-h3') && !classes.includes('text-display')) {
        fileLog += `   ⚠️ Заголовок без токена:\n      "${classes}"\n`;
        hasFindings = true;
      }
    }
  });

  // 2. Поиск inline clamp, rem и т.д.
  const hardcodedFonts = content.match(/text-\[clamp[^\]]+\]|text-\[\d+(\.\d+)?(rem|px)\]|leading-\[\d+(\.\d+)?(rem|px|em)?\]|tracking-\[[-\d]+(\.\d+)?(em|px)?\]/g) || [];
  if (hardcodedFonts.length > 0) {
    const uniqueFonts = [...new Set(hardcodedFonts)];
    fileLog += `   ⚠️ Inline-размеры: ${uniqueFonts.join(', ')}\n`;
    hasFindings = true;
  }

  // 3. Старый класс section-title
  if (content.includes('section-title')) {
    fileLog += `   ⚠️ Старый класс "section-title" (заменить на text-h2)\n`;
    hasFindings = true;
  }

  if (hasFindings) {
    console.log(fileLog);
    findingsCount++;
  }
});

console.log(`\n✅ Проверено файлов: ${files.length}`);
console.log(`🎯 Файлов с хардкод-типографикой: ${findingsCount}\n`);

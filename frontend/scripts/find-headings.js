// find-headings.js
const fs = require('fs');
const path = require('path');

// Целевая папка для сканирования
const MARKETING_DIR = '/srv/steloom-dev/frontend/src/marketing';

function getAllFiles(dir) {
  let results = [];
  if (!fs.existsSync(dir)) return results;
  const list = fs.readdirSync(dir);
  for (const file of list) {
    const filePath = path.join(dir, file);
    const stat = fs.statSync(filePath);
    if (stat.isDirectory()) {
      results.push(...getAllFiles(filePath));
    } else if (file.endsWith('.tsx')) {
      results.push(filePath);
    }
  }
  return results;
}

const files = getAllFiles(MARKETING_DIR);
let findingsCount = 0;

console.log('\n🔍 СКАНИРОВАНИЕ ЗАГОЛОВКОВ И ХАРДКОД-ШРИФТОВ...\n');

files.forEach(file => {
  const content = fs.readFileSync(file, 'utf-8');
  const relativeName = file.replace(MARKETING_DIR, '');
  let hasFindings = false;
  let fileLog = `📄 Файл: src/marketing${relativeName}\n`;

  // 1. Поиск тегов h1, h2, h3
  const headings = content.match(/<h[1-3][^>]*className=["']([^"']+)["'][^>]*>/g) || [];
  headings.forEach(match => {
    const classNameMatch = match.match(/className=["']([^"']+)["']/);
    if (classNameMatch) {
      const classes = classNameMatch[1];
      // Проверяем, есть ли там хардкод (всё, что не text-h1, text-h2 и т.д.)
      if (!classes.includes('text-h1') && !classes.includes('text-h2') && !classes.includes('text-display')) {
        fileLog += `   ⚠️ Найден тег <h*> с хардкод классами:\n      "${classes}"\n`;
        hasFindings = true;
      }
    }
  });

  // 2. Поиск text-[clamp(...)] и других хардкод-размеров в любых тегах
  const hardcodedFonts = content.match(/text-\[clamp[^\]]+\]|text-\[\d+(\.\d+)?rem\]|leading-\[\d+(\.\d+)?\]|tracking-\[[-\d]+(\.\d+)?em\]/g) || [];
  if (hardcodedFonts.length > 0) {
    // Удаляем дубликаты для чистоты отчета
    const uniqueFonts = [...new Set(hardcodedFonts)];
    fileLog += `   ⚠️ Найдены inline-размеры: ${uniqueFonts.join(', ')}\n`;
    hasFindings = true;
  }

  // 3. Поиск старого класса .section-title (если он где-то остался)
  if (content.includes('section-title')) {
    fileLog += `   ⚠️ Используется старый класс: "section-title" (нужно заменить на text-h2)\n`;
    hasFindings = true;
  }

  if (hasFindings) {
    console.log(fileLog);
    findingsCount++;
  }
});

console.log(`\n✅ Проверено файлов: ${files.length}`);
console.log(`🎯 Файлов, требующих рефакторинга типографики: ${findingsCount}\n`);



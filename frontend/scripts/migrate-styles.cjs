const fs = require('fs');
const path = require('path');

const MARKETING_DIR = path.join(__dirname, '../src/marketing');

function getAllFiles(dir, extension = '.tsx') {
  const results = [];
  if (!fs.existsSync(dir)) return results;
  const list = fs.readdirSync(dir);
  for (const file of list) {
    const filePath = path.join(dir, file);
    if (filePath.includes('node_modules')) continue;
    const stat = fs.statSync(filePath);
    if (stat.isDirectory()) {
      results.push(...getAllFiles(filePath, extension));
    } else if (file.endsWith(extension)) {
      results.push(filePath);
    }
  }
  return results;
}

// Правила замены: используем arbitrary values с вашими CSS-переменными
const replacements = [
  // Цвета текста
  [/text-\[#1A1917\]/g, 'text-[var(--text-primary)]'],
  [/text-\[#78756F\]/g, 'text-[var(--text-secondary)]'],
  [/text-\[#A8A29E\]/g, 'text-[var(--text-muted)]'],
  [/text-\[#D6D0C7\]/g, 'text-[var(--text-faint)]'],
  [/text-\[#FAF8F5\]/g, 'text-[var(--text-inverse)]'],
  [/text-\[var\(--color-accent\)\]/g, 'text-[var(--accent-primary)]'],
  
  // Фоны
  [/bg-\[#FAF8F5\]/g, 'bg-[var(--bg-base)]'],
  [/bg-\[#F3F0EB\]/g, 'bg-[var(--bg-surface)]'],
  [/bg-\[#FFFFFF\]/g, 'bg-[var(--bg-card)]'],
  
  // Границы
  [/border-\[#E8E4DD\]/g, 'border-[var(--border-color)]'],
  [/border-\[var\(--color-border\)\]/g, 'border-[var(--border-color)]'],
];

let totalReplacements = 0;
const files = getAllFiles(MARKETING_DIR);

console.log(`\n🔍 Сканирую ${files.length} файлов в /src/marketing...\n`);

for (const file of files) {
  let content = fs.readFileSync(file, 'utf-8');
  let originalContent = content;
  let fileReplacements = 0;

  for (const [regex, replacement] of replacements) {
    const matches = content.match(regex);
    if (matches) {
      content = content.replace(regex, replacement);
      fileReplacements += matches.length;
    }
  }

  if (content !== originalContent) {
    fs.writeFileSync(file, content, 'utf-8');
    totalReplacements += fileReplacements;
    console.log(`   ✅ ${path.relative(path.join(__dirname, '..'), file)} (${fileReplacements} замен)`);
  }
}

console.log(`\n🎉 Готово! Всего выполнено ${totalReplacements} замен.`);
console.log('💡 Теперь весь хардкод цветов заменён на ссылки на ваши CSS-переменные из index.css.\n');

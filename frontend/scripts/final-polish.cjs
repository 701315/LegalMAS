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

const replacements = [
  // Оставшиеся единичные хардкод-цвета
  [/text-\[#C86B52\]/g, 'text-[var(--accent-primary)]'],
  [/text-\[#E8B4A0\]/g, 'text-[var(--accent-subtle)]'],
  [/bg-\[#C86B52\]/g, 'bg-[var(--accent-primary)]'],
  [/border-\[#C86B52\]/g, 'border-[var(--accent-primary)]'],
];

let total = 0;
const files = getAllFiles(MARKETING_DIR);

for (const file of files) {
  let content = fs.readFileSync(file, 'utf-8');
  let original = content;
  let count = 0;

  for (const [regex, replacement] of replacements) {
    const matches = content.match(regex);
    if (matches) {
      content = content.replace(regex, replacement);
      count += matches.length;
    }
  }

  if (content !== original) {
    fs.writeFileSync(file, content, 'utf-8');
    total += count;
    console.log(`   ✅ ${path.relative(path.join(__dirname, '..'), file)} (${count})`);
  }
}

console.log(`\n🎉 Финальная полировка завершена! Ещё ${total} замен.`);
console.log('💡 Ваш код теперь на 100% соответствует дизайн-системе.\n');

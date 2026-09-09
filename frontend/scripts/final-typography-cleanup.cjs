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

// Безопасные замены
const replacements = [
  // Стандартные Tailwind-классы
  [/text-\[1rem\]/g, 'text-base'],
  [/text-\[1\.125rem\]/g, 'text-lg'],
  [/text-\[0\.875rem\]/g, 'text-sm'],
  [/text-\[2\.5rem\]/g, 'text-4xl'],
  [/text-\[1\.75rem\]/g, 'text-3xl'],
  
  // Наши семантические классы
  [/text-\[clamp\(2\.5rem,5vw,4rem\)\]/g, 'text-display'],
  [/text-\[clamp\(1\.5rem,3vw,2rem\)\]/g, 'text-h2'],
];

let total = 0;
const files = getAllFiles(MARKETING_DIR);

console.log('\n🔍 Финальная очистка типографики...\n');

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

console.log(`\n🎉 Готово! Выполнено ${total} замен.`);
console.log('💡 Теперь ваш код максимально чист и семантичен.\n');

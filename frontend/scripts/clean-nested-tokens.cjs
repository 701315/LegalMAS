const fs = require('fs');
const path = require('path');

const SOLUTIONS_DIR = path.join(__dirname, '../src/marketing/pages/solutions');
const files = fs.readdirSync(SOLUTIONS_DIR).filter(f => f.endsWith('.tsx'));

console.log('\n===============================================================');
console.log('🧹 ОЧИСТКА ВЛОЖЕННЫХ CSS-ПЕРЕМЕННЫХ В SOLUTIONS');
console.log('===============================================================\n');

files.forEach(file => {
  const filePath = path.join(SOLUTIONS_DIR, file);
  let content = fs.readFileSync(filePath, 'utf-8');

  // Убираем двойные/тройные вложения var(--text-[var(--text-...)])
  content = content.replace(/text-\[var\(--text-\[var\(--text-([a-z]+)\)\]\)/g, 'text-[var(--text-$1)');
  content = content.replace(/text-\[var\(--text-([a-z]+)\)\]/g, 'text-[var(--text-$1)]');
  content = content.replace(/text-\[var\(--text-var\(--text-([a-z]+)\)\)\]/g, 'text-[var(--text-$1)]');
  content = content.replace(/bg-\[var\(--bg-\[var\(--bg-([a-z]+)\)\]\)/g, 'bg-[var(--bg-$1)');
  content = content.replace(/bg-\[var\(--bg-([a-z]+)\)\]/g, 'bg-[var(--bg-$1)]');

  // Нормализуем точные имена
  content = content.replace(/text-\[var\(--text-primary\)\]/g, 'text-[var(--text-primary)]');
  content = content.replace(/text-\[var\(--text-secondary\)\]/g, 'text-[var(--text-secondary)]');
  content = content.replace(/text-\[var\(--text-muted\)\]/g, 'text-[var(--text-muted)]');
  content = content.replace(/text-\[var\(--text-inverse\)\]/g, 'text-[var(--text-inverse)]');

  fs.writeFileSync(filePath, content, 'utf-8');
  console.log(`✅ ${file}: токены приведены в идеальный вид`);
});

console.log('\n===============================================================\n');

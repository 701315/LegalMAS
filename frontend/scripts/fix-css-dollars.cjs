const fs = require('fs');
const path = require('path');

const SOLUTIONS_DIR = path.join(__dirname, '../src/marketing/pages/solutions');
const files = fs.readdirSync(SOLUTIONS_DIR).filter(f => f.endsWith('.tsx'));

files.forEach(file => {
  const filePath = path.join(SOLUTIONS_DIR, file);
  let content = fs.readFileSync(filePath, 'utf-8');

  content = content.replace(/text-\[var\(--text-\$1\)\]/g, 'text-[var(--text-primary)]');
  content = content.replace(/bg-\[var\(--bg-\$1\)\]/g, 'bg-[var(--bg-base)]');

  fs.writeFileSync(filePath, content, 'utf-8');
});

console.log('✅ Очистка некорректных классов $1 завершена!');

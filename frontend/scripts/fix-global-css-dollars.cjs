const fs = require('fs');
const path = require('path');

const SRC_DIR = path.join(__dirname, '../src');

function cleanDir(dir) {
  const list = fs.readdirSync(dir);
  for (const file of list) {
    const filePath = path.join(dir, file);
    const stat = fs.statSync(filePath);
    if (stat.isDirectory()) {
      cleanDir(filePath);
    } else if (file.endsWith('.tsx') || file.endsWith('.ts') || file.endsWith('.css')) {
      let content = fs.readFileSync(filePath, 'utf-8');
      if (content.includes('$1')) {
        content = content.replace(/text-\[var\(--text-\$1\)\]/g, 'text-[var(--text-primary)]');
        content = content.replace(/bg-\[var\(--bg-\$1\)\]/g, 'bg-[var(--bg-base)]');
        fs.writeFileSync(filePath, content, 'utf-8');
        console.log(`✅ ${path.relative(SRC_DIR, filePath)}: символы $1 очищены!`);
      }
    }
  }
}

cleanDir(SRC_DIR);

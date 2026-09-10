const fs = require('fs');
const path = require('path');

const SRC_DIR = path.join(__dirname, '../src');

function purgeDollars(dir) {
  const list = fs.readdirSync(dir);
  for (const item of list) {
    const fullPath = path.join(dir, item);
    const stat = fs.statSync(fullPath);
    if (stat.isDirectory()) {
      purgeDollars(fullPath);
    } else if (item.endsWith('.css') || item.endsWith('.tsx') || item.endsWith('.ts')) {
      let content = fs.readFileSync(fullPath, 'utf-8');
      if (content.includes('$1')) {
        content = content.replace(/--bg-\$1/g, '--bg-base');
        content = content.replace(/--text-\$1/g, '--text-primary');
        content = content.replace(/text-\[var\(--text-\$1\)\]/g, 'text-[var(--text-primary)]');
        content = content.replace(/bg-\[var\(--bg-\$1\)\]/g, 'bg-[var(--bg-base)]');
        content = content.replace(/\$1/g, 'primary');
        fs.writeFileSync(fullPath, content, 'utf-8');
        console.log(`✅ ${path.relative(SRC_DIR, fullPath)}: очищено!`);
      }
    }
  }
}

purgeDollars(SRC_DIR);

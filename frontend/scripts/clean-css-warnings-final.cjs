const fs = require('fs');
const path = require('path');

const SRC_DIR = path.join(__dirname, '../src');

function searchAndReplace(dir) {
  const list = fs.readdirSync(dir);
  for (const item of list) {
    const fullPath = path.join(dir, item);
    const stat = fs.statSync(fullPath);
    if (stat.isDirectory()) {
      searchAndReplace(fullPath);
    } else if (item.endsWith('.tsx') || item.endsWith('.ts') || item.endsWith('.css')) {
      let content = fs.readFileSync(fullPath, 'utf-8');
      if (content.includes('$1')) {
        content = content.replace(/bg-\[var\(--bg-\$1\)\]/g, 'bg-[var(--bg-base)]');
        content = content.replace(/text-\[var\(--text-\$1\)\]/g, 'text-[var(--text-primary)]');
        content = content.replace(/\$1/g, 'primary');
        fs.writeFileSync(fullPath, content, 'utf-8');
        console.log(`✅ ${path.relative(SRC_DIR, fullPath)}: $1 очищен!`);
      }
    }
  }
}

searchAndReplace(SRC_DIR);

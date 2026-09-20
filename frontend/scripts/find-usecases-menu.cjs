const fs = require('fs');
const path = require('path');

const SRC = path.join(__dirname, '../src');

function search(dir, results = []) {
  for (const f of fs.readdirSync(dir)) {
    const p = path.join(dir, f);
    const st = fs.statSync(p);
    if (st.isDirectory()) search(p, results);
    else if (f.endsWith('.tsx') || f.endsWith('.ts')) {
      const c = fs.readFileSync(p, 'utf-8');
      if (
        c.includes('BY DIRECTION') ||
        c.includes('By Direction') ||
        c.includes('byDirection') ||
        c.includes('UseCases') ||
        c.includes('MegaMenu') ||
        c.includes('mega-menu') ||
        (c.includes('solutions') && c.includes('dropdown') && c.includes('SiteHeader'))
      ) {
        results.push(path.relative(path.join(__dirname, '..'), p));
      }
    }
  }
  return results;
}

console.log('\n===============================================================');
console.log('🔍 ПОИСК КОМПОНЕНТА МЕНЮ USE CASES');
console.log('===============================================================\n');

const files = search(SRC);
files.forEach(f => console.log('📄', f));

// Детальнее SiteHeader и shared
const candidates = [
  'src/marketing/components/shared/SiteHeader.tsx',
  'src/marketing/components/shared/MobileMenu.tsx',
];

['src/marketing/components/shared', 'src/marketing/components'].forEach(d => {
  const full = path.join(__dirname, '..', d);
  if (!fs.existsSync(full)) return;
  fs.readdirSync(full).forEach(f => {
    if (f.toLowerCase().includes('menu') || f.toLowerCase().includes('nav') || f.toLowerCase().includes('header') || f.toLowerCase().includes('dropdown')) {
      console.log('📄 candidate:', path.join(d, f));
    }
  });
});

console.log('\n');

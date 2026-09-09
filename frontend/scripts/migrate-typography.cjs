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

// Правила замены типографики (порядок важен: от более специфичных к менее)
const replacements = [
  // 1. Display / H1 (Главные заголовки)
  [/font-serif\s+text-\[clamp\(2\.5rem,5vw,4\.2rem\)\]\s+leading-\[1\.05\]\s+tracking-\[-0\.03em\]\s+text-\[var\(--text-primary\)\]/g, 'text-display'],
  [/font-serif\s+text-\[clamp\(2\.25rem,4vw,3\.25rem\)\]\s+leading-\[1\.05\]\s+tracking-\[-0\.03em\]\s+text-\[var\(--text-primary\)\]/g, 'text-h1'],
  
  // 2. H2 (Заголовки секций)
  [/font-serif\s+text-\[clamp\(1\.75rem,3vw,2\.5rem\)\]\s+leading-\[1\.15\]\s+tracking-\[-0\.02em\]\s+text-\[var\(--text-primary\)\]/g, 'text-h2'],
  
  // 3. H3 (Подзаголовки, часто с italic)
  [/font-serif\s+text-\[1\.25rem\]\s+tracking-tight\s+text-\[var\(--text-primary\)\]/g, 'text-h3'],
  [/font-serif\s+text-\[1\.35rem\]\s+tracking-tight\s+text-\[var\(--text-primary\)\]/g, 'text-h3'],
  
  // 4. Body (Основной текст)
  [/text-\[1\.0625rem\]\s+leading-\[1\.75\]\s+text-\[var\(--text-secondary\)\]\s+font-light/g, 'text-body'],
  [/text-\[1rem\]\s+leading-\[1\.75\]\s+text-\[var\(--text-secondary\)\]/g, 'text-body'],
  
  // 5. Body-sm (Текст в карточках и списках)
  [/text-\[0\.9375rem\]\s+leading-\[1\.65\]\s+text-\[var\(--text-secondary\)\]\s+font-light/g, 'text-body-sm'],
  [/text-\[0\.9375rem\]\s+leading-\[1\.7\]\s+text-\[var\(--text-secondary\)\]\s+font-light/g, 'text-body-sm'],
  [/text-\[0\.875rem\]\s+leading-\[1\.7\]\s+text-\[var\(--text-secondary\)\]/g, 'text-body-sm'],
  
  // 6. Eyebrow (Надзаголовки секций)
  [/text-\[0\.8125rem\]\s+uppercase\s+tracking-\[0\.12em\]\s+text-\[var\(--text-muted\)\]\s+font-medium/g, 'text-eyebrow'],
  [/text-\[0\.8125rem\]\s+uppercase\s+tracking-\[0\.14em\]\s+text-\[var\(--text-muted\)\]\s+font-medium/g, 'text-eyebrow'],
  
  // 7. Meta (Мелкие метки, нумерация)
  [/text-\[0\.75rem\]\s+uppercase\s+tracking-\[0\.14em\]\s+text-\[var\(--text-muted\)\]\s+font-medium/g, 'text-meta'],
  [/text-\[10px\]\s+font-medium\s+uppercase\s+tracking-\[0\.14em\]\s+text-\[var\(--text-muted\)\]/g, 'text-meta'],
  [/text-\[10px\]\s+font-medium\s+uppercase\s+tracking-\[0\.18em\]\s+text-\[var\(--text-muted\)\]/g, 'text-meta'],
  [/text-\[11px\]\s+font-semibold\s+uppercase\s+tracking-\[0\.18em\]\s+text-\[var\(--text-muted\)\]/g, 'text-meta'],
];

let totalReplacements = 0;
const files = getAllFiles(MARKETING_DIR);

console.log(`\n🔍 Сканирую ${files.length} файлов в /src/marketing для унификации типографики...\n`);

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

console.log(`\n🎉 Готово! Всего выполнено ${totalReplacements} замен типографики.`);
console.log('💡 Ваш JSX-код стал значительно чище и семантичнее!\n');

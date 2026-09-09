const fs = require('fs');
const path = require('path');

const MARKETING_DIR = path.join(__dirname, '../src/marketing');

function getAllFiles(dir) {
  let results = [];
  if (!fs.existsSync(dir)) return results;
  const list = fs.readdirSync(dir);
  for (const file of list) {
    const filePath = path.join(dir, file);
    const stat = fs.statSync(filePath);
    if (stat.isDirectory()) {
      results.push(...getAllFiles(filePath));
    } else if (file.endsWith('.tsx') || file.endsWith('.ts')) {
      results.push(filePath);
    }
  }
  return results;
}

const files = getAllFiles(MARKETING_DIR);
let modifiedCount = 0;

console.log('\n🚀 ЗАПУСК ФАЗЫ 2 МИГРАЦИИ ТИПОГРАФИКИ...\n');

files.forEach(file => {
  let content = fs.readFileSync(file, 'utf-8');
  const original = content;

  // 1. Крупные заголовки (Hero / Display)
  content = content.replace(
    /font-serif\s+text-5xl\s+leading-\[0\.95\]\s+tracking-\[-0\.04em\][^\s"]*/g,
    'text-display'
  );
  content = content.replace(/text-\[2.25rem\]\s+leading-\[1\.05\]\s+tracking-\[-0\.03em\]/g, 'text-h1');
  content = content.replace(/text-\[2rem\]\s+leading-\[1\.15\]/g, 'text-h2');

  // 2. Средние и мелкие заголовки (H2 / H3)
  content = content.replace(/font-serif\s+text-4xl\s+leading-tight\s+tracking-tight/g, 'text-h2');
  content = content.replace(/font-serif\s+text-3xl\s+leading-none\s+tracking-tight/g, 'text-h2');
  content = content.replace(/font-serif\s+text-3xl\s+tracking-\[-0\.03em\]/g, 'text-h2');
  content = content.replace(/font-serif\s+text-3xl\s+leading-tight\s+tracking-\[-0\.03em\]/g, 'text-h2');
  content = content.replace(/font-serif\s+text-2xl\s+tracking-\[-0\.03em\]/g, 'text-h3');
  content = content.replace(/font-serif\s+text-2xl\s+italic\s+mb-4\s+tracking-tight/g, 'text-h3 italic mb-4');
  content = content.replace(/font-serif\s+text-xl\s+italic\s+mb-3\s+tracking-tight/g, 'text-h3 italic mb-3');
  content = content.replace(/font-serif\s+text-\[1\.375rem\]\s+leading-\[1\.2\]\s+tracking-\[-0\.02em\]/g, 'text-h3');

  // 3. Мета-тексты и надзаголовки
  content = content.replace(/text-\[10px\]\s+tracking-\[0\.22em\]/g, 'text-meta');
  content = content.replace(/text-\[10px\]\s+tracking-\[0\.18em\]/g, 'text-meta');
  content = content.replace(/text-\[10px\]\s+tracking-\[0\.14em\]/g, 'text-meta');
  content = content.replace(/text-\[11px\]\s+tracking-\[0\.22em\]/g, 'text-meta');
  content = content.replace(/text-\[11px\]\s+tracking-\[0\.2em\]/g, 'text-meta');

  // 4. Очистка хардкод-интервалов основного текста (leading-[1.7..1.8])
  content = content.replace(/leading-\[1\.75\]/g, 'leading-relaxed');
  content = content.replace(/leading-\[1\.7\]/g, 'leading-relaxed');
  content = content.replace(/leading-\[1\.8\]/g, 'leading-relaxed');
  content = content.replace(/leading-\[1\.65\]/g, 'leading-normal');
  content = content.replace(/leading-\[1\.6\]/g, 'leading-normal');

  if (content !== original) {
    fs.writeFileSync(file, content, 'utf-8');
    const relativeName = path.relative(MARKETING_DIR, file);
    console.log(`  ✅ Обновлён: src/marketing/${relativeName}`);
    modifiedCount++;
  }
});

console.log(`\n🎉 Фаза 2 завершена! Обновлено файлов: ${modifiedCount}\n`);

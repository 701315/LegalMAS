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

console.log('\n🚀 ЗАПУСК МИГРАЦИИ ТИПОГРАФИКИ В MARKETING...\n');

files.forEach(file => {
  let content = fs.readFileSync(file, 'utf-8');
  const original = content;

  // 1. Замена устаревшего класса section-title на text-h2
  content = content.replace(/\bsection-title\b/g, 'text-h2');

  // 2. Унификация хардкод clamp заголовков в text-display или text-h1
  content = content.replace(
    /font-serif\s+text-\[clamp\(2\.5rem,5vw,4\.5rem\)\]\s+leading-\[1\.05\]\s+tracking-\[-0\.03em\]/g,
    'text-display'
  );
  content = content.replace(
    /font-serif\s+text-\[clamp\(2\.25rem,4vw,3\.25rem\)\]\s+leading-\[1\.05\]\s+tracking-\[-0\.03em\]/g,
    'text-h1'
  );
  content = content.replace(
    /text-\[clamp\(2rem,4vw,3\.05rem\)\]\s+leading-\[1\.08\]\s+tracking-\[-0\.03em\]/g,
    'text-h1'
  );

  // 3. Замена типовых inline-параметров межстрочного интервала в параграфах
  content = content.replace(/text-\[1\.0625rem\]\s+leading-\[1\.7\]/g, 'text-body');
  content = content.replace(/text-\[1\.0625rem\]\s+leading-\[1\.75\]/g, 'text-body');

  // 4. Замена мелких надзаголовков (eyebrow / meta)
  content = content.replace(/text-\[11px\]\s+font-bold\s+uppercase\s+tracking-\[0\.2em\]/g, 'text-meta font-bold');
  content = content.replace(/text-\[11px\]\s+font-bold\s+uppercase\s+tracking-widest/g, 'text-meta font-bold');

  if (content !== original) {
    fs.writeFileSync(file, content, 'utf-8');
    const relativeName = path.relative(MARKETING_DIR, file);
    console.log(`  ✅ Обновлён: src/marketing/${relativeName}`);
    modifiedCount++;
  }
});

console.log(`\n🎉 Миграция завершена! Успешно обновлено файлов: ${modifiedCount}\n`);

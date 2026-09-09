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

console.log('\n🚀 ЗАПУСК ФИНАЛЬНОЙ ПОЛИРОВКИ ТИПОГРАФИКИ В MARKETING...\n');

files.forEach(file => {
  let content = fs.readFileSync(file, 'utf-8');
  const original = content;

  // 1. Приведение заголовков без токенов к системным h1, h2, h3, display
  content = content.replace(/font-serif\s+text-xl\s+tracking-\[-0\.02em\]/g, 'text-h3 font-serif');
  content = content.replace(/text-xl\s+font-serif\s+text-white\s+lg:text-3xl/g, 'text-h3 lg:text-h2 font-serif text-white');
  content = content.replace(/text-lg\s+font-medium\s+text-\[var\(--text-primary\)\]\s+tracking-tight/g, 'text-h3 font-medium text-[var(--text-primary)]');
  content = content.replace(/(?:\b[a-z]+:)?text-\[4\.5rem\]/g, 'text-display');
  content = content.replace(/(?:\b[a-z]+:)?text-\[2\.25rem\]/g, 'text-h1');
  content = content.replace(/(?:\b[a-z]+:)?text-\[2rem\]/g, 'text-h2');
  content = content.replace(/(?:\b[a-z]+:)?text-\[1\.375rem\]/g, 'text-h3');

  // 2. Хардкодные мелкие размеры (10px, 11px, 13px, 15px) в токены meta / body-sm
  content = content.replace(/(?:\b[a-z]+:)?text-\[10px\]/g, 'text-meta');
  content = content.replace(/(?:\b[a-z]+:)?text-\[11px\]/g, 'text-meta');
  content = content.replace(/(?:\b[a-z]+:)?text-\[0\.6875rem\]/g, 'text-meta');
  content = content.replace(/(?:\b[a-z]+:)?text-\[13px\]/g, 'text-body-sm');
  content = content.replace(/(?:\b[a-z]+:)?text-\[15px\]/g, 'text-body-sm');
  content = content.replace(/(?:\b[a-z]+:)?text-\[0\.95rem\]/g, 'text-body-sm');

  // 3. Удаление избыточных tracking и leading (уже заложены в токены text-display, text-h1..h3, text-body)
  content = content.replace(/(?:\b[a-z]+:)?tracking-\[-0\.0[012345]em\]/g, '');
  content = content.replace(/(?:\b[a-z]+:)?tracking-\[0\.(12|14|18|20|22|24)em\]/g, '');
  content = content.replace(/(?:\b[a-z]+:)?tracking-\[0\.2em\]/g, '');
  content = content.replace(/(?:\b[a-z]+:)?leading-\[1\.05\]/g, '');
  content = content.replace(/(?:\b[a-z]+:)?leading-\[1\.15\]/g, '');
  content = content.replace(/(?:\b[a-z]+:)?leading-\[1\.5\]/g, '');
  content = content.replace(/(?:\b[a-z]+:)?leading-\[1\.4\]/g, '');

  // 4. Форматирование двойных пробелов внутри className
  content = content.replace(/className=["']([^"']+)["']/g, (match, classNames) => {
    const cleaned = classNames.replace(/\s+/g, ' ').trim();
    return `className="${cleaned}"`;
  });

  if (content !== original) {
    fs.writeFileSync(file, content, 'utf-8');
    const relativeName = path.relative(MARKETING_DIR, file);
    console.log(`  ✅ Обновлён: src/marketing/${relativeName}`);
    modifiedCount++;
  }
});

console.log(`\n🎉 Финальная полировка завершена! Успешно обновлено файлов: ${modifiedCount}\n`);

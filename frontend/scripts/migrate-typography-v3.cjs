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

console.log('\n🚀 ЗАПУСК ФАЗЫ 3 (ФИНАЛЬНАЯ ПОЛИРОВКА ТИПОГРАФИКИ)...\n');

files.forEach(file => {
  let content = fs.readFileSync(file, 'utf-8');
  const original = content;

  // 1. Очистка избыточных tracking и leading, которые уже заложены в CSS-токены
  content = content.replace(/\btracking-\[-0\.0[234]em\]\b/g, '');
  content = content.replace(/\btracking-\[-0\.005em\]\b/g, '');
  content = content.replace(/\btracking-\[0\.(12|14|18|20|22|24)em\]\b/g, '');
  content = content.replace(/\bleading-\[1\.05\]\b/g, '');
  content = content.replace(/\bleading-\[1\.15\]\b/g, '');
  content = content.replace(/\bleading-\[1\.2\]\b/g, '');
  content = content.replace(/\bleading-\[0\.95\]\b/g, '');

  // 2. Преобразование оставшихся несистемных размеров в токены
  content = content.replace(/\btext-\[4\.5rem\]\b/g, 'text-display');
  content = content.replace(/\btext-\[2\.25rem\]\b/g, 'text-h1');
  content = content.replace(/\btext-\[2rem\]\b/g, 'text-h2');
  content = content.replace(/\btext-\[1\.375rem\]\b/g, 'text-h3');
  content = content.replace(/\btext-\[0\.6875rem\]\b/g, 'text-meta');
  content = content.replace(/\btext-\[10px\]\b/g, 'text-meta');
  content = content.replace(/\btext-\[11px\]\b/g, 'text-meta');
  content = content.replace(/\btext-\[13px\]\b/g, 'text-body-sm');
  content = content.replace(/\btext-\[15px\]\b/g, 'text-body-sm');
  content = content.replace(/\btext-\[0\.95rem\]\b/g, 'text-body-sm');

  // 3. Перевод оставшихся мелких заголовков в системный text-h3
  content = content.replace(/text-base\s+font-semibold\s+text-\[var\(--text-primary\)\]/g, 'text-h3 font-semibold text-[var(--text-primary)]');
  content = content.replace(/text-base\s+font-medium\s+text-primary/g, 'text-h3 font-medium text-primary');
  content = content.replace(/text-xl\s+font-semibold\s+tracking-tight/g, 'text-h3 font-semibold');

  // 4. Форматирование лишних пробелов внутри className=""
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

console.log(`\n🎉 Фаза 3 завершена! Успешно обновлено файлов: ${modifiedCount}\n`);

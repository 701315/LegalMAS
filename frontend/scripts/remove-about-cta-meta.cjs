const fs = require('fs');
const path = require('path');

const SRC_DIR = path.join(__dirname, '../src');

function searchAndClean(dir) {
  if (!fs.existsSync(dir)) return;
  const list = fs.readdirSync(dir);

  for (const item of list) {
    const fullPath = path.join(dir, item);
    const stat = fs.statSync(fullPath);

    if (stat.isDirectory()) {
      searchAndClean(fullPath);
    } else if (item.endsWith('.tsx') || item.endsWith('.ts')) {
      let content = fs.readFileSync(fullPath, 'utf-8');
      const original = content;

      // Удаляем вхождения t("about.cta.meta") вместе с тегом <p>
      content = content.replace(
        /\s*<p[^>]*>\s*\{t\("about\.cta\.meta"\)\}\s*<\/p>/g,
        ''
      );
      content = content.replace(
        /\s*<p[^>]*>\s*\{t\("marketing:about\.cta\.meta"\)\}\s*<\/p>/g,
        ''
      );
      // Если у вызова t("about.cta.meta") есть fallback
      content = content.replace(
        /\s*<p[^>]*>\s*\{t\("about\.cta\.meta"[^}]*\)\}\s*<\/p>/g,
        ''
      );

      if (content !== original) {
        fs.writeFileSync(fullPath, content, 'utf-8');
        console.log(`✅ ${path.relative(SRC_DIR, fullPath)}: Элемент about.cta.meta удалён из JSX!`);
      }
    }
  }
}

console.log('\n===============================================================');
console.log('🧹 ПОИСК И УДАЛЕНИЕ ЭЛЕМЕНТА about.cta.meta В JSX');
console.log('===============================================================\n');

searchAndClean(SRC_DIR);

console.log('\n===============================================================\n');

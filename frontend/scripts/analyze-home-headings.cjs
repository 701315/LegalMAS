const fs = require('fs');
const path = require('path');

const HOME_DIR = path.join(__dirname, '../src/marketing/components/home');
const HOME_PAGE = path.join(__dirname, '../src/marketing/pages/HomePage.tsx');

function getAllFiles(dir) {
  let results = [];
  if (fs.existsSync(dir)) {
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
  }
  return results;
}

const files = getAllFiles(HOME_DIR);
if (fs.existsSync(HOME_PAGE)) files.unshift(HOME_PAGE);

console.log('\n🔍 АНАЛИЗ ЗАГОЛОВКОВ И СТИЛЕЙ НА ГЛАВНОЙ СТРАНИЦЕ (HOME)...\n');

let totalHeadings = 0;

files.forEach(file => {
  const content = fs.readFileSync(file, 'utf-8');
  const rel = path.relative(path.join(__dirname, '../src/marketing'), file);

  const regex = /<(h[1-4]|span|p)[^>]*className=["']([^"']*)["'][^>]*>([\s\S]*?)<\/\1>/gi;
  let fileHeadings = [];
  let match;

  while ((match = regex.exec(content)) !== null) {
    const tag = match[1];
    const className = match[2];
    const inner = match[3].replace(/\s+/g, ' ').trim();

    // Фильтруем только заголовки или элементы с типографическими токенами
    const isHeadingTag = /^h[1-4]$/i.test(tag);
    const hasTypographyClass = /text-(display|h1|h2|h3|eyebrow|meta)/.test(className);

    if (isHeadingTag || hasTypographyClass) {
      fileHeadings.push({
        tag: tag.toLowerCase(),
        className,
        text: inner.length > 70 ? inner.slice(0, 70) + '...' : inner
      });
    }
  }

  if (fileHeadings.length > 0) {
    console.log(`📄 src/marketing/${rel}`);
    fileHeadings.forEach((h, idx) => {
      console.log(`   ${idx + 1}. <${h.tag}> [${h.className}]`);
      console.log(`      💬 Content: ${h.text}\n`);
      totalHeadings++;
    });
  }
});

console.log(`==================================================`);
console.log(`📊 Всего заголовков на главной странице: ${totalHeadings}`);
console.log(`==================================================\n`);

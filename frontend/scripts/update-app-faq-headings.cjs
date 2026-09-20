const fs = require('fs');
const path = require('path');

const HOME_DIR = path.join(__dirname, '../src/marketing/components/home');

console.log('\n🚀 ОБНОВЛЕНИЕ ЗАГОЛОВКОВ В APPLICATION И FAQ...\n');

// 1. ApplicationSection -> text-h1 !text-white (гарантированно белый заголовок на тёмном фоне)
const appPath = path.join(HOME_DIR, 'ApplicationSection/ApplicationSection.tsx');
if (fs.existsSync(appPath)) {
  let content = fs.readFileSync(appPath, 'utf-8');
  content = content.replace(
    /className=["'][^"']*text-h[12][^"']*["']/g,
    'className="text-h1 !text-white max-w-4xl mx-auto mb-4"'
  );
  fs.writeFileSync(appPath, content, 'utf-8');
  console.log('  ✅ ApplicationSection: заголовок установлен в text-h1 !text-white (Белый на тёмном фоне)');
}

// 2. FaqSection -> text-h1 (Вопросы перед пилотом)
const faqPath = path.join(HOME_DIR, 'FaqSection.tsx');
if (fs.existsSync(faqPath)) {
  let content = fs.readFileSync(faqPath, 'utf-8');
  content = content.replace(
    /className=["']text-h2 text-\[var\(--text-primary\)\] whitespace-pre-line["']/g,
    'className="text-h1 text-[var(--text-primary)] whitespace-pre-line max-w-3xl"'
  );
  fs.writeFileSync(faqPath, content, 'utf-8');
  console.log('  ✅ FaqSection: заголовок обновлен до text-h1 (52px)');
}

console.log('\n🎉 Заголовки успешно настроены!\n');

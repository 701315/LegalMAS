const fs = require('fs');
const path = require('path');

const appPath = path.join(__dirname, '../src/marketing/components/home/ApplicationSection/ApplicationSection.tsx');

if (fs.existsSync(appPath)) {
  let content = fs.readFileSync(appPath, 'utf-8');

  // 1. Возвращаем заголовкам карточек ролей нормальный размер text-h3 lg:text-h2
  content = content.replace(
    /<h3>\s*className=["'][^"']*text-h1[^"']*["']/g,
    '<h3 className="text-h3 lg:text-h2 font-serif text-white transition-all duration-300 tracking-tight leading-tight"'
  );

  // 2. Исправляем текст описания секции на системный text-body
  content = content.replace(
    /className=["']mt-4 text-base leading-relaxed text-stone-300 lg:text-lg font-medium["']/g,
    'className="mt-4 text-body !text-stone-300 font-medium max-w-2xl mx-auto"'
  );

  fs.writeFileSync(appPath, content, 'utf-8');
  console.log('✅ ApplicationSection.tsx успешно исправлен!');
}

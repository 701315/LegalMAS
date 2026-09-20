const fs = require('fs');
const path = require('path');

const indexHtmlPath = path.join(__dirname, '../index.html');
const headerPath = path.join(__dirname, '../src/marketing/components/shared/SiteHeader.tsx');
const cssPath = path.join(__dirname, '../src/index.css');

console.log('\n===============================================================');
console.log('🔍 ПОИСК ЭЛЕМЕНТОВ, ВЫЗЫВАЮЩИХ ВЫЛЕЗАНИЕ ЗА ПРЕДЕЛЫ ЭКРАНА');
console.log('===============================================================\n');

// 1. Проверка index.html viewport
if (fs.existsSync(indexHtmlPath)) {
  const html = fs.readFileSync(indexHtmlPath, 'utf-8');
  console.log('📄 index.html viewport:');
  const vp = html.match(/<meta[^>]*viewport[^>]*>/i)?.[0];
  console.log('  ', vp || 'НЕ НАЙДЕН');
}

// 2. Проверка SiteHeader.tsx на фиксированные ширины или padding
if (fs.existsSync(headerPath)) {
  const header = fs.readFileSync(headerPath, 'utf-8');
  console.log('\n📄 SiteHeader.tsx элементы и ширины:');
  const lines = header.split('\n');
  lines.forEach((line, idx) => {
    if (
      line.includes('min-w') ||
      line.includes('w-[') ||
      line.includes('px-') ||
      line.includes('gap-') ||
      line.includes('<header') ||
      line.includes('flex')
    ) {
      if (idx < 200) {
        console.log(`  [Строка ${idx + 1}] ${line.trim()}`);
      }
    }
  });
}

console.log('\n===============================================================\n');

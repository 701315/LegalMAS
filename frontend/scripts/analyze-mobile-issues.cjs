const fs = require('fs');
const path = require('path');

console.log('\n===============================================================');
console.log('🔍 ДИАГНОСТИКА МОБИЛЬНОЙ ВЕРСТКИ И ЯЗЫКОВОГО СЕЛЕКТОРА');
console.log('===============================================================\n');

// 1. Проверка index.html на meta viewport
const htmlPath = path.join(__dirname, '../index.html');
if (fs.existsSync(htmlPath)) {
  const html = fs.readFileSync(htmlPath, 'utf-8');
  const viewportMatch = html.match(/<meta[^>]*name=["']viewport["'][^>]*>/i);
  console.log('📄 1. index.html:');
  if (viewportMatch) {
    console.log(`   ✅ Meta Viewport найден: ${viewportMatch[0]}`);
  } else {
    console.log('   ❌ КРИТИЧЕСКАЯ ОШИБКА: Meta viewport отсутствует в index.html!');
  }
}

console.log('\n---------------------------------------------------------------\n');

// 2. Проверка SiteHeader.tsx на переключатель языка и логику мобильного адаптива
const headerPath = path.join(__dirname, '../src/marketing/components/shared/SiteHeader.tsx');
if (fs.existsSync(headerPath)) {
  const headerContent = fs.readFileSync(headerPath, 'utf-8');
  console.log('📄 2. SiteHeader.tsx (Кнопка языка и адаптивность):');

  const lines = headerContent.split('\n');
  lines.forEach((line, i) => {
    if (line.includes('Globe') || line.includes('language') || line.includes('i18n.changeLanguage') || line.includes('EN') || line.includes('RU')) {
      console.log(`   [Строка ${i + 1}] ${line.trim()}`);
    }
  });
}

console.log('\n---------------------------------------------------------------\n');

// 3. Проверка MobileMenu.tsx на выбор языка
const mobileMenuPath = path.join(__dirname, '../src/marketing/components/shared/MobileMenu.tsx');
if (fs.existsSync(mobileMenuPath)) {
  const mobileContent = fs.readFileSync(mobileMenuPath, 'utf-8');
  console.log('📄 3. MobileMenu.tsx (Наличие языка в мобильном меню):');

  const lines = mobileContent.split('\n');
  lines.forEach((line, i) => {
    if (line.includes('Globe') || line.includes('language') || line.includes('i18n') || line.includes('lang')) {
      console.log(`   [Строка ${i + 1}] ${line.trim()}`);
    }
  });
}

console.log('\n---------------------------------------------------------------\n');

// 4. Проверка index.css на overflow-x: hidden для html, body
const cssPath = path.join(__dirname, '../src/index.css');
if (fs.existsSync(cssPath)) {
  const css = fs.readFileSync(cssPath, 'utf-8');
  console.log('📄 4. src/index.css (Защита от горизонтального скролла):');

  const hasBodyOverflow = css.includes('overflow-x: hidden') || css.includes('overflow-x-hidden');
  if (hasBodyOverflow) {
    console.log('   ✅ Найдена защита overflow-x: hidden в CSS.');
  } else {
    console.log('   ⚠️ Защита overflow-x: hidden отсутствует в корневом CSS!');
  }
}

console.log('\n===============================================================\n');

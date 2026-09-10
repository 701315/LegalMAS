const fs = require('fs');
const path = require('path');

console.log('\n===============================================================');
console.log('🛠️ ИСПРАВЛЕНИЕ: FAQ, ЯЗЫК В МОБИЛЬНОМ МЕНЮ, OVERFLOW');
console.log('===============================================================\n');

// 1. Исправление MobileMenu.tsx — кнопка языка показывает literal ключ вместо текста
const mobileMenuPath = path.join(__dirname, '../src/marketing/components/shared/MobileMenu.tsx');
if (fs.existsSync(mobileMenuPath)) {
  let content = fs.readFileSync(mobileMenuPath, 'utf-8');
  
  // Заменяем literal "mobileMenu.language" на вызов t()
  content = content.replace(
    /mobileMenu\.language/g,
    't("mobileMenu.language")'
  );
  
  // Убедимся что t импортирован из useTranslation
  if (!content.includes('const { t,')) {
    content = content.replace(
      /const \{ i18n \} = useTranslation\("marketing"\);/g,
      'const { t, i18n } = useTranslation("marketing");'
    );
  }
  
  fs.writeFileSync(mobileMenuPath, content, 'utf-8');
  console.log('✅ MobileMenu.tsx: Кнопка языка теперь использует t("mobileMenu.language")!');
}

// 2. Проверка и исправление FAQ секции на главной (FaqSection.tsx)
const faqPath = path.join(__dirname, '../src/marketing/components/home/FaqSection.tsx');
if (fs.existsSync(faqPath)) {
  let content = fs.readFileSync(faqPath, 'utf-8');
  
  // Добавляем overflow-hidden и proper z-index на контейнер FAQ
  content = content.replace(
    /className="([^"]*relative[^"]*)"/g,
    'className="$1 overflow-hidden"'
  );
  
  // Проверяем что у заголовка есть правильный z-index
  if (content.includes('<h2') && !content.includes('z-10')) {
    content = content.replace(
      /<h2 className="text-h1/g,
      '<h2 className="text-h1 relative z-10"'
    );
  }
  
  fs.writeFileSync(faqPath, content, 'utf-8');
  console.log('✅ FaqSection.tsx: Добавлен overflow-hidden и z-index для заголовка!');
}

// 3. Проверка HomePage.tsx на главной странице
const homePagePath = path.join(__dirname, '../src/marketing/pages/HomePage.tsx');
if (fs.existsSync(homePagePath)) {
  let content = fs.readFileSync(homePagePath, 'utf-8');
  
  // Убедимся что у main есть overflow-x-hidden
  if (content.includes('<main') && !content.includes('overflow-x-hidden')) {
    content = content.replace(
      /<main([^>]*)>/g,
      '<main$1 className="$1 overflow-x-hidden">'
    ).replace('className="className="', 'className="');
  }
  
  fs.writeFileSync(homePagePath, content, 'utf-8');
  console.log('✅ HomePage.tsx: Добавлен overflow-x-hidden!');
}

// 4. Глобальная защита в index.css
const cssPath = path.join(__dirname, '../src/index.css');
if (fs.existsSync(cssPath)) {
  let css = fs.readFileSync(cssPath, 'utf-8');
  
  if (!css.includes('/* MOBILE OVERFLOW PROTECTION */')) {
    const protection = `
/* MOBILE OVERFLOW PROTECTION */
html, body, #root {
  max-width: 100vw !important;
  overflow-x: hidden !important;
  position: relative;
}

/* Fix for mobile header overflow */
header {
  max-width: 100vw !important;
  overflow-x: hidden !important;
}

/* Fix FAQ z-index issues */
.faq-section, [class*="FaqSection"] {
  position: relative;
  z-index: 1;
}
`;
    css = protection + css;
    fs.writeFileSync(cssPath, css, 'utf-8');
    console.log('✅ index.css: Добавлена глобальная защита от overflow!');
  }
}

console.log('\n===============================================================\n');

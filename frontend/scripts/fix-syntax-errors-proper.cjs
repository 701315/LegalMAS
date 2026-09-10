const fs = require('fs');
const path = require('path');

console.log('\n===============================================================');
console.log('️ ИСПРАВЛЕНИЕ СИНТАКСИЧЕСКИХ ОШИБОК');
console.log('===============================================================\n');

// 1. Исправление MobileMenu.tsx — убираем двойное t("t(...)")
const mobileMenuPath = path.join(__dirname, '../src/marketing/components/shared/MobileMenu.tsx');
if (fs.existsSync(mobileMenuPath)) {
  let content = fs.readFileSync(mobileMenuPath, 'utf-8');
  
  // Исправляем двойное t("t(...)") на правильное t("mobileMenu.language")
  content = content.replace(/t\("t\("mobileMenu\.language"\)"\)/g, 't("mobileMenu.language")');
  
  // Убеждаемся что t импортирован
  if (!content.includes('const { t,')) {
    content = content.replace(
      /const \{ i18n \} = useTranslation\("marketing"\);/g,
      'const { t, i18n } = useTranslation("marketing");'
    );
  }
  
  fs.writeFileSync(mobileMenuPath, content, 'utf-8');
  console.log('✅ MobileMenu.tsx: Исправлен вызов t("mobileMenu.language")!');
}

// 2. Исправление FaqSection.tsx — восстанавливаем правильный className
const faqPath = path.join(__dirname, '../src/marketing/components/home/FaqSection.tsx');
if (fs.existsSync(faqPath)) {
  let content = fs.readFileSync(faqPath, 'utf-8');
  
  // Исправляем сломанный h2 с вынесенными атрибутами
  content = content.replace(
    /<h2 className="text-h1 relative z-10" text-\[var\(--text-primary\)\] whitespace-pre-line max-w-3xl">/g,
    '<h2 className="text-h1 relative z-10 text-[var(--text-primary)] whitespace-pre-line max-w-3xl">'
  );
  
  fs.writeFileSync(faqPath, content, 'utf-8');
  console.log('✅ FaqSection.tsx: Восстановлен правильный className для h2!');
}

// 3. Исправление HomePage.tsx — убираем дубликат className и ломающий синтаксис
const homePagePath = path.join(__dirname, '../src/marketing/pages/HomePage.tsx');
if (fs.existsSync(homePagePath)) {
  let content = fs.readFileSync(homePagePath, 'utf-8');
  
  // Исправляем сломанный main с дубликатом className
  content = content.replace(
    /<main className="text-\[var\(--text-primary\)\]" className=" className="text-\[var\(--text-primary\)\]" overflow-x-hidden">/g,
    '<main className="text-[var(--text-primary)] overflow-x-hidden">'
  );
  
  fs.writeFileSync(homePagePath, content, 'utf-8');
  console.log('✅ HomePage.tsx: Убран дубликат className на main!');
}

console.log('\n===============================================================\n');

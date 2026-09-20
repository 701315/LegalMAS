const fs = require('fs');
const path = require('path');

console.log('\n===============================================================');
console.log('️ ИСПРАВЛЕНИЕ КНОПКИ ЯЗЫКА В МОБИЛЬНОМ МЕНЮ');
console.log('===============================================================\n');

// 1. Добавляем ключ mobileMenu.language во все словари
const LOCALES_DIR = path.join(__dirname, '../public/locales');
const LANGUAGES = ['en', 'ru', 'ar', 'tr'];

const translations = {
  en: 'Language',
  ru: 'Язык',
  ar: 'اللغة',
  tr: 'Dil'
};

LANGUAGES.forEach(lang => {
  const filePath = path.join(LOCALES_DIR, lang, 'marketing.json');
  if (fs.existsSync(filePath)) {
    const dict = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
    
    if (!dict.mobileMenu) dict.mobileMenu = {};
    dict.mobileMenu.language = translations[lang];
    
    fs.writeFileSync(filePath, JSON.stringify(dict, null, 2), 'utf-8');
    console.log(`✅ ${lang}/marketing.json: Добавлен ключ mobileMenu.language = "${translations[lang]}"`);
  }
});

// 2. Проверяем MobileMenu.tsx на правильный вызов t()
const mobileMenuPath = path.join(__dirname, '../src/marketing/components/shared/MobileMenu.tsx');
if (fs.existsSync(mobileMenuPath)) {
  let content = fs.readFileSync(mobileMenuPath, 'utf-8');
  
  // Убеждаемся что t импортирован из useTranslation
  if (!content.includes('const { t,')) {
    content = content.replace(
      /const \{ i18n \} = useTranslation\("marketing"\);/g,
      'const { t, i18n } = useTranslation("marketing");'
    );
  }
  
  // Исправляем любой вариант отображения literal ключа
  content = content.replace(/mobileMenu\.language/g, 't("mobileMenu.language")');
  content = content.replace(/t\("t\("mobileMenu\.language"\)"\)/g, 't("mobileMenu.language")');
  content = content.replace(/t\("mobileMenu\.language"\)/g, 't("mobileMenu.language")');
  
  fs.writeFileSync(mobileMenuPath, content, 'utf-8');
  console.log('✅ MobileMenu.tsx: Вызов t("mobileMenu.language") исправлен!');
}

console.log('\n===============================================================\n');

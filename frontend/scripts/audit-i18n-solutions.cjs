const fs = require('fs');
const path = require('path');

const SOLUTIONS_DIR = path.join(__dirname, '../src/marketing/pages/solutions');
const DICT_PATH = path.join(__dirname, '../public/locales/en/marketing.json');

console.log('\n===============================================================');
console.log('🌐 ГЛУБОКИЙ I18N АУДИТ РАЗДЕЛА SOLUTIONS');
console.log('===============================================================\n');

// 1. Загрузка и парсинг словаря
let dict = {};
if (fs.existsSync(DICT_PATH)) {
  dict = JSON.parse(fs.readFileSync(DICT_PATH, 'utf-8'));
  console.log(`✅ Словарь загружен: ${DICT_PATH}\n`);
} else {
  console.error(`❌ ОШИБКА: Словарь не найден по пути ${DICT_PATH}`);
  process.exit(1);
}

// Функция для проверки существования вложенного ключа в JSON (например: "solutions.realEstate.hero.title")
function checkKeyExists(obj, keyPath) {
  // Игнорируем ключи с динамическими переменными типа \`solutions.${dynamic}\`
  if (keyPath.includes('${')) return true; 
  
  return keyPath.split('.').reduce((acc, part) => {
    if (acc && acc[part] !== undefined) return acc[part];
    return undefined;
  }, obj) !== undefined;
}

const files = fs.readdirSync(SOLUTIONS_DIR).filter(f => f.endsWith('.tsx'));

let totalMissingKeys = 0;
let totalHardcodedStrings = 0;

files.forEach(file => {
  const filePath = path.join(SOLUTIONS_DIR, file);
  const content = fs.readFileSync(filePath, 'utf-8');
  
  console.log(`---------------------------------------------------------------`);
  console.log(`📄 ФАЙЛ: ${file}`);
  
  // 1. Проверка хука useTranslation
  if (!content.includes('useTranslation')) {
    console.log(`   ⚠️ Нет импорта useTranslation!`);
  } else if (!content.includes('useTranslation("marketing")') && !content.includes("useTranslation('marketing')")) {
    console.log(`   ⚠️ Хук useTranslation инициализирован БЕЗ указания неймспейса "marketing"!`);
  } else {
    console.log(`   ✅ Хук i18n подключен правильно.`);
  }

  // 2. Сбор всех ключей t("key") или t("key", "default")
  const keyRegex = /t\(\s*["']([a-zA-Z0-9_.-]+)["']/g;
  let match;
  const extractedKeys = new Set();
  
  while ((match = keyRegex.exec(content)) !== null) {
    extractedKeys.add(match[1]);
  }

  // 3. Проверка ключей в словаре
  const missingKeys = [];
  extractedKeys.forEach(key => {
    // Убираем префикс неймспейса, если он случайно написан (например marketing:solutions...)
    const cleanKey = key.replace(/^marketing:/, '');
    if (!checkKeyExists(dict, cleanKey)) {
      missingKeys.push(cleanKey);
    }
  });

  if (missingKeys.length > 0) {
    console.log(`   ❌ НАЙДЕНЫ ОТСУТСТВУЮЩИЕ КЛЮЧИ В marketing.json (${missingKeys.length} шт):`);
    missingKeys.forEach(k => console.log(`      - "${k}"`));
    totalMissingKeys += missingKeys.length;
  } else {
    console.log(`   ✅ Все ${extractedKeys.size} ключей перевода существуют в словаре.`);
  }

  // 4. Эвристический поиск хардкода (текст между > и <, не являющийся JS-кодом)
  // Ищем текст, состоящий из букв (минимум 3 подряд), не обернутый в {}
  const hardcodeRegex = />\s*([A-Z][^<{}]{3,}[a-zA-Z.!?])\s*</g;
  const hardcoded = [];
  let hcMatch;
  
  // Очистим контент от комментариев перед проверкой хардкода
  const cleanContent = content.replace(/\{\/\*[\s\S]*?\*\/\}/g, '');
  
  while ((hcMatch = hardcodeRegex.exec(cleanContent)) !== null) {
    const text = hcMatch[1].trim();
    // Фильтруем ложные срабатывания (одиночные слова, спецсимволы и т.д.)
    if (text.length > 5 && text.includes(' ') && !text.includes('var(')) {
      hardcoded.push(text);
    }
  }

  if (hardcoded.length > 0) {
    console.log(`   ⚠️ ВОЗМОЖНЫЙ ХАРДКОД В JSX (${hardcoded.length} шт):`);
    // Выводим уникальные
    [...new Set(hardcoded)].forEach(t => console.log(`      - "${t.substring(0, 50)}${t.length > 50 ? '...' : ''}"`));
    totalHardcodedStrings += hardcoded.length;
  }
});

console.log('\n===============================================================');
console.log('🏆 ИТОГИ АУДИТА МНОГОЯЗЫЧНОСТИ');
console.log('===============================================================');
if (totalMissingKeys === 0 && totalHardcodedStrings === 0) {
  console.log('✨ ВЕЛИКОЛЕПНО! Все страницы имеют идеальную поддержку i18n.');
} else {
  console.log(`🔍 Отсутствующих ключей в словаре: ${totalMissingKeys}`);
  console.log(`🔍 Возможных строк хардкода: ${totalHardcodedStrings}`);
  console.log('\nПожалуйста, добавьте недостающие ключи в /public/locales/en/marketing.json');
}
console.log('===============================================================\n');

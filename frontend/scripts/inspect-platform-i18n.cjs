const fs = require('fs');
const path = require('path');

const ruJsonPath = path.join(__dirname, '../public/locales/ru/marketing.json');
const enJsonPath = path.join(__dirname, '../public/locales/en/marketing.json');

console.log('🔍 ТЕКСТЫ ДЛЯ PLATFORM В I18N:\n');

if (fs.existsSync(ruJsonPath)) {
  const ru = JSON.parse(fs.readFileSync(ruJsonPath, 'utf-8'));
  console.log('📌 platform.standards (RU):');
  console.log(JSON.stringify(ru.platform?.standards, null, 2));

  console.log('\n📌 platform.methodology (RU):');
  console.log(JSON.stringify(ru.platform?.methodology, null, 2));
} else {
  console.log('Файл ru/marketing.json не найден');
}

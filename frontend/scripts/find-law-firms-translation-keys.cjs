const fs = require('fs');
const path = require('path');

const localesPath = path.join(__dirname, '../public/locales/en/marketing.json');

if (fs.existsSync(localesPath)) {
  const json = JSON.parse(fs.readFileSync(localesPath, 'utf-8'));
  const lawFirms = json?.solutions?.lawFirms || {};

  console.log('\n===============================================================');
  console.log('🌐 КЛЮЧИ ЛОКАЛИЗАЦИИ ДЛЯ solutions.lawFirms:');
  console.log('===============================================================\n');

  console.log(JSON.stringify(lawFirms, null, 2).substring(0, 1500));

  console.log('\n===============================================================\n');
}

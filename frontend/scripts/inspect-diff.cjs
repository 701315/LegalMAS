const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

console.log('🔍 ПРОВЕРКА ИЗМЕНЕНИЙ В GIT:\n');

try {
  const status = execSync('git status --porcelain frontend/src/marketing/', { encoding: 'utf-8' });
  console.log('Измененные файлы:');
  console.log(status || 'Нет изменений');

  console.log('\n📄 СОДЕРЖИМОЕ CapabilitiesPage.tsx:\n');
  const capPath = path.join(__dirname, '../src/marketing/pages/CapabilitiesPage.tsx');
  if (fs.existsSync(capPath)) {
    console.log(fs.readFileSync(capPath, 'utf-8'));
  }
} catch (e) {
  console.error(e.message);
}

const fs = require('fs');
const path = require('path');

const appPath = path.join(__dirname, '../src/App.tsx');

if (fs.existsSync(appPath)) {
  const content = fs.readFileSync(appPath, 'utf-8');
  console.log('\n===============================================================');
  console.log('🔍 СТРОКИ РОУТЕРА В App.tsx ДЛЯ corporate-legal:');
  console.log('===============================================================\n');

  const lines = content.split('\n');
  lines.forEach((line, idx) => {
    if (line.includes('corporate-legal') || line.includes('CorporateLegal')) {
      console.log(`Строка ${idx + 1}: ${line.trim()}`);
    }
  });

  console.log('\n===============================================================\n');
}

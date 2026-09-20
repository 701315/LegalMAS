const fs = require('fs');
const path = require('path');

const appPath = path.join(__dirname, '../src/marketing/components/home/ApplicationSection/ApplicationSection.tsx');

if (fs.existsSync(appPath)) {
  const content = fs.readFileSync(appPath, 'utf-8');
  console.log('\n===============================================================');
  console.log('📄 СТРОКИ РЕНДЕРИНГА НАЗВАНИЙ В ApplicationSection.tsx');
  console.log('===============================================================\n');

  const lines = content.split('\n');
  lines.forEach((line, i) => {
    if (
      line.includes('title') ||
      line.includes('label') ||
      line.includes('font-semibold') ||
      line.includes('font-bold') ||
      line.includes('text-body-sm') ||
      line.includes('group-hover')
    ) {
      console.log(`[${i + 1}] ${line.trim()}`);
    }
  });

  console.log('\n===============================================================\n');
}

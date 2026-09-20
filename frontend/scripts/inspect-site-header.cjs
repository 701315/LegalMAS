const fs = require('fs');
const path = require('path');

const headerPath = path.join(__dirname, '../src/marketing/components/shared/SiteHeader.tsx');

if (fs.existsSync(headerPath)) {
  const content = fs.readFileSync(headerPath, 'utf-8');
  console.log('\n===============================================================');
  console.log('📄 СТРУКТУРА ВЫПАДАЮЩЕГО МЕНЮ В SiteHeader.tsx');
  console.log('===============================================================\n');

  // Найдем блоки JSX рендеринга выпадающего меню
  const lines = content.split('\n');
  lines.forEach((line, idx) => {
    if (
      line.includes('solutions') ||
      line.includes('dropdown') ||
      line.includes('byDirection') ||
      line.includes('byTeam') ||
      line.includes('font-medium') ||
      line.includes('text-')
    ) {
      if (line.includes('title') || line.includes('label') || line.includes('link') || line.includes('text-[#') || line.includes('text-gray') || line.includes('text-primary') || line.includes('hover:')) {
        console.log(`[${idx + 1}] ${line.trim()}`);
      }
    }
  });
}

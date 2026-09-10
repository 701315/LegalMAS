const fs = require('fs');
const path = require('path');

const SOLUTIONS_DIR = path.join(__dirname, '../src/marketing/pages/solutions');
const files = fs.readdirSync(SOLUTIONS_DIR).filter(f => f.endsWith('.tsx'));

console.log('\n===============================================================');
console.log('🔎 СТРУКТУРА СТРАНИЦ SOLUTIONS');
console.log('===============================================================\n');

files.forEach(file => {
  const filePath = path.join(SOLUTIONS_DIR, file);
  const content = fs.readFileSync(filePath, 'utf-8');

  console.log(`📄 Файл: ${file}`);

  // Проверяем Hero / H1
  const h1Match = content.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i);
  if (h1Match) {
    const fullTag = h1Match[0].replace(/\n/g, ' ').substring(0, 100);
    console.log(`   👑 Hero H1: ${fullTag}...`);
  } else {
    // Ищем первый H2
    const h2Match = content.match(/<h2[^>]*>([\s\S]*?)<\/h2>/i);
    if (h2Match) {
      const fullTag = h2Match[0].replace(/\n/g, ' ').substring(0, 100);
      console.log(`   👑 Первый заголовок (H2): ${fullTag}...`);
    }
  }

  // Проверяем наличие shared layout
  const imports = content.match(/import\s+.*from\s+["']([^"']+)["']/g) || [];
  const sharedLayout = imports.find(i => i.includes('Layout') || i.includes('Solution'));
  if (sharedLayout) {
    console.log(`   🧩 Импорт: ${sharedLayout}`);
  }

  console.log('');
});

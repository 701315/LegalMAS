const fs = require('fs');
const path = require('path');

const SOLUTIONS_DIR = path.join(__dirname, '../src/marketing/pages/solutions');
const files = fs.readdirSync(SOLUTIONS_DIR).filter(f => f.endsWith('.tsx'));

console.log('\n===============================================================');
console.log('🔍 ПОИСК ПОДЗАГОЛОВКОВ В КОДЕ СТРАНИЦ SOLUTIONS');
console.log('===============================================================\n');

const targets = ["Volume and Format", "Focus and Directions", "Data Systematization"];

files.forEach(file => {
  const filePath = path.join(SOLUTIONS_DIR, file);
  const content = fs.readFileSync(filePath, 'utf-8');
  
  let found = false;
  targets.forEach(target => {
    if (content.toLowerCase().includes(target.toLowerCase())) {
      console.log(`🎯 Найдено прямое совпадение "${target}" в файле: ${file}`);
      found = true;
    }
  });

  // Также проверим ключи локализации в JSX (например, card.title или pillars)
  if (!found) {
    const renderBlocks = content.match(/const\s+\w+Section[\s\S]*?return\s*\([\s\S]*?\)/g) || [];
    renderBlocks.forEach(block => {
      if (block.includes('Volume') || block.includes('Focus') || block.includes('Data') || block.includes('pillars') || block.includes('ThreePillars') || block.includes('ThreeBlocks')) {
        console.log(`💡 Подозрение на блок в файле ${file}:`);
        const lines = block.split('\n').slice(0, 15).join('\n');
        console.log(lines);
        console.log('--------------------------------------------------');
      }
    });
  }
});

// Проверим также в файле перевода marketing.json
const localesPath = path.join(__dirname, '../public/locales/en/marketing.json');
if (fs.existsSync(localesPath)) {
  const locales = JSON.parse(fs.readFileSync(localesPath, 'utf-8'));
  console.log('\n🌐 ПОИСК В АНГЛИЙСКОЙ ЛОКАЛИЗАЦИИ (marketing.json):');
  
  function searchObj(obj, pathStr = '') {
    for (const key in obj) {
      const currentPath = pathStr ? `${pathStr}.${key}` : key;
      if (typeof obj[key] === 'string') {
        targets.forEach(t => {
          if (obj[key].toLowerCase().includes(t.toLowerCase())) {
            console.log(`   • Ключ: "${currentPath}" => "${obj[key]}"`);
          }
        });
      } else if (typeof obj[key] === 'object' && obj[key] !== null) {
        searchObj(obj[key], currentPath);
      }
    }
  }
  searchObj(locales);
}
console.log('\n===============================================================\n');

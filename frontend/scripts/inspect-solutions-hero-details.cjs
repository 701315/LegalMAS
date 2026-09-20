const fs = require('fs');
const path = require('path');

const SOLUTIONS_PAGE_DIR = path.join(__dirname, '../src/marketing/pages/solutions');
const COMPONENTS_DIR = path.join(__dirname, '../src/marketing/components');

console.log('\n===============================================================');
console.log('🔍 ДЕТАЛЬНЫЙ АНАЛИЗ СТРАНИЦ И HERO-БЛОКОВ SOLUTIONS');
console.log('===============================================================\n');

// Проверяем наличие папки components/solutions
const solCompDir = path.join(COMPONENTS_DIR, 'solutions');
if (fs.existsSync(solCompDir)) {
  console.log(`📁 Найдена папка компонентов: src/marketing/components/solutions/`);
  fs.readdirSync(solCompDir).forEach(f => console.log(`   • ${f}`));
  console.log('');
}

const files = fs.readdirSync(SOLUTIONS_PAGE_DIR).filter(f => f.endsWith('.tsx'));

files.forEach(file => {
  const filePath = path.join(SOLUTIONS_PAGE_DIR, file);
  const content = fs.readFileSync(filePath, 'utf-8');

  console.log(`📄 Файл: src/marketing/pages/solutions/${file}`);

  // Ищем все импорты компонентов Hero или Layout
  const importedComponents = content.match(/import\s+([A-Z]\w+)\s+from/g) || [];
  if (importedComponents.length > 0) {
    console.log(`   🧩 Компоненты: ${importedComponents.map(c => c.replace(/import\s+|from/g, '').trim()).join(', ')}`);
  }

  // Проверяем первые 50 строк JSX для понимания структуры Hero
  const returnMatch = content.match(/return\s*\(\s*([\s\S]*?)(?:<section|<\/div>)/);
  if (returnMatch) {
    const snippet = returnMatch[0].replace(/\n\s*/g, ' ').substring(0, 150);
    console.log(`   🚀 Начало рендера: ${snippet}...`);
  }

  console.log('');
});

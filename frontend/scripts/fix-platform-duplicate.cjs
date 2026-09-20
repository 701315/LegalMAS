const fs = require('fs');
const path = require('path');

const PAGES_DIR = path.join(__dirname, '../src/marketing/pages');
const PLATFORM_DIR = path.join(__dirname, '../src/marketing/components/platform');

function getAllFiles(dir) {
  let results = [];
  if (!fs.existsSync(dir)) return results;
  const list = fs.readdirSync(dir);
  for (const file of list) {
    const filePath = path.join(dir, file);
    const stat = fs.statSync(filePath);
    if (stat.isDirectory()) {
      results.push(...getAllFiles(filePath));
    } else if (file.endsWith('.tsx') || file.endsWith('.ts')) {
      results.push(filePath);
    }
  }
  return results;
}

const allFiles = [...getAllFiles(PAGES_DIR), ...getAllFiles(PLATFORM_DIR)];

console.log('\n🔍 ПОИСК И УДАЛЕНИЕ ДУБЛИКАТА СЕКЦИИ METHODOLOGY...\n');

allFiles.forEach(file => {
  let content = fs.readFileSync(file, 'utf-8');
  const rel = path.relative(path.join(__dirname, '../src/marketing'), file);

  // Считаем количество вызовов PlatformMethodologySection
  const matches = content.match(/<PlatformMethodologySection\s*[^>]*\/>/g) || [];
  
  if (matches.length > 1) {
    console.log(`⚠️ Найдено ${matches.length} дубликата <PlatformMethodologySection /> в файле: src/marketing/${rel}`);
    
    // Оставляем только ПЕРВЫЙ вызов, удаляя последующие дубликаты
    let firstFound = false;
    content = content.replace(/<PlatformMethodologySection\s*[^>]*\/>/g, (match) => {
      if (!firstFound) {
        firstFound = true;
        return match;
      }
      return ''; // Удаляем дубликат
    });

    fs.writeFileSync(file, content, 'utf-8');
    console.log(`  ✅ Дубликат успешно удалён из src/marketing/${rel}`);
  }
});


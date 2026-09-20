const fs = require('fs');
const path = require('path');

const SRC_DIR = path.join(__dirname, '../src');

function searchFiles(dir) {
  let results = [];
  const list = fs.readdirSync(dir);
  for (const file of list) {
    const filePath = path.join(dir, file);
    const stat = fs.statSync(filePath);
    if (stat.isDirectory()) {
      results.push(...searchFiles(filePath));
    } else if (file.endsWith('.tsx') || file.endsWith('.ts')) {
      const content = fs.readFileSync(filePath, 'utf-8');
      if (
        content.includes('threeBlocks') ||
        content.includes('Volume and Format') ||
        content.includes('maDueDiligence') ||
        content.includes('briefBlocks') ||
        content.includes('ThreeBlocksSection')
      ) {
        results.push({ filePath, content });
      }
    }
  }
  return results;
}

console.log('\n===============================================================');
console.log('🔍 СИСТЕМНЫЙ ПОИСК ВСЕХ ФАЙЛОВ, СВЯЗАННЫХ С MA-DUE-DILIGENCE / THREEBLOCKS');
console.log('===============================================================\n');

const matches = searchFiles(SRC_DIR);

matches.forEach(m => {
  const rel = path.relative(path.join(__dirname, '..'), m.filePath);
  console.log(`📄 Найден файл: ${rel}`);

  // Выведем все места в файле, где рендерятся названия трех блоков
  const lines = m.content.split('\n');
  lines.forEach((line, idx) => {
    if (
      line.includes('title') ||
      line.includes('threeBlocks') ||
      line.includes('briefBlocks') ||
      line.includes('ThreeBlocks') ||
      line.includes('Volume')
    ) {
      if (line.includes('item.') || line.includes('block.') || line.includes('h2') || line.includes('h3') || line.includes('strong') || line.includes('font-serif')) {
        console.log(`   Строка ${idx + 1}: ${line.trim()}`);
      }
    }
  });
  console.log('');
});

console.log('===============================================================\n');

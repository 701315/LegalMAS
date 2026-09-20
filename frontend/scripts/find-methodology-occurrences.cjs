const fs = require('fs');
const path = require('path');

const MARKETING_DIR = path.join(__dirname, '../src/marketing');

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

const files = getAllFiles(MARKETING_DIR);

console.log('\n🔍 ИЩЕМ ВСЕ УПОМИНАНИЯ МЕТОДОЛОГИИ (METHODOLOGY)...\n');

files.forEach(file => {
  const content = fs.readFileSync(file, 'utf-8');
  const rel = path.relative(MARKETING_DIR, file);

  if (content.includes('Methodology') || content.includes('methodology')) {
    console.log(`📄 src/marketing/${rel}`);
    
    // Ищем компоненты или импорты
    const lines = content.split('\n');
    lines.forEach((line, idx) => {
      if (line.includes('Methodology') || line.includes('methodology')) {
        console.log(`   L${idx + 1}: ${line.trim()}`);
      }
    });
    console.log('');
  }
});

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
let modifiedCount = 0;

files.forEach(file => {
  let content = fs.readFileSync(file, 'utf-8');
  const original = content;

  // Удаляем оставшийся несистемный tracking-[-0.005em]
  content = content.replace(/\s*tracking-\[-0\.005em\]/g, '');

  // Очищаем пробелы
  content = content.replace(/className=["']([^"']+)["']/g, (match, classNames) => {
    const cleaned = classNames.replace(/\s+/g, ' ').trim();
    return `className="${cleaned}"`;
  });

  if (content !== original) {
    fs.writeFileSync(file, content, 'utf-8');
    modifiedCount++;
  }
});

console.log(`\n✨ Зачищено файлов: ${modifiedCount}`);

// Обновляем скрипт проверки, чтобы он распознавал text-meta и text-eyebrow
const findHeadingsPath = path.join(__dirname, '../find-headings.cjs');
let findHeadingsCode = fs.readFileSync(findHeadingsPath, 'utf-8');
findHeadingsCode = findHeadingsCode.replace(
  "!classes.includes('text-display')",
  "!classes.includes('text-display') && !classes.includes('text-meta') && !classes.includes('text-eyebrow')"
);
fs.writeFileSync(findHeadingsPath, findHeadingsCode, 'utf-8');

const fs = require('fs');
const path = require('path');

const SRC_DIR = path.join(__dirname, '../src');

console.log('\n===============================================================');
console.log('🔎 СТРОГИЙ АНАЛИЗ ПРИЧИН РАСШИРЕНИЯ ЭКРАНА (OVERFLOW SCANNER)');
console.log('===============================================================\n');

function scanFile(filePath) {
  const content = fs.readFileSync(filePath, 'utf-8');
  const lines = content.split('\n');
  const relPath = path.relative(SRC_DIR, filePath);
  const issues = [];

  lines.forEach((line, idx) => {
    const lineNum = idx + 1;

    // 1. Поиск w-screen
    if (line.includes('w-screen')) {
      issues.push({ lineNum, type: 'w-screen (вызывает сдвиг экрана)', code: line.trim() });
    }

    // 2. Поиск фиксированных min-w или w больше 300px
    const pxMatch = line.match(/(?:min-w|w)-\[(\d+)px\]/);
    if (pxMatch && parseInt(pxMatch[1], 10) > 300) {
      issues.push({ lineNum, type: `Фиксированная ширина ${pxMatch[0]} > 300px`, code: line.trim() });
    }

    // 3. Поиск style={{ minWidth: ... }} или style={{ width: ... }}
    const stylePxMatch = line.match(/style=\{\{[\s\S]*?(?:minWidth|width):\s*["']?(\d+)px["']?[\s\S]*?\}\}/);
    if (stylePxMatch && parseInt(stylePxMatch[1], 10) > 300) {
      issues.push({ lineNum, type: `Инлайн стиль ширины ${stylePxMatch[1]}px > 300px`, code: line.trim() });
    }

    // 4. Поиск отрицательных отступов -mx-
    if (line.match(/-mx-(8|10|12|16|20|24)/)) {
      issues.push({ lineNum, type: 'Большой отрицательный маржин (-mx-)', code: line.trim() });
    }

    // 5. Поиск абсолютных элементов вылетающих вправо
    if (line.match(/absolute[\s\S]*?-right-(8|10|12|16|20|24|32|40|64)/)) {
      issues.push({ lineNum, type: 'Абсолютный элемент вылетает за правый край', code: line.trim() });
    }
  });

  if (issues.length > 0) {
    console.log(`📄 Файл: src/${relPath}`);
    issues.forEach(iss => {
      console.log(`   • Строка ${iss.lineNum} [${iss.type}]:`);
      console.log(`     ${iss.code.substring(0, 120)}`);
    });
    console.log('');
  }
}

function traverse(dir) {
  const list = fs.readdirSync(dir);
  for (const item of list) {
    const fullPath = path.join(dir, item);
    const stat = fs.statSync(fullPath);
    if (stat.isDirectory()) {
      traverse(fullPath);
    } else if (item.endsWith('.tsx') || item.endsWith('.ts') || item.endsWith('.css')) {
      scanFile(fullPath);
    }
  }
}

traverse(SRC_DIR);

console.log('===============================================================\n');

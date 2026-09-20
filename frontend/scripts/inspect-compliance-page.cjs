const fs = require('fs');
const path = require('path');

const compPath = path.join(__dirname, '../src/marketing/pages/solutions/CompliancePage.tsx');

if (fs.existsSync(compPath)) {
  const content = fs.readFileSync(compPath, 'utf-8');
  console.log('\n===============================================================');
  console.log('📄 СТРУКТУРА ФАЙЛА CompliancePage.tsx');
  console.log('===============================================================\n');

  // Выведем все функции секций
  const functions = content.match(/function\s+\w+Section[\s\S]*?(?=\nfunction|\nexport|$)/g) || [];
  functions.forEach(fn => {
    const fnName = fn.match(/function\s+(\w+)/)?.[1] || '';
    console.log(`📌 Функция: ${fnName}`);
    const lines = fn.split('\n');
    lines.forEach((line, idx) => {
      if (line.includes('title') || line.includes('h2') || line.includes('h3') || line.includes('p className') || line.includes('item') || line.includes('block')) {
        console.log(`   [${idx + 1}] ${line.trim()}`);
      }
    });
    console.log('--------------------------------------------------');
  });
}

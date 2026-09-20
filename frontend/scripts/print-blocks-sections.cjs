const fs = require('fs');
const path = require('path');

const targetFiles = [
  'src/marketing/pages/solutions/MaDueDiligencePage.tsx',
  'src/marketing/pages/solutions/ContractReviewPage.tsx',
  'src/marketing/pages/solutions/InternalAuditPage.tsx'
];

targetFiles.forEach(rel => {
  const filePath = path.join(__dirname, '..', rel);
  if (!fs.existsSync(filePath)) return;
  const content = fs.readFileSync(filePath, 'utf-8');

  console.log(`\n==============================================================`);
  console.log(`📂 ФАЙЛ: ${rel}`);
  console.log(`==============================================================`);

  const lines = content.split('\n');
  let startIdx = -1;
  let endIdx = -1;

  lines.forEach((line, i) => {
    if (line.includes('function ThreeBlocksSection') || line.includes('function ThreePillarsSection')) {
      startIdx = i;
    }
    if (startIdx !== -1 && endIdx === -1 && line.trim() === '}') {
      // Ищем закрывающую скобку функции (простой способ для вывода блока)
      if (i > startIdx + 15) {
        endIdx = i;
      }
    }
  });

  if (startIdx !== -1) {
    console.log(lines.slice(startIdx, (endIdx !== -1 ? endIdx + 1 : startIdx + 60)).join('\n'));
  } else {
    console.log('Не удалось найти функцию');
  }
});

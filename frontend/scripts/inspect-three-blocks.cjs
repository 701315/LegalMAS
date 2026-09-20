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

  // Ищем ThreeBlocksSection или аналогичные секции
  const match = content.match(/function\s+(?:ThreeBlocksSection|ThreePillarsSection|BriefBlocksSection)[\s\S]*?(?:return\s*\([\s\S]*?<\/section>\s*\})/);
  if (match) {
    console.log(match[0]);
  } else {
    console.log('Секция не найдена через regex');
  }
});

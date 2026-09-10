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

  // Ищем строки, где упоминается threeBlocks, threePillars или аналогичные ключи локализации
  const lines = content.split('\n');
  lines.forEach((line, index) => {
    if (line.includes('threeBlocks') || line.includes('threePillars') || line.includes('.title') || line.includes('ThreeBlocks') || line.includes('ThreePillars')) {
      console.log(`Строка ${index + 1}: ${line.trim()}`);
    }
  });

  // Найдем также все h3 или h2 теги в файле
  console.log('\n🏷️  Все теги h2/h3 в этом файле:');
  const headings = content.match(/<h[23][^>]*>[\s\S]*?<\/h[23]>/gi) || [];
  headings.forEach(h => console.log(`   ${h.trim()}`));
});

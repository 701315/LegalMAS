const fs = require('fs');
const path = require('path');

const SOLUTIONS_DIR = path.join(__dirname, '../src/marketing/pages/solutions');
const targetFiles = [
  'AuditCompliancePage.tsx',
  'CompliancePage.tsx',
  'ContractReviewPage.tsx',
  'CorporateLegalPage.tsx',
  'InternalAuditPage.tsx',
  'MaDueDiligencePage.tsx'
];

console.log('\n===============================================================');
console.log('🔍 КОД HERO-СЕКЦИЙ БЕЗ <h1>');
console.log('===============================================================\n');

targetFiles.forEach(file => {
  const filePath = path.join(SOLUTIONS_DIR, file);
  if (!fs.existsSync(filePath)) return;
  const content = fs.readFileSync(filePath, 'utf-8');

  console.log(`📄 Файл: ${file}`);
  
  // Находим функцию HeroSection
  const heroMatch = content.match(/function\s+HeroSection[\s\S]*?(?:return\s*\([\s\S]*?<\/section>)/);
  if (heroMatch) {
    // Выведем первые 40 строк функции HeroSection
    const lines = heroMatch[0].split('\n').slice(0, 45).join('\n');
    console.log(lines);
  } else {
    console.log('   HeroSection не найден');
  }
  console.log('\n---------------------------------------------------------------\n');
});

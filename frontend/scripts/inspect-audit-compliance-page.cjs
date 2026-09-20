const fs = require('fs');
const path = require('path');

const acPath = path.join(__dirname, '../src/marketing/pages/solutions/AuditCompliancePage.tsx');

if (fs.existsSync(acPath)) {
  const content = fs.readFileSync(acPath, 'utf-8');
  console.log('\n===============================================================');
  console.log('🔎 СТРУКТУРА ФАЙЛА AuditCompliancePage.tsx');
  console.log('===============================================================\n');

  const fns = content.match(/function\s+\w+Section[\s\S]*?(?=\nfunction|\nexport|$)/g) || [];
  fns.forEach(fn => {
    const fnName = fn.match(/function\s+(\w+)/)?.[1] || '';
    console.log(`📌 Функция секции: ${fnName}`);
  });
}

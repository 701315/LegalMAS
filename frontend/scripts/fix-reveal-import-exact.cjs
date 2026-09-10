const fs = require('fs');
const path = require('path');

const corpPath = path.join(__dirname, '../src/marketing/pages/solutions/CorporateLegalPage.tsx');
const compPath = path.join(__dirname, '../src/marketing/pages/solutions/CompliancePage.tsx');

let correctRevealImport = '';
if (fs.existsSync(compPath)) {
  const compContent = fs.readFileSync(compPath, 'utf-8');
  const match = compContent.match(/import\s+.*Reveal.*from\s+["']([^"']+)["']/);
  if (match) {
    correctRevealImport = match[0];
  }
}

if (fs.existsSync(corpPath)) {
  let content = fs.readFileSync(corpPath, 'utf-8');

  if (correctRevealImport) {
    // Заменяем имеющийся импорт Reveal на заведомо рабочий из CompliancePage
    content = content.replace(/import\s+.*Reveal.*from\s+["'][^"']+["'];?/, correctRevealImport);
  } else {
    // Если в CompliancePage Reveal не импортируется, убираем Reveal из JSX
    content = content.replace(/import\s+.*Reveal.*from\s+["'][^"']+["'];?\n?/, '');
    content = content.replace(/<\/?RevealItem[^>]*>/g, '');
    content = content.replace(/<\/?Reveal[^>]*>/g, '');
  }

  fs.writeFileSync(corpPath, content, 'utf-8');
  console.log('✅ CorporateLegalPage.tsx: Импорт Reveal успешно исправлен!');
}

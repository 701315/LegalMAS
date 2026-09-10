const fs = require('fs');
const path = require('path');

const compPath = path.join(__dirname, '../src/marketing/pages/solutions/CompliancePage.tsx');

if (fs.existsSync(compPath)) {
  let content = fs.readFileSync(compPath, 'utf-8');

  // Делаем заголовок h1 и его первую часть чисто белыми (!text-white)
  content = content.replace(
    /className="mt-12 font-serif text-display text-\[var\(--text-inverse\)\] whitespace-pre-line"/g,
    'className="mt-12 font-serif text-display !text-white whitespace-pre-line"'
  );

  content = content.replace(
    /\{t\("solutions\.compliance\.hero\.titlePart1"\)\}/g,
    '<span className="!text-white">{t("solutions.compliance.hero.titlePart1")}</span>'
  );

  fs.writeFileSync(compPath, content, 'utf-8');
  console.log('✅ CompliancePage.tsx: Заголовок "A unified review standard -" сделан чисто белым!');
}

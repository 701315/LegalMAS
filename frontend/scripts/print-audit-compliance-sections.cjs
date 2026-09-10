const fs = require('fs');
const path = require('path');

const acPath = path.join(__dirname, '../src/marketing/pages/solutions/AuditCompliancePage.tsx');

if (fs.existsSync(acPath)) {
  const content = fs.readFileSync(acPath, 'utf-8');

  console.log('\n===============================================================');
  console.log('📄 СЕКЦИИ В AuditCompliancePage.tsx');
  console.log('===============================================================\n');

  const hero = content.match(/function HeroSection[\s\S]*?(?=\nfunction|\nexport|$)/)?.[0];
  console.log('--- HeroSection ---');
  console.log(hero?.split('\n').slice(0, 50).join('\n'));

  console.log('\n--------------------------------------------------\n');

  const intro = content.match(/function AuditRoutinesIntroSection[\s\S]*?(?=\nfunction|\nexport|$)/)?.[0];
  console.log('--- AuditRoutinesIntroSection ---');
  console.log(intro?.split('\n').slice(0, 40).join('\n'));

  console.log('\n--------------------------------------------------\n');

  const visual = content.match(/function VisualCardsSection[\s\S]*?(?=\nfunction|\nexport|$)/)?.[0];
  console.log('--- VisualCardsSection ---');
  console.log(visual?.split('\n').slice(0, 40).join('\n'));

  console.log('\n===============================================================\n');
}

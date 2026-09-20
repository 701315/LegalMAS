const fs = require('fs');
const path = require('path');

const corpPath = path.join(__dirname, '../src/marketing/pages/solutions/CorporateLegalPage.tsx');

if (fs.existsSync(corpPath)) {
  const content = fs.readFileSync(corpPath, 'utf-8');

  console.log('\n===============================================================');
  console.log('🔍 ПРОВЕРКА ТЕГОВ В CorporateLegalPage.tsx');
  console.log('===============================================================\n');

  const h2Matches = content.match(/<h2[^>]*>[\s\S]*?<\/h2>/gi) || [];
  const h3Matches = content.match(/<h3[^>]*>[\s\S]*?<\/h3>/gi) || [];

  console.log(`📌 Найдено тегов <h2> (${h2Matches.length} шт):`);
  h2Matches.forEach(h => console.log(`   ${h.replace(/\s+/g, ' ').substring(0, 80)}`));

  console.log(`\n📌 Найдено тегов <h3> (${h3Matches.length} шт):`);
  h3Matches.forEach(h => console.log(`   ${h.replace(/\s+/g, ' ').substring(0, 80)}`));

  console.log('\n===============================================================\n');
}

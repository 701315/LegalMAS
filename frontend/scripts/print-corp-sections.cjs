const fs = require('fs');
const path = require('path');

const corpPath = path.join(__dirname, '../src/marketing/pages/solutions/CorporateLegalPage.tsx');

if (fs.existsSync(corpPath)) {
  const content = fs.readFileSync(corpPath, 'utf-8');

  console.log('\n===============================================================');
  console.log('📄 ВЕРСТКА PressureSection И OutcomesSection');
  console.log('===============================================================\n');

  const pressure = content.match(/function PressureSection\(\) \{[\s\S]*?\n\}/)?.[0];
  console.log('--- PressureSection ---');
  console.log(pressure);

  const outcomes = content.match(/function OutcomesSection\(\) \{[\s\S]*?\n\}/)?.[0];
  console.log('\n--- OutcomesSection ---');
  console.log(outcomes);

  console.log('\n===============================================================\n');
}

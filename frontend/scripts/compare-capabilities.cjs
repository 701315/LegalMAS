const fs = require('fs');
const path = require('path');

const compPath = path.join(__dirname, '../src/marketing/pages/solutions/CompliancePage.tsx');
const iaPath = path.join(__dirname, '../src/marketing/pages/solutions/InternalAuditPage.tsx');

console.log('\n===============================================================');
console.log('🔍 СРАВНЕНИЕ CapabilitiesSection В CompliancePage И InternalAuditPage');
console.log('===============================================================\n');

if (fs.existsSync(compPath)) {
  const compContent = fs.readFileSync(compPath, 'utf-8');
  const compCap = compContent.match(/function CapabilitiesSection\(\) \{[\s\S]*?\n\}/)?.[0];
  console.log('📄 CompliancePage.tsx (CapabilitiesSection):');
  console.log(compCap);
}

console.log('\n---------------------------------------------------------------\n');

if (fs.existsSync(iaPath)) {
  const iaContent = fs.readFileSync(iaPath, 'utf-8');
  const iaCap = iaContent.match(/function CapabilitiesSection\(\) \{[\s\S]*?\n\}/)?.[0];
  console.log('📄 InternalAuditPage.tsx (CapabilitiesSection):');
  console.log(iaCap);
}

console.log('\n===============================================================\n');

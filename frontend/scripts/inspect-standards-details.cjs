const fs = require('fs');
const path = require('path');

const sectionPath = path.join(__dirname, '../src/marketing/components/platform/PlatformStandardsSection.tsx');
const diagramPath = path.join(__dirname, '../src/marketing/components/platform/diagrams/StandardsDiagram.tsx');

console.log('📄 === PlatformStandardsSection.tsx ===\n');
if (fs.existsSync(sectionPath)) console.log(fs.readFileSync(sectionPath, 'utf-8'));

console.log('\n📄 === StandardsDiagram.tsx ===\n');
if (fs.existsSync(diagramPath)) console.log(fs.readFileSync(diagramPath, 'utf-8'));

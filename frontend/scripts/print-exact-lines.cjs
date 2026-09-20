const fs = require('fs');
const path = require('path');

const filePath = path.join(__dirname, '../src/marketing/pages/solutions/MaDueDiligencePage.tsx');
const content = fs.readFileSync(filePath, 'utf-8');
const lines = content.split('\n');

console.log('\n===============================================================');
console.log('📄 ТОЧНЫЕ СТРОКИ 110-155 В MaDueDiligencePage.tsx:');
console.log('===============================================================\n');

for (let i = 105; i < Math.min(lines.length, 155); i++) {
  console.log(`${i + 1}: ${lines[i]}`);
}

console.log('\n===============================================================\n');

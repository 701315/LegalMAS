const fs = require('fs');
const path = require('path');

const SOLUTIONS_DIR = path.join(__dirname, '../src/marketing/pages/solutions');
const files = fs.readdirSync(SOLUTIONS_DIR).filter(f => f.endsWith('.tsx'));

console.log('\n===============================================================');
console.log('🛠️ ИСПРАВЛЕНИЕ ПРОПОВ ContactModal (isOpen -> open)');
console.log('===============================================================\n');

files.forEach(file => {
  const filePath = path.join(SOLUTIONS_DIR, file);
  let content = fs.readFileSync(filePath, 'utf-8');

  if (content.includes('isOpen={contactModalOpen}')) {
    content = content.replace(/isOpen=\{contactModalOpen\}/g, 'open={contactModalOpen}');
    fs.writeFileSync(filePath, content, 'utf-8');
    console.log(`✅ ${file}: проп успешно изменён на open={contactModalOpen}`);
  }
});

console.log('\n===============================================================\n');

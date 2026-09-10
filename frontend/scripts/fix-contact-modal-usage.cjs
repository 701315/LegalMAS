const fs = require('fs');
const path = require('path');

// 1. Смотрим интерфейс ContactModal
const modalPath = path.join(__dirname, '../src/marketing/components/home/ContactModal.tsx');
let modalContent = '';
if (fs.existsSync(modalPath)) {
  modalContent = fs.readFileSync(modalPath, 'utf-8');
  console.log('\n===============================================================');
  console.log('📄 ИНТЕРФЕЙС ContactModal:');
  console.log('===============================================================\n');
  const iface = modalContent.match(/(?:interface|type)\s+ContactModalProps[\s\S]*?\{[\s\S]*?\}/)?.[0];
  console.log(iface || 'Interface not found via regex');
  
  // Также первые 80 строк
  console.log('\n--- Первые 80 строк ContactModal.tsx ---\n');
  console.log(modalContent.split('\n').slice(0, 80).join('\n'));
}

// 2. Смотрим как ContactModal используется на рабочей странице
const workingPages = [
  'src/marketing/pages/solutions/CompliancePage.tsx',
  'src/marketing/pages/solutions/LawFirmsPage.tsx',
  'src/marketing/pages/solutions/MaDueDiligencePage.tsx',
  'src/marketing/components/home/PremiumFinalCtaSection.tsx',
];

console.log('\n===============================================================');
console.log('📄 ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ ContactModal:');
console.log('===============================================================\n');

workingPages.forEach(rel => {
  const p = path.join(__dirname, '..', rel);
  if (!fs.existsSync(p)) return;
  const c = fs.readFileSync(p, 'utf-8');
  const lines = c.split('\n');
  lines.forEach((line, i) => {
    if (line.includes('ContactModal') || line.includes('contactModal') || line.includes('openContactModal') || line.includes('useContactModal')) {
      console.log(`${rel}:${i + 1}: ${line.trim()}`);
    }
  });
  console.log('');
});

const fs = require('fs');
const path = require('path');

const dictPath = path.join(__dirname, '../public/locales/en/marketing.json');
const cpPath = path.join(__dirname, '../src/marketing/pages/solutions/CounterpartiesPage.tsx');
const rePath = path.join(__dirname, '../src/marketing/pages/solutions/RealEstatePage.tsx');

console.log('\n===============================================================');
console.log('🔍 БЕЗОПАСНЫЙ АУДИТ ПЕРЕД I18N-РЕФАКТОРИНГОМ');
console.log('===============================================================\n');

// 1. Проверка словаря marketing.json
if (fs.existsSync(dictPath)) {
  const dict = JSON.parse(fs.readFileSync(dictPath, 'utf-8'));
  const cpKeys = dict.solutions?.counterparties ? Object.keys(dict.solutions.counterparties) : [];
  const reKeys = dict.solutions?.realEstate ? Object.keys(dict.solutions.realEstate) : [];
  
  console.log('📖 1. СОСТОЯНИЕ СЛОВАРЯ (marketing.json):');
  console.log(`   • Ключи counterparties: ${cpKeys.length > 0 ? cpKeys.join(', ') : 'ОТСУТСТВУЮТ'}`);
  console.log(`   • Ключи realEstate: ${reKeys.length > 0 ? reKeys.join(', ') : 'ОТСУТСТВУЮТ'}`);
}

console.log('\n---------------------------------------------------------------\n');

// 2. Проверка CounterpartiesPage
if (fs.existsSync(cpPath)) {
  const content = fs.readFileSync(cpPath, 'utf-8');
  console.log('📄 2. СОСТОЯНИЕ CounterpartiesPage.tsx:');
  
  // Проверяем как вызывается ContactModal (чтобы не вернуть баг с isOpen/open)
  const hasContactModalHook = content.includes('useContactModal');
  const hasOpenProp = content.includes('open={contactModalOpen}') || content.includes('onDemo={openContactModal}');
  console.log(`   • Использование useContactModal: ${hasContactModalHook ? '✅ Да' : '❌ Нет (возможна ошибка TypeScript)'}`);
  console.log(`   • Наличие хардкода: ${content.includes('Operational Risks & Blind Spots') ? '⚠️ Есть хардкод' : '✅ Локализовано'}`);
}

console.log('\n---------------------------------------------------------------\n');

// 3. Проверка RealEstatePage
if (fs.existsSync(rePath)) {
  const content = fs.readFileSync(rePath, 'utf-8');
  console.log('📄 3. СОСТОЯНИЕ RealEstatePage.tsx:');
  
  const hasContactModalHook = content.includes('useContactModal');
  console.log(`   • Использование useContactModal: ${hasContactModalHook ? '✅ Да' : '❌ Нет (возможна ошибка TypeScript)'}`);
  console.log(`   • Наличие хардкода: ${content.includes('Property Risk Exposure') ? '⚠️ Есть хардкод' : '✅ Локализовано'}`);
}

console.log('\n===============================================================\n');

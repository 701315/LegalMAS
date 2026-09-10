const fs = require('fs');
const path = require('path');

const HOME_DIR = path.join(__dirname, '../src/marketing/components/home');

console.log('\n🚀 ПРИМЕНЕНИЕ ВАРИАНТА А (КРУПНЫЕ АКЦЕНТНЫЕ ЗАГОЛОВКИ HA HOME)...\n');

// 1. KnowledgeGrowthSection -> text-h1
const knowledgePath = path.join(HOME_DIR, 'KnowledgeGrowthSection/index.tsx');
if (fs.existsSync(knowledgePath)) {
  let content = fs.readFileSync(knowledgePath, 'utf-8');
  content = content.replace(/className=["']text-h2 !mt-2/g, 'className="text-h1 !mt-2 max-w-3xl');
  fs.writeFileSync(knowledgePath, content, 'utf-8');
  console.log('  ✅ KnowledgeGrowthSection: заголовок обновлен до text-h1 (52px)');
}

// 2. ApplicationSection -> text-h1
const appPath = path.join(HOME_DIR, 'ApplicationSection/ApplicationSection.tsx');
if (fs.existsSync(appPath)) {
  let content = fs.readFileSync(appPath, 'utf-8');
  content = content.replace(/className=["']text-h2 text-white["']/g, 'className="text-h1 text-white max-w-4xl mx-auto"');
  fs.writeFileSync(appPath, content, 'utf-8');
  console.log('  ✅ ApplicationSection: заголовок обновлен до text-h1 (52px)');
}

// 3. SecurityFoundationSection -> text-h1
const secPath = path.join(HOME_DIR, 'SecurityFoundationSection/index.tsx');
if (fs.existsSync(secPath)) {
  let content = fs.readFileSync(secPath, 'utf-8');
  content = content.replace(/className=["']text-h2 !mt-2/g, 'className="text-h1 !mt-2 max-w-3xl');
  fs.writeFileSync(secPath, content, 'utf-8');
  console.log('  ✅ SecurityFoundationSection: заголовок обновлен до text-h1 (52px)');
}

// 4. PremiumFinalCtaSection -> text-display
const ctaPath = path.join(HOME_DIR, 'PremiumFinalCtaSection.tsx');
if (fs.existsSync(ctaPath)) {
  let content = fs.readFileSync(ctaPath, 'utf-8');
  content = content.replace(/className=["']mt-6 text-h1["']/g, 'className="mt-6 text-display max-w-4xl mx-auto"');
  fs.writeFileSync(ctaPath, content, 'utf-8');
  console.log('  ✅ PremiumFinalCtaSection: заголовок обновлен до text-display (67px)');
}

console.log('\n🎉 Все ключевые заголовки главной страницы успешно обновлены!\n');

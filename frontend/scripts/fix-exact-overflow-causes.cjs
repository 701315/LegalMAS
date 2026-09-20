const fs = require('fs');
const path = require('path');

console.log('\n===============================================================');
console.log('🛠️ ТОЧНОЕ ИСПРАВЛЕНИЕ ВСЕХ ПРИЧИН ГОРИЗОНТАЛЬНОГО СКРОЛЛА');
console.log('===============================================================\n');

// 1. Исправление SiteHeader.tsx (Строка 293: w-[1140px])
const headerPath = path.join(__dirname, '../src/marketing/components/shared/SiteHeader.tsx');
if (fs.existsSync(headerPath)) {
  let content = fs.readFileSync(headerPath, 'utf-8');
  content = content.replace(
    /className=["']absolute left-0 top-full mt-5 w-\[1140px\]/g,
    'className="absolute left-0 top-full mt-5 hidden lg:block w-[1140px] max-w-[calc(100vw-2rem)]'
  );
  fs.writeFileSync(headerPath, content, 'utf-8');
  console.log('✅ SiteHeader.tsx: Мегаменю w-[1140px] теперь сжато для мобильных!');
}

// 2. Исправление AboutHeroSection.tsx (Строка 25: 800px круги)
const aboutHeroPath = path.join(__dirname, '../src/marketing/components/about/AboutHeroSection.tsx');
if (fs.existsSync(aboutHeroPath)) {
  let content = fs.readFileSync(aboutHeroPath, 'utf-8');
  content = content.replace(/<section([^>]*)className=["']([^"']*)["']/g, (m, p1, p2) => {
    if (!p2.includes('overflow-hidden')) {
      return `<section${p1}className="${p2} overflow-hidden"`;
    }
    return m;
  });
  fs.writeFileSync(aboutHeroPath, content, 'utf-8');
  console.log('✅ AboutHeroSection.tsx: Добавлен overflow-hidden на секцию с 800px кругами!');
}

// 3. Исправление SecurityHeroSection.tsx (Строка 24, 33: 800px круги)
const secHeroPath = path.join(__dirname, '../src/marketing/components/security/SecurityHeroSection.tsx');
if (fs.existsSync(secHeroPath)) {
  let content = fs.readFileSync(secHeroPath, 'utf-8');
  content = content.replace(/<section([^>]*)className=["']([^"']*)["']/g, (m, p1, p2) => {
    if (!p2.includes('overflow-hidden')) {
      return `<section${p1}className="${p2} overflow-hidden"`;
    }
    return m;
  });
  fs.writeFileSync(secHeroPath, content, 'utf-8');
  console.log('✅ SecurityHeroSection.tsx: Добавлен overflow-hidden на секцию с 800px кругами!');
}

// 4. Исправление ApplicationSection.tsx (Строка 233: max-w-[840px])
const appSecPath = path.join(__dirname, '../src/marketing/components/home/ApplicationSection/ApplicationSection.tsx');
if (fs.existsSync(appSecPath)) {
  let content = fs.readFileSync(appSecPath, 'utf-8');
  content = content.replace(
    /max-w-\[840px\]/g,
    'max-w-[840px] max-w-[calc(100vw-2rem)]'
  );
  fs.writeFileSync(appSecPath, content, 'utf-8');
  console.log('✅ ApplicationSection.tsx: Всплывающее окно ограничено по ширине 100vw!');
}

console.log('\n===============================================================\n');

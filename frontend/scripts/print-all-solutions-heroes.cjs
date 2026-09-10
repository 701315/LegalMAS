const fs = require('fs');
const path = require('path');

const SOLUTIONS_DIR = path.join(__dirname, '../src/marketing/pages/solutions');
const files = fs.readdirSync(SOLUTIONS_DIR).filter(f => f.endsWith('.tsx'));

console.log('\n===============================================================');
console.log('📄 ДЕТАЛЬНЫЙ КОД HERO ВСЕХ 9 СТРАНИЦ SOLUTIONS');
console.log('===============================================================\n');

files.forEach(file => {
  const filePath = path.join(SOLUTIONS_DIR, file);
  const content = fs.readFileSync(filePath, 'utf-8');

  console.log(`==============================================================`);
  console.log(`📂 ФАЙЛ: ${file}`);
  console.log(`==============================================================`);

  // Ищем HeroSection функцию или Hero разметку
  const heroMatch = content.match(/function\s+HeroSection[\s\S]*?(?:return\s*\([\s\S]*?<\/section>\s*\))/);
  if (heroMatch) {
    console.log(heroMatch[0]);
  } else {
    // Ищем первый section
    const secMatch = content.match(/<section[\s\S]*?<\/section>/);
    if (secMatch) {
      console.log(secMatch[0].split('\n').slice(0, 35).join('\n'));
    } else {
      console.log('Hero section не найдена');
    }
  }
  console.log('\n');
});

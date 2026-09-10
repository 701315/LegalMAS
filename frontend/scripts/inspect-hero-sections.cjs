const fs = require('fs');
const path = require('path');

const SOLUTIONS_DIR = path.join(__dirname, '../src/marketing/pages/solutions');
const files = fs.readdirSync(SOLUTIONS_DIR).filter(f => f.endsWith('.tsx'));

console.log('\n===============================================================');
console.log('🔍 ПРОВЕРКА ВЕРСТКИ HERO-СЕКЦИЙ ВО ВСЕХ ФАЙЛАХ');
console.log('===============================================================\n');

files.forEach(file => {
  const filePath = path.join(SOLUTIONS_DIR, file);
  const content = fs.readFileSync(filePath, 'utf-8');

  console.log(`📄 Файл: ${file}`);
  
  // Ищем первый section или hero контейнер
  const heroMatch = content.match(/<main[\s\S]*?<section[^>]*>([\s\S]*?)<\/section>/i) ||
                    content.match(/<section[^>]*>([\s\S]*?)<\/section>/i);
                    
  if (heroMatch) {
    const lines = heroMatch[0].split('\n').slice(0, 20).join('\n');
    console.log(lines);
  } else {
    console.log('   Hero section не найдена по паттерну');
  }
  console.log('\n---------------------------------------------------------------\n');
});

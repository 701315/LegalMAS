const fs = require('fs');
const path = require('path');

const MARKETING_DIR = path.join(__dirname, '../src/marketing');

function getAllFiles(dir, extension = '.tsx') {
  const results = [];
  if (!fs.existsSync(dir)) return results;
  const list = fs.readdirSync(dir);
  for (const file of list) {
    const filePath = path.join(dir, file);
    if (filePath.includes('node_modules')) continue;
    const stat = fs.statSync(filePath);
    if (stat.isDirectory()) {
      results.push(...getAllFiles(filePath, extension));
    } else if (file.endsWith(extension)) {
      results.push(filePath);
    }
  }
  return results;
}

// Маппинг "магических чисел" на семантические классы из index.css
const replacements = [
  // 1. Основные заголовки (Clamp)
  [/text-\[clamp\(2\.5rem,5vw,4\.2rem\)\]/g, 'text-display'],
  [/text-\[clamp\(2\.5rem,5vw,4\.5rem\)\]/g, 'text-display'], // Небольшая вариация, тоже ведём в display
  [/text-\[clamp\(2\.25rem,4vw,3\.25rem\)\]/g, 'text-h1'],
  [/text-\[clamp\(1\.75rem,3vw,2\.5rem\)\]/g, 'text-h2'],
  
  // 2. Тело текста и заголовки карточек
  [/text-\[1\.25rem\]/g, 'text-h3'],
  [/text-\[1\.0625rem\]/g, 'text-body'],       // 17px
  [/text-\[0\.9375rem\]/g, 'text-body-sm'],    // 15px
  [/text-\[0\.8125rem\]/g, 'text-eyebrow'],    // 13px
  [/text-\[0\.75rem\]/g, 'text-meta'],         // 12px
  
  // 3. Стандартные мелкие размеры (оставляем как Tailwind-дефолты, они и так семантичны)
  [/text-\[10px\]/g, 'text-[10px]'], // Оставляем, это специфичный микро-размер
  [/text-\[11px\]/g, 'text-[11px]'], // Оставляем
  
  // 4. Очистка inline fontSize (только те, что точно совпадают с нашими токенами)
  [/fontSize:\s*"1\.0625rem"/g, 'className="text-body"'], // Внимание: это упрощённая замена, лучше править вручную, если встречается редко
];

let totalReplacements = 0;
const files = getAllFiles(MARKETING_DIR);

console.log('\n🔍 Запускаю финальную очистку типографики...\n');

for (const file of files) {
  let content = fs.readFileSync(file, 'utf-8');
  let originalContent = content;
  let fileReplacements = 0;

  for (const [regex, replacement] of replacements) {
    // Пропускаем замену inline fontSize, если она слишком рискованна для массового запуска
    if (replacement.includes('className=')) continue; 

    const matches = content.match(regex);
    if (matches) {
      content = content.replace(regex, replacement);
      fileReplacements += matches.length;
    }
  }

  if (content !== originalContent) {
    fs.writeFileSync(file, content, 'utf-8');
    totalReplacements += fileReplacements;
    console.log(`   ✅ ${path.relative(path.join(__dirname, '..'), file)} (${fileReplacements} замен)`);
  }
}

console.log(`\n🎉 Готово! Выполнено ${totalReplacements} дополнительных замен.`);
console.log('💡 Теперь размеры текста максимально унифицированы.\n');

const fs = require('fs');
const path = require('path');

const MARKETING_DIR = path.join(__dirname, 'src/marketing');

function getAllFiles(dir) {
  let results = [];
  if (!fs.existsSync(dir)) return results;
  const list = fs.readdirSync(dir);
  for (const file of list) {
    const filePath = path.join(dir, file);
    const stat = fs.statSync(filePath);
    if (stat.isDirectory()) {
      results.push(...getAllFiles(filePath));
    } else if (file.endsWith('.tsx') || file.endsWith('.ts')) {
      results.push(filePath);
    }
  }
  return results;
}

const files = getAllFiles(MARKETING_DIR);
let changesFound = 0;

console.log('\n🔍 ТЕСТОВЫЙ ПРОГОН МИГРАЦИИ (ФАЙЛЫ НЕ ИЗМЕНЯЮТСЯ)...\n');

files.forEach(file => {
  let content = fs.readFileSync(file, 'utf-8');
  const relativeName = path.relative(MARKETING_DIR, file);
  let fileChanges = [];

  // 1. Проверка замены section-title -> text-h2
  if (content.includes('section-title')) {
    fileChanges.push('   • [section-title]  ===>  [text-h2]');
  }

  // 2. Проверка замен clamp для Hero/H1
  if (content.match(/font-serif\s+text-\[clamp\(2\.5rem,5vw,4\.5rem\)\]/)) {
    fileChanges.push('   • [font-serif text-[clamp(2.5rem,5vw,4.5rem)]...]  ===>  [text-display]');
  }
  if (content.match(/font-serif\s+text-\[clamp\(2\.25rem,4vw,3\.25rem\)\]/)) {
    fileChanges.push('   • [font-serif text-[clamp(2.25rem,4vw,3.25rem)]...]  ===>  [text-h1]');
  }

  // 3. Проверка основного текста body
  if (content.match(/text-\[1\.0625rem\]\s+leading-\[1\.7\]/)) {
    fileChanges.push('   • [text-[1.0625rem] leading-[1.7]]  ===>  [text-body]');
  }

  // 4. Проверка мелких надзаголовков (eyebrow)
  if (content.match(/text-\[11px\]\s+font-bold\s+uppercase/)) {
    fileChanges.push('   • [text-[11px] font-bold uppercase...]  ===>  [text-meta font-bold]');
  }

  if (fileChanges.length > 0) {
    console.log(`📄 src/marketing/${relativeName}`);
    fileChanges.forEach(change => console.log(change));
    console.log('');
    changesFound++;
  }
});

console.log(`\n📊 Итого будет затронуто файлов: ${changesFound}`);
console.log('ℹ️  Ни один файл не был изменен. Ознакомьтесь со списком изменений выше.\n');

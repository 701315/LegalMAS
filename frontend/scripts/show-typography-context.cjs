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

function readSafe(f) {
  try { return fs.readFileSync(f, 'utf-8'); } catch { return ''; }
}

function relativePath(f) {
  return path.relative(path.join(__dirname, '..'), f);
}

// Список нестандартных значений для поиска
const targets = [
  'text-[10px]',
  'text-[11px]',
  'text-[13px]',
  'text-[15px]',
  'text-[1rem]',
  'text-[1.125rem]',
  'text-[1.25rem]',
  'text-[1.375rem]',
  'text-[1.75rem]',
  'text-[2rem]',
  'text-[2.25rem]',
  'text-[2.5rem]',
  'text-[4.5rem]',
  'text-[0.6875rem]',
  'text-[0.875rem]',
  'text-[0.95rem]',
  'text-[clamp(2.5rem,5vw,4rem)]',
  'text-[clamp(1.5rem,3vw,2rem)]',
  'text-[clamp(2rem,4vw,3.05rem)]',
  'text-[rgba(250,248,245,0.75)]',
  'text-[rgba(200,107,82,1)]',
  'text-[rgba(250,248,245,1)]',
];

// Группировка результатов: target -> [{file, line, context, element}]
const results = new Map();

const files = getAllFiles(MARKETING_DIR);

for (const file of files) {
  const content = readSafe(file);
  const lines = content.split('\n');
  const rel = relativePath(file);
  
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    for (const target of targets) {
      if (line.includes(target)) {
        if (!results.has(target)) results.set(target, []);
        
        // Определяем элемент (H1, H2, H3, p, button, span, div)
        const elementMatch = line.match(/<(h[1-6]|p|button|span|div|a|label|strong|li)[^>]*className/);
        const element = elementMatch ? elementMatch[1] : '?';
        
        results.get(target).push({
          file: rel,
          lineNum: i + 1,
          context: line.trim(),
          element: element,
        });
      }
    }
  }
}

// Вывод отчёта
const divider = '\n' + '═'.repeat(100) + '\n';
const lines = [];

lines.push(divider);
lines.push('  🔍 ДЕТАЛЬНЫЙ АУДИТ НЕСТАНДАРТНЫХ ЗНАЧЕНИЙ ТИПОГРАФИКИ');
lines.push('  Дата: ' + new Date().toISOString().split('T')[0]);
lines.push(divider);

// Сортируем по количеству вхождений (от большего к меньшему)
const sorted = [...results.entries()].sort((a, b) => b[1].length - a[1].length);

for (const [target, occurrences] of sorted) {
  lines.push(`\n📌 ${target}  (${occurrences.length} ${occurrences.length === 1 ? 'случай' : 'случаев'})`);
  lines.push('─'.repeat(100));
  
  for (const occ of occurrences) {
    lines.push(`   📄 ${occ.file}:${occ.lineNum}  [элемент: <${occ.element}>]`);
    // Обрезаем длинные строки для читаемости
    const ctx = occ.context.length > 150 ? occ.context.substring(0, 147) + '...' : occ.context;
    lines.push(`      ${ctx}`);
  }
}

// Inline fontSize
lines.push('\n\n🎨 INLINE fontSize (стиль в JS-объекте)\n');
for (const file of files) {
  const content = readSafe(file);
  const linesArr = content.split('\n');
  const rel = relativePath(file);
  
  for (let i = 0; i < linesArr.length; i++) {
    const line = linesArr[i];
    if (line.includes('fontSize:') && (line.includes('clamp') || line.includes('px') || line.includes('rem'))) {
      lines.push(`   📄 ${rel}:${i + 1}`);
      const ctx = line.trim().length > 150 ? line.trim().substring(0, 147) + '...' : line.trim();
      lines.push(`      ${ctx}`);
    }
  }
}

lines.push('\n' + divider);

const report = lines.join('\n');
console.log(report);

const reportPath = path.join(__dirname, '../typography-context-report.txt');
fs.writeFileSync(reportPath, report, 'utf-8');
console.log(`\n💾 Отчёт сохранён: ${reportPath}`);

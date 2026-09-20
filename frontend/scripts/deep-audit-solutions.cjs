const fs = require('fs');
const path = require('path');

const SOLUTIONS_DIR = path.join(__dirname, '../src/marketing/pages/solutions');
const files = fs.readdirSync(SOLUTIONS_DIR).filter(f => f.endsWith('.tsx'));

console.log('\n===============================================================');
console.log('🔬 ГЛУБОКИЙ АНАЛИЗ ВСЕХ 9 СТРАНИЦ SOLUTIONS');
console.log('===============================================================\n');

files.forEach(file => {
  const filePath = path.join(SOLUTIONS_DIR, file);
  const content = fs.readFileSync(filePath, 'utf-8');

  console.log(`═══════════════════════════════════════════════════════════════`);
  console.log(`📄 СТРАНИЦА: ${file}`);
  console.log(`═══════════════════════════════════════════════════════════════`);

  // 1. Поиск H1
  const h1Match = content.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i);
  if (h1Match) {
    const cls = h1Match[0].match(/className=["']([^"']+)["']/)?.[1] || 'no-class';
    console.log(`   👑 Hero H1: class="${cls}"`);
  } else {
    console.log(`   ⚠️ НЕТ ТЕГА <h1>!`);
  }

  // 2. Поиск всех H2
  const h2Matches = content.match(/<h2[^>]*>([\s\S]*?)<\/h2>/gi) || [];
  console.log(`   📌 Заголовки H2 (${h2Matches.length} шт):`);
  h2Matches.forEach(h2 => {
    const cls = h2.match(/className=["']([^"']+)["']/)?.[1] || '';
    const textSnippet = h2.replace(/<[^>]+>/g, '').trim().substring(0, 50);
    console.log(`      • class="${cls}" => "${textSnippet}"`);
  });

  // 3. Поиск всех H3
  const h3Matches = content.match(/<h3[^>]*>([\s\S]*?)<\/h3>/gi) || [];
  console.log(`   🏷️  Подзаголовки/карточки H3 (${h3Matches.length} шт):`);
  h3Matches.forEach(h3 => {
    const cls = h3.match(/className=["']([^"']+)["']/)?.[1] || '';
    const textSnippet = h3.replace(/<[^>]+>/g, '').trim().substring(0, 40);
    console.log(`      • class="${cls}" => "${textSnippet}"`);
  });

  // 4. Поиск некорректных токенов (не через var(--...))
  const legacyClasses = content.match(/\b(bg-base|text-primary|text-secondary|text-muted|bg-surface|selection:bg-accent)\b/g) || [];
  if (legacyClasses.length > 0) {
    console.log(`   ⚠️ Устаревшие классы без var: ${[...new Set(legacyClasses)].join(', ')}`);
  } else {
    console.log(`   ✅ Переменные цветов в порядке`);
  }

  console.log('');
});

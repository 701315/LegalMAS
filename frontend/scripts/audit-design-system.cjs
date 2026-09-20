const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const SRC = path.join(ROOT, 'src');
const MARKETING = path.join(SRC, 'marketing');
const APP_DIR = path.join(SRC, 'app'); // Next.js app router (если есть)

function getAllFiles(dir, extensions = ['.tsx', '.ts', '.css', '.js', '.json']) {
  const results = [];
  if (!fs.existsSync(dir)) return results;
  const list = fs.readdirSync(dir);
  for (const file of list) {
    const filePath = path.join(dir, file);
    if (filePath.includes('node_modules')) continue;
    const stat = fs.statSync(filePath);
    if (stat.isDirectory()) {
      results.push(...getAllFiles(filePath, extensions));
    } else if (extensions.some(ext => file.endsWith(ext))) {
      results.push(filePath);
    }
  }
  return results;
}

function readSafe(f) {
  try { return fs.readFileSync(f, 'utf-8'); } catch { return ''; }
}

function rel(f) { return path.relative(ROOT, f); }

const divider = '\n' + '═'.repeat(80) + '\n';
const lines = [];

lines.push(divider);
lines.push('  🎨 АУДИТ ДИЗАЙН-СИСТЕМЫ ЛЕНДИНГА (Steloom)');
lines.push('  Дата: ' + new Date().toISOString().split('T')[0]);
lines.push('  ⚠️  Дашборд (приложение) ИСКЛЮЧЁН из анализа');
lines.push(divider);

// ═════════════════════════════════════════════════════════════════════════════
// 1. КОНФИГУРАЦИЯ ШРИФТОВ
// ═════════════════════════════════════════════════════════════════════════════
lines.push('\n\n📝 1. КОНФИГУРАЦИЯ ШРИФТОВ\n');

// 1.1. tailwind.config
const twConfigs = getAllFiles(ROOT, ['.js', '.ts', '.mjs', '.cjs'])
  .filter(f => path.basename(f).startsWith('tailwind.config'));

if (twConfigs.length === 0) {
  lines.push('   ⚠️  tailwind.config не найден в корне проекта');
} else {
  for (const cfg of twConfigs) {
    lines.push(`   📄 ${rel(cfg)}`);
    const content = readSafe(cfg);
    
    // fontFamily
    const fontFamilyMatch = content.match(/fontFamily\s*:\s*\{([\s\S]*?)\}/);
    if (fontFamilyMatch) {
      lines.push('      🔤 fontFamily:');
      const inner = fontFamilyMatch[1];
      const fontEntries = inner.match(/['"]?(\w+)['"]?\s*:\s*\[([\s\S]*?)\]/g) || [];
      for (const entry of fontEntries) {
        lines.push(`         • ${entry.replace(/\s+/g, ' ').trim()}`);
      }
    } else {
      lines.push('      ⚠️  fontFamily не задан в tailwind.config');
    }
    
    // fontSize
    const fontSizeMatch = content.match(/fontSize\s*:\s*\{([\s\S]*?)\}/);
    if (fontSizeMatch) {
      lines.push('      📏 fontSize (кастомные):');
      const inner = fontSizeMatch[1];
      const entries = inner.match(/['"]?([\w-]+)['"]?\s*:/g) || [];
      for (const e of entries.slice(0, 20)) {
        lines.push(`         • ${e.replace(':', '').trim()}`);
      }
      if (entries.length > 20) lines.push(`         ... и ещё ${entries.length - 20}`);
    } else {
      lines.push('      ℹ️  fontSize не расширен (используются только дефолты Tailwind)');
    }
  }
}

// 1.2. Google Fonts / @import в CSS
lines.push('\n   🔗 Подключение внешних шрифтов:');
const cssFiles = getAllFiles(SRC, ['.css']).filter(f => !f.includes('node_modules'));
let foundFonts = false;
for (const css of cssFiles) {
  const content = readSafe(css);
  const googleMatches = content.match(/@import\s+url\(['"]?(https:\/\/fonts\.googleapis\.com[^'")\s]+)['"]?\)/g) || [];
  const fontFaceMatches = content.match(/@font-face\s*\{[\s\S]*?\}/g) || [];
  const fontFamilies = content.match(/font-family:\s*['"]?([^;'"}]+)['"]?/g) || [];
  
  if (googleMatches.length || fontFaceMatches.length || fontFamilies.length) {
    lines.push(`      📄 ${rel(css)}`);
    for (const m of googleMatches) {
      lines.push(`         🌐 ${m.substring(0, 120)}...`);
    }
    for (const m of fontFaceMatches) {
      const nameMatch = m.match(/font-family:\s*['"]?([^;'"}]+)['"]?/);
      if (nameMatch) lines.push(`         📦 @font-face: ${nameMatch[1].trim()}`);
    }
    foundFonts = true;
  }
}
if (!foundFonts) {
  lines.push('      ⚠️  Внешние шрифты не найдены в CSS');
}

// 1.3. HTML-файлы (index.html, _document.tsx)
lines.push('\n   📄 HTML/Document файлы:');
const htmlFiles = getAllFiles(ROOT, ['.html', '.tsx']).filter(f => 
  f.endsWith('index.html') || 
  f.includes('_document') || 
  f.includes('layout.tsx') ||
  f.includes('RootLayout')
);
for (const f of htmlFiles) {
  const content = readSafe(f);
  const linkFonts = content.match(/<link[^>]*fonts\.googleapis[^>]*>/g) || [];
  const preloadFonts = content.match(/<link[^>]*fonts\.gstatic[^>]*>/g) || [];
  if (linkFonts.length || preloadFonts.length) {
    lines.push(`      📄 ${rel(f)}`);
    for (const l of linkFonts) lines.push(`         🌐 ${l.substring(0, 140)}`);
    for (const p of preloadFonts) lines.push(`         ⚡ preload: ${p.substring(0, 140)}`);
  }
}

// ═════════════════════════════════════════════════════════════════════════════
// 2. ЦВЕТОВАЯ СИСТЕМА (CSS-переменные)
// ═════════════════════════════════════════════════════════════════════════════
lines.push('\n\n🎨 2. ЦВЕТОВАЯ СИСТЕМА (CSS-переменные)\n');

const allCssVars = new Map(); // varName -> { value, file }
for (const css of cssFiles) {
  const content = readSafe(css);
  const varMatches = content.match(/(--[\w-]+)\s*:\s*([^;}\n]+)/g) || [];
  for (const m of varMatches) {
    const [name, ...rest] = m.split(':');
    const value = rest.join(':').trim();
    if (!allCssVars.has(name)) {
      allCssVars.set(name, { value, file: rel(css) });
    }
  }
}

// Группируем по префиксам
const groups = {
  'colors': [],
  'bg': [],
  'text': [],
  'border': [],
  'font': [],
  'other': []
};

for (const [name, data] of allCssVars) {
  if (name.startsWith('--color-')) groups.colors.push({ name, ...data });
  else if (name.startsWith('--bg-')) groups.bg.push({ name, ...data });
  else if (name.startsWith('--text-')) groups.text.push({ name, ...data });
  else if (name.startsWith('--border-')) groups.border.push({ name, ...data });
  else if (name.startsWith('--font-')) groups.font.push({ name, ...data });
  else groups.other.push({ name, ...data });
}

lines.push(`   Всего CSS-переменных: ${allCssVars.size}\n`);

for (const [groupName, vars] of Object.entries(groups)) {
  if (vars.length === 0) continue;
  lines.push(`   📌 --${groupName}-* (${vars.length}):`);
  for (const v of vars) {
    lines.push(`      • ${v.name.padEnd(30)} = ${v.value.padEnd(25)} (${v.file})`);
  }
  lines.push('');
}

// ═════════════════════════════════════════════════════════════════════════════
// 3. СТРУКТУРА МАРКЕТИНГОВЫХ КОМПОНЕНТОВ
// ═════════════════════════════════════════════════════════════════════════════
lines.push('\n📁 3. СТРУКТУРА МАРКЕТИНГОВЫХ КОМПОНЕНТОВ\n');

const marketingComponents = path.join(MARKETING, 'components');
const sharedDir = path.join(marketingComponents, 'shared');
const platformDir = path.join(marketingComponents, 'platform');
const motionDir = path.join(MARKETING, 'motion');

function listDir(dir, indent = '   ') {
  if (!fs.existsSync(dir)) return [];
  const items = fs.readdirSync(dir);
  const result = [];
  for (const item of items) {
    const full = path.join(dir, item);
    const stat = fs.statSync(full);
    if (stat.isDirectory()) {
      result.push(`${indent}📂 ${item}/`);
      result.push(...listDir(full, indent + '   '));
    } else {
      result.push(`${indent}📄 ${item}`);
    }
  }
  return result;
}

lines.push('   📂 src/marketing/');
lines.push(...listDir(MARKETING, '      '));

// ═════════════════════════════════════════════════════════════════════════════
// 4. ПЕРЕИСПОЛЬЗУЕМЫЕ КОМПОНЕНТЫ (shared/)
// ═════════════════════════════════════════════════════════════════════════════
lines.push('\n\n🔧 4. ПЕРЕИСПОЛЬЗУЕМЫЕ КОМПОНЕНТЫ (shared/)\n');

if (fs.existsSync(sharedDir)) {
  const sharedFiles = fs.readdirSync(sharedDir).filter(f => f.endsWith('.tsx'));
  for (const f of sharedFiles) {
    const full = path.join(sharedDir, f);
    const content = readSafe(full);
    const componentName = f.replace('.tsx', '');
    
    // Считаем, где используется
    const usageCount = getAllFiles(MARKETING, ['.tsx'])
      .filter(file => {
        const c = readSafe(file);
        return c.includes(`from`) && c.includes(componentName) && file !== full;
      }).length;
    
    lines.push(`   🧩 ${componentName}`);
    lines.push(`      Используется в: ${usageCount} файлах маркетинга`);
    
    // Вытаскиваем пропсы
    const propsMatch = content.match(/interface\s+\w+Props\s*\{([\s\S]*?)\}/);
    if (propsMatch) {
      const props = propsMatch[1].match(/(\w+)\s*(\??)\s*:/g) || [];
      if (props.length > 0) {
        lines.push(`      Пропсы: ${props.map(p => p.replace(':', '').trim()).join(', ')}`);
      }
    }
  }
} else {
  lines.push('   ⚠️  Папка shared/ не найдена');
}

// ═════════════════════════════════════════════════════════════════════════════
// 5. АНАЛИЗ ПОВТОРЕНИЙ (паттерны секций)
// ═════════════════════════════════════════════════════════════════════════════
lines.push('\n\n🔁 5. АНАЛИЗ ПОВТОРЕНИЙ (паттерны секций)\n');

const pageFiles = getAllFiles(path.join(MARKETING, 'pages'), ['.tsx']);

// Паттерны, которые могут быть вынесены в компоненты
const patterns = {
  'HeroSection': 0,
  'CTASection': 0,
  'CapabilitiesSection': 0,
  'BriefBlocksSection|ThreeBlocksSection|ThreePillarsSection': 0,
  'PathCrumb': 0,
  'cta-primary': 0,
  'section-title': 0,
  'data-header-theme="dark"': 0,
  'data-header-theme="light"': 0,
};

for (const file of pageFiles) {
  const content = readSafe(file);
  for (const pattern of Object.keys(patterns)) {
    const regex = new RegExp(pattern, 'g');
    const matches = content.match(regex);
    if (matches) patterns[pattern] += matches.length;
  }
}

lines.push('   Частота паттернов на страницах лендинга:');
for (const [pattern, count] of Object.entries(patterns)) {
  if (count > 0) {
    lines.push(`      • ${pattern.padEnd(45)} — ${count} раз`);
  }
}

// ═════════════════════════════════════════════════════════════════════════════
// 6. РАЗДЕЛЕНИЕ ЛЕНДИНГ / ДАШБОРД
// ═════════════════════════════════════════════════════════════════════════════
lines.push('\n\n🧭 6. РАЗДЕЛЕНИЕ ЛЕНДИНГ / ДАШБОРД\n');

const marketingFiles = getAllFiles(MARKETING, ['.tsx', '.ts']);
const dashboardFiles = getAllFiles(SRC, ['.tsx', '.ts']).filter(f => {
  const relPath = rel(f);
  return !relPath.includes('/marketing/') && !relPath.includes('node_modules');
});

lines.push(`   📊 Файлов маркетинга (лендинг): ${marketingFiles.length}`);
lines.push(`   📊 Файлов приложения (дашборд): ${dashboardFiles.length}`);
lines.push('');
lines.push('   🎯 Маркетинг использует:');
lines.push('      • /src/marketing/components/ — UI-компоненты лендинга');
lines.push('      • /src/marketing/pages/ — страницы лендинга');
lines.push('      • /src/marketing/hooks/ — хуки (useMediaQuery, useScrollDirection)');
lines.push('      • /src/marketing/motion/ — анимации (Reveal, RevealItem)');
lines.push('      • /src/marketing/content/ — контент (устаревший, переносится в i18n)');
lines.push('');
lines.push('   🎯 Дашборд использует:');
lines.push('      • /src/components/ — общие компоненты приложения');
lines.push('      • /src/pages/ — страницы приложения');
lines.push('      • /src/hooks/ — хуки приложения');
lines.push('      • /src/lib/ — утилиты и API');

// ═════════════════════════════════════════════════════════════════════════════
// 7. РЕКОМЕНДАЦИИ
// ═════════════════════════════════════════════════════════════════════════════
lines.push('\n\n💡 7. РЕКОМЕНДАЦИИ\n');

lines.push('   🔤 ШРИФТЫ:');
if (allCssVars.has('--font-serif') || allCssVars.has('--font-sans')) {
  lines.push('      ✅ CSS-переменные для шрифтов уже заданы');
} else {
  lines.push('      ⚠️  Рекомендуется ввести --font-serif и --font-sans в globals.css');
}

lines.push('\n   🎨 ЦВЕТА:');
const hardcodedColors = ['text-[#1A1917]', 'text-[#78756F]', 'text-[#A8A29E]', 'text-[#C86B52]'];
let hardcodedCount = 0;
for (const file of getAllFiles(MARKETING, ['.tsx'])) {
  const content = readSafe(file);
  for (const color of hardcodedColors) {
    const matches = content.match(new RegExp(color.replace(/[[\]]/g, '\\$&'), 'g'));
    if (matches) hardcodedCount += matches.length;
  }
}
lines.push(`      • Найдено ${hardcodedCount} случаев хардкод-цветов (text-[#...])`);
if (hardcodedCount > 50) {
  lines.push('      ⚠️  Рекомендуется массовая замена на CSS-переменные');
}

lines.push('\n   📏 РАЗМЕРЫ:');
lines.push('      • Рекомендуется ввести семантические классы:');
lines.push('        - text-display (H1 лендинга)');
lines.push('        - text-h1, text-h2, text-h3');
lines.push('        - text-body, text-body-sm');
lines.push('        - text-eyebrow, text-meta');

lines.push('\n   🧩 КОМПОНЕНТЫ:');
lines.push('      • Многие секции (Hero, CTA, Capabilities) дублируются');
lines.push('      • Рекомендуется вынести общие паттерны в /components/shared/');

lines.push('\n' + divider);

// Вывод и сохранение
const report = lines.join('\n');
console.log(report);

const reportPath = path.join(ROOT, 'design-system-audit.txt');
fs.writeFileSync(reportPath, report, 'utf-8');
console.log(`\n💾 Отчёт сохранён: ${reportPath}`);

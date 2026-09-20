#!/usr/bin/env node
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const MARKETING_DIR = path.join(__dirname, '../src/marketing');

function getAllFiles(dir, extension = '.tsx') {
  const results = [];
  if (!fs.existsSync(dir)) return results;
  const list = fs.readdirSync(dir);
  for (const file of list) {
    const filePath = path.join(dir, file);
    const stat = fs.statSync(filePath);
    if (stat.isDirectory()) {
      results.push(...getAllFiles(filePath, extension));
    } else if (file.endsWith(extension)) {
      results.push(filePath);
    }
  }
  return results;
}

function readSafe(filePath) {
  try { return fs.readFileSync(filePath, 'utf-8'); } catch (e) { return ''; }
}

function relativePath(filePath) {
  return path.relative(path.join(__dirname, '..'), filePath);
}

function analyzePageStructure() {
  const pagesDir = path.join(MARKETING_DIR, 'pages');
  const pageFiles = getAllFiles(pagesDir);
  return pageFiles.map(f => {
    const rel = relativePath(f);
    const name = path.basename(f, '.tsx');
    let route = '/' + name.replace(/Page$/, '').toLowerCase();
    if (rel.includes('/solutions/')) route = '/solutions/' + name.replace(/Page$/, '').toLowerCase();
    else if (rel.includes('/about')) route = '/about';
    return { file: rel, name, route };
  });
}

function analyzeTypography() {
  const files = getAllFiles(MARKETING_DIR);
  const results = {
    fonts: new Map(), sizes: new Map(), fontSizes: new Map(),
    clampUsages: [], byFile: new Map(),
    roles: { h1: [], h2: [], h3: [], eyebrow: [] }
  };
  
  const fontPatterns = [/font-serif/g, /font-sans/g, /font-mono/g, /font-\[[^\]]+\]/g];
  const sizePatterns = [/text-(?:xs|sm|base|lg|xl|2xl|3xl|4xl|5xl|6xl|7xl|8xl|9xl)/g, /text-\[[^\]]+\]/g];
  
  for (const file of files) {
    const content = readSafe(file);
    const rel = relativePath(file);
    
    for (const p of fontPatterns) {
      for (const m of content.match(p) || []) {
        results.fonts.set(m, (results.fonts.get(m) || 0) + 1);
      }
    }
    for (const p of sizePatterns) {
      for (const m of content.match(p) || []) {
        results.sizes.set(m, (results.sizes.get(m) || 0) + 1);
        if (m.includes('clamp')) results.clampUsages.push({ file: rel, usage: m });
      }
    }
    
    for (const m of content.match(/fontSize:\s*(?:"([^"]+)"|`([^`]+)`)/g) || []) {
      results.fontSizes.set(m, (results.fontSizes.get(m) || 0) + 1);
    }
    
    for (const m of content.match(/<h1[^>]*className="([^"]*)"[^>]*>/g) || []) {
      results.roles.h1.push({ file: rel, className: m.match(/className="([^"]*)"/)[1] });
    }
    for (const m of content.match(/<h2[^>]*className="([^"]*)"[^>]*>/g) || []) {
      results.roles.h2.push({ file: rel, className: m.match(/className="([^"]*)"/)[1] });
    }
    for (const m of content.match(/<h3[^>]*className="([^"]*)"[^>]*>/g) || []) {
      results.roles.h3.push({ file: rel, className: m.match(/className="([^"]*)"/)[1] });
    }
    for (const m of content.match(/className="([^"]*eyebrow[^"]*)"/g) || []) {
      results.roles.eyebrow.push({ file: rel, className: m });
    }
  }
  return results;
}

function analyzeLinks(pages) {
  const files = getAllFiles(MARKETING_DIR);
  const existingRoutes = new Set(pages.map(p => p.route));
  const links = { internal: [], anchors: [], mailto: [], external: [], windowNav: [], broken: [] };
  
  for (const file of files) {
    const content = readSafe(file);
    const rel = relativePath(file);
    
    let match;
    const linkRegex = /<Link[^>]*to=["']([^"']+)["'][^>]*>/g;
    while ((match = linkRegex.exec(content)) !== null) {
      const to = match[1];
      links.internal.push({ file: rel, to });
      if (to.startsWith('/') && !to.startsWith('/#')) {
        const norm = to.replace(/\/$/, '') || '/';
        if (!existingRoutes.has(norm)) links.broken.push({ file: rel, to, type: 'Link' });
      }
    }
    
    const anchorRegex = /<a[^>]*href=["']([^"']+)["'][^>]*>/g;
    while ((match = anchorRegex.exec(content)) !== null) {
      const href = match[1];
      if (href.startsWith('mailto:')) links.mailto.push({ file: rel, href });
      else if (href.startsWith('http://') || href.startsWith('https://')) links.external.push({ file: rel, href });
      else if (href.startsWith('/') || href.startsWith('#')) {
        links.anchors.push({ file: rel, href });
        if (href.startsWith('/') && !href.startsWith('/#')) {
          const norm = href.replace(/\/$/, '') || '/';
          if (!existingRoutes.has(norm)) links.broken.push({ file: rel, to: href, type: 'a' });
        }
      }
    }
  }
  return links;
}

function generateReport(pages, typography, links) {
  const lines = [];
  const divider = '\n' + '═'.repeat(80) + '\n';
  lines.push(divider, '  📊 ОТЧЁТ ПО АНАЛИЗУ ПАПКИ /src/marketing', '  Дата: ' + new Date().toISOString().split('T')[0], divider);
  
  lines.push('\n📄 1. КАРТА СТРАНИЦ (' + pages.length + ' шт.)\n');
  for (const p of pages) {
    lines.push(`   • ${p.file.replace('src/marketing/', '').padEnd(60)} → ${p.route}`);
  }
  
  lines.push('\n\n🔤 2. АУДИТ ТИПОГРАФИКИ\n');
  lines.push('   📌 Шрифты:');
  for (const [f, c] of [...typography.fonts.entries()].sort((a,b) => b[1]-a[1])) {
    lines.push(`      • ${f.padEnd(20)} — ${c}`);
  }
  lines.push('\n   📏 Размеры (Tailwind):');
  for (const [s, c] of [...typography.sizes.entries()].sort((a,b) => b[1]-a[1])) {
    lines.push(`      • ${s.padEnd(35)} — ${c}`);
  }
  lines.push('\n   🎨 Inline fontSize:');
  for (const [s, c] of [...typography.fontSizes.entries()].sort((a,b) => b[1]-a[1])) {
    lines.push(`      • ${s.padEnd(40)} — ${c}`);
  }
  lines.push(`\n   📐 Clamp-значений: ${typography.clampUsages.length}`);
  lines.push(`\n   🎭 Роли: H1=${typography.roles.h1.length}, H2=${typography.roles.h2.length}, H3=${typography.roles.h3.length}, Eyebrow=${typography.roles.eyebrow.length}`);
  
  if (typography.roles.h1.length > 0) {
    lines.push('\n   🔍 Классы H1:');
    const uniq = new Set(typography.roles.h1.map(h => h.className));
    for (const c of uniq) lines.push(`      • "${c}"`);
  }
  
  lines.push('\n\n🔗 3. ССЫЛКИ\n');
  lines.push(`   📎 <Link>: ${links.internal.length}`);
  lines.push(`   📎 <a href>: ${links.anchors.length}`);
  lines.push(`   📧 Mailto: ${links.mailto.length}`);
  lines.push(`   🌐 Внешние: ${links.external.length}`);
  
  if (links.broken.length > 0) {
    lines.push('\n   ⚠️  СЛОМАННЫЕ:');
    for (const b of links.broken) lines.push(`      • ${b.file} → ${b.to} (${b.type})`);
  } else {
    lines.push('\n   ✅ Все внутренние ссылки валидны!');
  }
  
  lines.push('\n' + divider);
  return lines.join('\n');
}

console.log('\n🔍 Анализирую...\n');
if (!fs.existsSync(MARKETING_DIR)) {
  console.error('❌ Папка не найдена:', MARKETING_DIR);
  process.exit(1);
}

const pages = analyzePageStructure();
const typography = analyzeTypography();
const links = analyzeLinks(pages);
const report = generateReport(pages, typography, links);

console.log(report);

const reportPath = path.join(__dirname, '../marketing-analysis-report.txt');
fs.writeFileSync(reportPath, report, 'utf-8');
console.log(`\n💾 TXT: ${reportPath}`);

const jsonPath = path.join(__dirname, '../marketing-analysis-report.json');
fs.writeFileSync(jsonPath, JSON.stringify({ pages, typography: { fonts: Object.fromEntries(typography.fonts), sizes: Object.fromEntries(typography.sizes), fontSizes: Object.fromEntries(typography.fontSizes), clampUsages: typography.clampUsages, roles: typography.roles }, links }, null, 2), 'utf-8');
console.log(`💾 JSON: ${jsonPath}`);
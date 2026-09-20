const fs = require('fs');
const path = require('path');

const SOL_DIR = path.join(__dirname, '../src/marketing/pages/solutions');

function processFile(filePath) {
  if (!fs.existsSync(filePath)) return;
  let content = fs.readFileSync(filePath, 'utf-8');

  // 1. Заголовки секций h2 -> text-h1
  content = content.replace(
    /<h2([^>]*)className=["']([^"']*)text-h2([^"']*)["']/g,
    '<h2$1className="$2text-h1$3"'
  );

  // 2. Исправление карточек: h3 italic / text-h3 -> font-serif text-h3
  content = content.replace(
    /className=["']text-h3 italic["']/g,
    'className="text-h3 font-serif italic text-[var(--text-primary)] text-start"'
  );

  // 3. Выравнивание основного текста p.text-body-sm -> p.text-body
  content = content.replace(
    /className=["']mt-3 text-body-sm["']/g,
    'className="mt-3 text-body leading-relaxed text-[var(--text-secondary)] text-start"'
  );

  fs.writeFileSync(filePath, content, 'utf-8');
  console.log(`✅ Страница ${path.basename(filePath)} успешно приведена к стандарту!`);
}

const files = fs.readdirSync(SOL_DIR).filter(f => f.endsWith('.tsx'));
files.forEach(f => processFile(path.join(SOL_DIR, f)));


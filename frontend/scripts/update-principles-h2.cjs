const fs = require('fs');
const path = require('path');

const ABOUT_DIR = path.join(__dirname, '../src/marketing/components/about');

function processFile(filePath) {
  if (!fs.existsSync(filePath)) return;
  let content = fs.readFileSync(filePath, 'utf-8');

  // Заменяем h3/h4 заголовки карточек принципов и философии на text-h2
  content = content.replace(
    /<h[34][^>]*className=["'][^"']*["'][^>]*>/g,
    '<h3 className="mt-3 text-h2 font-serif text-[var(--text-primary)] text-start leading-tight">'
  );

  fs.writeFileSync(filePath, content, 'utf-8');
  console.log(`✅ ${path.basename(filePath)}: Заголовки переведены в размер text-h2 (40px)!`);
}

processFile(path.join(ABOUT_DIR, 'AboutPrinciplesSection.tsx'));
processFile(path.join(ABOUT_DIR, 'AboutPhilosophySection.tsx'));


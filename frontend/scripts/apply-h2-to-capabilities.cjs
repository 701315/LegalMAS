const fs = require('fs');
const path = require('path');

const capPath = path.join(__dirname, '../src/marketing/components/security/SecurityCapabilitiesSection.tsx');

if (fs.existsSync(capPath)) {
  let content = fs.readFileSync(capPath, 'utf-8');

  // Заменяем класс заголовка h3 на чистый text-h2 (40px, Instrument Serif)
  content = content.replace(
    /<h3[^>]*className=["'][^"']*["'][^>]*>/g,
    '<h3 className="mt-3 text-h2 font-serif text-[var(--text-primary)] text-start leading-tight">'
  );

  fs.writeFileSync(capPath, content, 'utf-8');
  console.log('✅ Все 6 заголовков возможностей переведены в размер text-h2 (40px)!');
}

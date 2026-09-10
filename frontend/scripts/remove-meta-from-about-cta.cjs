const fs = require('fs');
const path = require('path');

const ctaPath = path.join(__dirname, '../src/marketing/components/about/AboutCTASection.tsx');

if (fs.existsSync(ctaPath)) {
  let content = fs.readFileSync(ctaPath, 'utf-8');

  // Удаляем абзац с about.cta.meta
  content = content.replace(
    /\s*<p[^>]*>\s*\{t\('about\.cta\.meta'\)\}\s*<\/p>/g,
    ''
  );

  fs.writeFileSync(ctaPath, content, 'utf-8');
  console.log('✅ AboutCTASection.tsx: Строка {t("about.cta.meta")} успешно удалена из компонента!');
}

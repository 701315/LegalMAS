const fs = require('fs');
const path = require('path');

const corpPath = path.join(__dirname, '../src/marketing/pages/solutions/CorporateLegalPage.tsx');

if (fs.existsSync(corpPath)) {
  let content = fs.readFileSync(corpPath, 'utf-8');

  // 1. Делаем "What the legal department gets" крупным главным заголовком секции H2
  content = content.replace(
    /<p className="text-eyebrow mb-4 text-start">\s*\{t\("solutions\.corporateLegal\.outcomes\.eyebrow"\)\}\s*<\/p>/g,
    `<h2 className="text-h1 mb-12 text-start text-[var(--text-primary)] font-serif">
          {t("solutions.corporateLegal.outcomes.eyebrow")}
        </h2>`
  );

  // 2. Делаем "Where overload occurs" крупным главным заголовком секции H2
  content = content.replace(
    /<p className="text-eyebrow mb-4 text-start">\s*\{t\("solutions\.corporateLegal\.pressure\.eyebrow"\)\}\s*<\/p>/g,
    `<h2 className="text-h1 mb-12 text-start text-[var(--text-primary)] font-serif">
          {t("solutions.corporateLegal.pressure.eyebrow")}
        </h2>`
  );

  // 3. Поднимаем визуальный кегль всех карточек в Pressure и Outcomes с text-h3 до text-h2
  content = content.replace(
    /<h2 className="text-h3 font-serif italic text-\[var\(--text-primary\)\] text-start">/g,
    '<h2 className="text-h2 font-serif italic text-[var(--text-primary)] text-start mb-3 leading-tight">'
  );

  fs.writeFileSync(corpPath, content, 'utf-8');
  console.log('✅ CorporateLegalPage.tsx: Заголовки "Where overload occurs" и "What the legal department gets" + все 9 карточек переведены на крупные H2!');
}

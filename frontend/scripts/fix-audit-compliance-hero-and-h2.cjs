const fs = require('fs');
const path = require('path');

const acPath = path.join(__dirname, '../src/marketing/pages/solutions/AuditCompliancePage.tsx');

if (fs.existsSync(acPath)) {
  let content = fs.readFileSync(acPath, 'utf-8');

  // 1. Делаем заголовок Hero чисто белым (!text-white)
  content = content.replace(
    /className="mt-10 font-serif text-[a-z0-9-]+ text-\[var\(--text-inverse\)\] whitespace-pre-line"/g,
    'className="mt-10 font-serif text-display !text-white whitespace-pre-line"'
  );

  content = content.replace(
    /\{t\("solutions\.internalAudit\.hero\.titlePart1"\)\}/g,
    '<span className="!text-white">{t("solutions.internalAudit.hero.titlePart1")}</span>'
  );

  // 2. Переводим заголовки карточек VisualCardsSection в h2 (Unified Checklist, Audit Trail, Period Comparison)
  content = content.replace(
    /<h3 className="text-h3 font-serif italic text-\[var\(--text-primary\)\] text-start">\s*\{card\.title\}\s*<\/h3>/g,
    `<h2 className="text-h2 font-serif italic text-[var(--text-primary)] text-start mb-3 leading-tight">
                  {card.title}
                </h2>`
  );

  // Дополнительная замена, если карточки рендерятся через h3
  content = content.replace(
    /<h3 className="text-h3 italic text-start">\s*\{card\.title\}\s*<\/h3>/g,
    `<h2 className="text-h2 font-serif italic text-[var(--text-primary)] text-start mb-3 leading-tight">
                  {card.title}
                </h2>`
  );

  fs.writeFileSync(acPath, content, 'utf-8');
  console.log('✅ AuditCompliancePage.tsx: Заголовок Hero сделан белым, а карточки переведены в h2!');
}

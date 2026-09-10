const fs = require('fs');
const path = require('path');

const acPath = path.join(__dirname, '../src/marketing/pages/solutions/AuditCompliancePage.tsx');

if (fs.existsSync(acPath)) {
  let content = fs.readFileSync(acPath, 'utf-8');

  // 1. CapabilitiesSection: h3 -> h2 с font-serif italic
  content = content.replace(
    /<h3 className="text-h3 italic text-start">\s*\{item\.title\}\s*<\/h3>/g,
    `<h2 className="text-h3 font-serif italic text-[var(--text-primary)] text-start">
                        {item.title}
                      </h2>`
  );

  // 2. AuditRoutinesIntroSection: text-base font-light -> text-body
  content = content.replace(
    /className="space-y-6 text-base leading-relaxed text-\[var\(--text-secondary\)\] font-light"/g,
    'className="space-y-6 text-body leading-relaxed text-[var(--text-secondary)]"'
  );

  // 3. SignalsSection: убрать font-light
  content = content.replace(
    /className="mt-5 text-body-sm leading-relaxed text-\[var\(--text-secondary\)\] font-light max-w-md text-start"/g,
    'className="mt-5 text-body-sm leading-relaxed text-[var(--text-secondary)] max-w-md text-start"'
  );

  // 4. CTASection: font-light opacity-60 -> font-normal
  content = content.replace(
    /className="italic font-light opacity-60 text-\[var\(--accent-primary\)\]"/g,
    'className="italic font-normal text-[var(--accent-primary)]"'
  );

  // 5. HeroSection: убрать лишний span !text-white (h1 уже !text-white)
  content = content.replace(
    /<span className="!text-white">\{t\("solutions\.internalAudit\.hero\.titlePart1"\)\}<\/span>/g,
    '{t("solutions.internalAudit.hero.titlePart1")}'
  );

  fs.writeFileSync(acPath, content, 'utf-8');
  console.log('✅ AuditCompliancePage.tsx: Все правки применены!');
  console.log('   • Capabilities: h3 -> h2 (font-serif italic)');
  console.log('   • Intro: text-base font-light -> text-body');
  console.log('   • Signals: font-light убран');
  console.log('   • CTA: font-light opacity-60 -> font-normal');
  console.log('   • Hero: лишний span убран');
}

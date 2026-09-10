const fs = require('fs');
const path = require('path');

const SOLUTIONS_DIR = path.join(__dirname, '../src/marketing/pages/solutions');
const files = fs.readdirSync(SOLUTIONS_DIR).filter(f => f.endsWith('.tsx'));

console.log('\n===============================================================');
console.log('🛠️  ПРИМЕНЕНИЕ СИСТЕМНЫХ ТОКЕНОВ ДИЗАЙН-СИСТЕМЫ К SOLUTIONS');
console.log('===============================================================\n');

files.forEach(file => {
  const filePath = path.join(SOLUTIONS_DIR, file);
  let content = fs.readFileSync(filePath, 'utf-8');
  let original = content;

  // 1. Системные переменные цветов и фонов
  content = content.replace(/\bclassName="min-h-screen bg-base text-primary"/g, 'className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)]"');
  content = content.replace(/\bclassName="min-h-screen bg-base text-primary selection:bg-accent selection:text-white"/g, 'className="min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)] selection:bg-[var(--accent-primary)] selection:text-white"');
  content = content.replace(/className="bg-base"/g, 'className="bg-[var(--bg-base)]"');
  content = content.replace(/className="bg-card"/g, 'className="bg-[var(--bg-surface)]"');
  content = content.replace(/border-border/g, 'border-[var(--border-color)]');
  content = content.replace(/border-[#EAE6DF]/g, 'border-[var(--border-color)]');
  
  // 2. Системные цвета текста
  content = content.replace(/\btext-primary\b/g, 'text-[var(--text-primary)]');
  content = content.replace(/\btext-secondary\b/g, 'text-[var(--text-secondary)]');
  content = content.replace(/\btext-muted\b/g, 'text-[var(--text-muted)]');
  content = content.replace(/\btext-accent\b/g, 'text-[var(--accent-primary)]');
  content = content.replace(/\bbg-surface\b/g, 'bg-[var(--bg-surface)]');

  // 3. Выравнивание контрастности текстов на темных фонах
  content = content.replace(/text-white\/72 font-light/g, '!text-[#D6D0C7] font-medium');
  content = content.replace(/text-white\/70 font-light/g, '!text-[#D6D0C7] font-medium');
  content = content.replace(/text-white\/70/g, 'text-[var(--text-secondary)]');
  content = content.replace(/font-light text-start/g, 'text-start');

  // 4. Оптимизация начертания Instrument Serif в заголовках
  content = content.replace(/italic font-light text-\[var\(--accent-primary\)\]/g, 'italic font-normal text-[var(--accent-primary)]');
  content = content.replace(/italic font-light text-accent/g, 'italic font-normal text-[var(--accent-primary)]');

  // 5. Точечные исправления по файлам

  // AuditCompliancePage: поднимаем заголовок Hero до text-display
  if (file === 'AuditCompliancePage.tsx') {
    content = content.replace(
      /className="mt-10 font-serif text-h1 text-\[var\(--text-inverse\)\] whitespace-pre-line"/g,
      'className="mt-10 font-serif text-display text-[var(--text-inverse)] whitespace-pre-line"'
    );
    // Очищаем оставшиеся font-light у параграфов
    content = content.replace(
      /className="mt-8 max-w-xl text-base leading-relaxed text-white\/72 font-light text-start"/g,
      'className="mt-8 max-w-xl text-body !text-[#D6D0C7] text-start"'
    );
    content = content.replace(
      /className="space-y-6 text-base leading-relaxed text-\[var\(--text-secondary\)\] font-light"/g,
      'className="space-y-6 text-body leading-relaxed text-[var(--text-secondary)]"'
    );
    content = content.replace(
      /className="mt-5 text-body-sm leading-relaxed text-\[var\(--text-secondary\)\] font-light/g,
      'className="mt-5 text-body-sm leading-relaxed text-[var(--text-secondary)]'
    );
  }

  // CompliancePage: убираем font-light из описания Hero
  if (file === 'CompliancePage.tsx') {
    content = content.replace(
      /className="text-body leading-relaxed text-white\/70 font-light text-start"/g,
      'className="text-body leading-relaxed !text-[#D6D0C7] text-start"'
    );
  }

  // CorporateLegalPage и LawFirmsPage: чистим лишние теги и классы
  if (file === 'CorporateLegalPage.tsx' || file === 'LawFirmsPage.tsx') {
    content = content.replace(/font-serif text-h1/g, 'text-h1');
    content = content.replace(/font-serif text-h3/g, 'text-h3');
    content = content.replace(/text-white\/55/g, 'text-[var(--text-muted)]');
  }

  // InternalAuditPage и MaDueDiligencePage: убираем font-light из интро-текста
  if (file === 'InternalAuditPage.tsx' || file === 'MaDueDiligencePage.tsx') {
    content = content.replace(
      /className="text-body leading-relaxed text-\[var\(--text-secondary\)\] font-light text-start"/g,
      'className="text-body leading-relaxed text-[var(--text-secondary)] text-start"'
    );
  }

  if (content !== original) {
    fs.writeFileSync(filePath, content, 'utf-8');
    console.log(`✅ ${file}: успешно обновлен и приведен к дизайн-системе!`);
  } else {
    console.log(`✨ ${file}: уже в идеальном состоянии.`);
  }
});

console.log('\n===============================================================');
console.log('🎉 РЕФАКТОРИНГ СТРАНИЦ SOLUTIONS ЗАВЕРШЕН!');
console.log('===============================================================\n');

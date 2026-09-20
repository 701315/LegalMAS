const fs = require('fs');
const path = require('path');

const aboutProcPath = path.join(__dirname, '../src/marketing/components/about/AboutProcessSection.tsx');

if (fs.existsSync(aboutProcPath)) {
  let content = fs.readFileSync(aboutProcPath, 'utf-8');

  // Обновляем заголовки 4 шагов до text-h2 (40px, Instrument Serif)
  content = content.replace(
    /<h3[^>]*className=["'][^"']*["'][^>]*>/g,
    '<h3 className="mt-3 text-h2 font-serif !text-white text-start leading-tight">'
  );

  fs.writeFileSync(aboutProcPath, content, 'utf-8');
  console.log('✅ О нас (AboutProcessSection.tsx): Заголовки Document Array, Instructions, Verification, Result успешно переведены в размер text-h2!');
}

// Проверим также, есть ли аналогичный Workflow в Платформе
const platWorkPath = path.join(__dirname, '../src/marketing/components/platform/PlatformWorkflowSection.tsx');
if (fs.existsSync(platWorkPath)) {
  let content = fs.readFileSync(platWorkPath, 'utf-8');

  content = content.replace(
    /<h3[^>]*className=["'][^"']*["'][^>]*>/g,
    '<h3 className="mt-3 text-h2 font-serif text-[var(--text-primary)] text-start leading-tight">'
  );

  fs.writeFileSync(platWorkPath, content, 'utf-8');
  console.log('✅ Платформа (PlatformWorkflowSection.tsx): Заголовки шагов процесса также переведены в размер text-h2!');
}


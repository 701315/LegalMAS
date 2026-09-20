const fs = require('fs');
const path = require('path');

const methodPath = path.join(__dirname, '../src/marketing/components/platform/PlatformMethodologySection.tsx');

if (fs.existsSync(methodPath)) {
  let content = fs.readFileSync(methodPath, 'utf-8');

  // 1. Делаем надзаголовок (Eyebrow) светлым акцентным
  content = content.replace(
    /className=["']eyebrow text-start["']/g,
    'className="eyebrow !text-[var(--accent-primary)] brightness-110 text-start"'
  );

  // 2. Делаем главный заголовок h2 ярко-белым (inverse)
  content = content.replace(
    /className=["']mt-4 text-h1 text-start["']/g,
    'className="mt-4 text-h1 !text-white text-start"'
  );
  content = content.replace(
    /className=["']mt-4 font-serif text-h1 text-\[var\(--text-primary\)\] text-start["']/g,
    'className="mt-4 text-h1 !text-white text-start"'
  );

  // 3. Делаем подзаголовок (lead-in курсив) светлым
  content = content.replace(
    /className=["']mt-6 font-serif text-h3 italic text-\[var\(--text-primary\)\] text-start["']/g,
    'className="mt-6 font-serif text-h3 italic !text-white/90 text-start"'
  );

  // 4. Делаем основной текст описания светлым читаемым
  content = content.replace(
    /className=["']text-body leading-relaxed text-\[var\(--text-secondary\)\] text-start["']/g,
    'className="text-body leading-relaxed !text-[#D6D0C7] text-start"'
  );

  fs.writeFileSync(methodPath, content, 'utf-8');
  console.log('✅ PlatformMethodologySection.tsx: заголовок и текст успешно переведены в светлый режим!');
}

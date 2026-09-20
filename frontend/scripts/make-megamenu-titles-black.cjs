const fs = require('fs');
const path = require('path');

const headerPath = path.join(__dirname, '../src/marketing/components/shared/SiteHeader.tsx');

if (fs.existsSync(headerPath)) {
  let content = fs.readFileSync(headerPath, 'utf-8');

  // Делаем заголовки ссылок в выпадающем меню насыщенно черными
  content = content.replace(
    /className=["']text-body-sm font-semibold text-\[var\(--text-primary\)\] group-hover:text-\[var\(--accent-primary\)\] transition-colors["']/g,
    'className="text-body-sm font-semibold !text-[#1A1917] group-hover:!text-[var(--accent-primary)] transition-colors"'
  );

  // На случай альтернативного синтаксиса
  content = content.replace(
    /className=["']text-body-sm font-semibold text-gray-900 group-hover:text-\[var\(--accent-primary\)\] transition-colors["']/g,
    'className="text-body-sm font-semibold !text-[#1A1917] group-hover:!text-[var(--accent-primary)] transition-colors"'
  );

  fs.writeFileSync(headerPath, content, 'utf-8');
  console.log('✅ SiteHeader.tsx: Названия страниц в выпадающем мегаменю сделаны четко черными!');
}

const fs = require('fs');
const path = require('path');

const headerPath = path.join(__dirname, '../src/marketing/components/shared/SiteHeader.tsx');

if (fs.existsSync(headerPath)) {
  let content = fs.readFileSync(headerPath, 'utf-8');

  // Делаем названия страниц жирными (!font-bold) и насыщенно черными (!text-[#1A1917])
  content = content.replace(
    /className=["']text-body-sm font-semibold !text-\[#1A1917\] group-hover:!text-\[var\(--accent-primary\)\] transition-colors["']/g,
    'className="text-body-sm !font-bold !text-[#1A1917] group-hover:!text-[var(--accent-primary)] transition-colors"'
  );

  // Дополнительная замена для старых вхождений
  content = content.replace(
    /className=["']text-body-sm font-semibold text-\[var\(--text-primary\)\] group-hover:text-\[var\(--accent-primary\)\] transition-colors["']/g,
    'className="text-body-sm !font-bold !text-[#1A1917] group-hover:!text-[var(--accent-primary)] transition-colors"'
  );

  fs.writeFileSync(headerPath, content, 'utf-8');
  console.log('✅ SiteHeader.tsx: Названия страниц в мегаменю сделаны ЧЁРНЫМИ и ЖИРНЫМИ (!font-bold !text-[#1A1917])');
}

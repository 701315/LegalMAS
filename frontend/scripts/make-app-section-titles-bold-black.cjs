const fs = require('fs');
const path = require('path');

const appPath = path.join(__dirname, '../src/marketing/components/home/ApplicationSection/ApplicationSection.tsx');

if (fs.existsSync(appPath)) {
  let content = fs.readFileSync(appPath, 'utf-8');

  // Делаем название каждой страницы жирным и черным (!font-bold !text-[#1A1917])
  content = content.replace(
    /className=["']text-body-sm font-semibold text-\[var\(--text-primary\)\] group-hover\/item:text-\[var\(--accent-primary\)\] transition-colors["']/g,
    'className="text-body-sm !font-bold !text-[#1A1917] group-hover/item:!text-[var(--accent-primary)] transition-colors"'
  );

  fs.writeFileSync(appPath, content, 'utf-8');
  console.log('✅ ApplicationSection.tsx: Заголовки страниц в раскрывающемся модальном окне сделаны ЧЁРНЫМИ и ЖИРНЫМИ (!font-bold !text-[#1A1917])!');
}

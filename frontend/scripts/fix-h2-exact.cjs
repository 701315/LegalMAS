const fs = require('fs');
const path = require('path');

const files = [
  'src/marketing/pages/solutions/MaDueDiligencePage.tsx',
  'src/marketing/pages/solutions/ContractReviewPage.tsx',
  'src/marketing/pages/solutions/InternalAuditPage.tsx'
];

files.forEach(rel => {
  const filePath = path.join(__dirname, '..', rel);
  if (!fs.existsSync(filePath)) return;

  let content = fs.readFileSync(filePath, 'utf-8');

  // Заменяем strong на h2
  content = content.replace(
    /<strong className="text-\[var\(--text-primary\)\] block mb-2 font-serif italic text-lg tracking-tight">/g,
    '<h2 className="text-h3 font-serif italic text-[var(--text-primary)] block mb-2 tracking-tight">'
  );
  content = content.replace(/<\/strong>/g, '</h2>');

  // Меняем внешнюю обертку <p> на <div>, чтобы HTML был валидным (h2 внутри div, а не p)
  content = content.replace(
    /<p className="text-body-sm text-start">\s*<h2/g,
    '<div className="text-start">\n                    <h2'
  );

  fs.writeFileSync(filePath, content, 'utf-8');
  console.log(`✅ ${rel}: Заголовки переведены в <h2>!`);
});

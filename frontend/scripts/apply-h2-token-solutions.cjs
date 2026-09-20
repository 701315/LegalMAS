const fs = require('fs');
const path = require('path');

const files = [
  'src/marketing/pages/solutions/MaDueDiligencePage.tsx',
  'src/marketing/pages/solutions/ContractReviewPage.tsx',
  'src/marketing/pages/solutions/InternalAuditPage.tsx'
];

console.log('\n===============================================================');
console.log('👑 ПРИМЕНЕНИЕ КЛАССА text-h2 К ЗАГОЛОВКАМ КАРТОЧЕК');
console.log('===============================================================\n');

files.forEach(rel => {
  const filePath = path.join(__dirname, '..', rel);
  if (!fs.existsSync(filePath)) return;

  let content = fs.readFileSync(filePath, 'utf-8');

  // Заменяем класс на системный text-h3 lg:text-h2
  content = content.replace(
    /className="text-\[var\(--text-primary\)\] block mb-2 font-serif italic text-lg tracking-tight"/g,
    'className="text-h3 lg:text-h2 font-serif italic text-[var(--text-primary)] block mb-3 tracking-tight"'
  );
  content = content.replace(
    /className="text-h3 font-serif italic text-\[var\(--text-primary\)\] block mb-2 tracking-tight"/g,
    'className="text-h3 lg:text-h2 font-serif italic text-[var(--text-primary)] block mb-3 tracking-tight"'
  );
  content = content.replace(
    /font-serif italic text-lg tracking-tight/g,
    'text-h3 lg:text-h2 font-serif italic tracking-tight'
  );

  fs.writeFileSync(filePath, content, 'utf-8');
  console.log(`✅ ${rel}: класс выровнен на text-h3 lg:text-h2!`);
});

console.log('\n===============================================================\n');

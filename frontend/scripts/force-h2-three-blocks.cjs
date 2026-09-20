const fs = require('fs');
const path = require('path');

const files = [
  'src/marketing/pages/solutions/MaDueDiligencePage.tsx',
  'src/marketing/pages/solutions/ContractReviewPage.tsx',
  'src/marketing/pages/solutions/InternalAuditPage.tsx'
];

console.log('\n===============================================================');
console.log('🛠️ ПРИНУДИТЕЛЬНЫЙ ПЕРЕВОД ЗАГОЛОВКОВ В H2');
console.log('===============================================================\n');

files.forEach(rel => {
  const filePath = path.join(__dirname, '..', rel);
  if (!fs.existsSync(filePath)) return;

  let content = fs.readFileSync(filePath, 'utf-8');
  let original = content;

  // 1. Заменяем обертку <p> + <strong ...>на <div ...> + <h2 ...>
  // Для item.title (MaDueDiligencePage, InternalAuditPage)
  content = content.replace(
    /<p className="text-body-sm text-start">[\s\S]*?<strong className="text-\[var\(--text-primary\)\] block mb-2 font-serif italic text-lg tracking-tight">[\s\S]*?\{item\.title\}[\s\S]*?<\/strong>[\s\S]*?\{item\.text\}[\s\S]*?<\/p>/g,
    `<div className="text-start">
                    <h2 className="text-h3 font-serif italic text-[var(--text-primary)] block mb-2 tracking-tight">
                      {item.title}
                    </h2>
                    <p className="text-body-sm text-[var(--text-secondary)]">
                      {item.text}
                    </p>
                  </div>`
  );

  // Для block.title (ContractReviewPage)
  content = content.replace(
    /<p className="text-body-sm text-start">[\s\S]*?<strong className="text-\[var\(--text-primary\)\] block mb-2 font-serif italic text-lg tracking-tight">[\s\S]*?\{block\.title\}[\s\S]*?<\/strong>[\s\S]*?\{block\.text\}[\s\S]*?<\/p>/g,
    `<div className="text-start">
                    <h2 className="text-h3 font-serif italic text-[var(--text-primary)] block mb-2 tracking-tight">
                      {block.title}
                    </h2>
                    <p className="text-body-sm text-[var(--text-secondary)]">
                      {block.text}
                    </p>
                  </div>`
  );

  // Универсальная замена, если первичное регулярное выражение не зацепило
  if (content === original) {
    content = content.replace(
      /<strong className="text-\[var\(--text-primary\)\] block mb-2 font-serif italic text-lg tracking-tight">/g,
      '<h2 className="text-h3 font-serif italic text-[var(--text-primary)] block mb-2 tracking-tight">'
    );
    content = content.replace(/<\/strong>/g, '</h2>');
  }

  if (content !== original) {
    fs.writeFileSync(filePath, content, 'utf-8');
    console.log(`✅ ${rel}: Заголовки "Volume and Format", "Focus and Directions", "Data Systematization" теперь семантические <h2 className="text-h3">!`);
  } else {
    console.log(`⚠️ ${rel}: Совпадение не найдено, проверяем код напрямую...`);
  }
});

console.log('\n===============================================================\n');

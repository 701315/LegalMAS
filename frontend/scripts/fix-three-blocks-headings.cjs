const fs = require('fs');
const path = require('path');

const targets = [
  'src/marketing/pages/solutions/MaDueDiligencePage.tsx',
  'src/marketing/pages/solutions/ContractReviewPage.tsx',
  'src/marketing/pages/solutions/InternalAuditPage.tsx'
];

console.log('\n===============================================================');
console.log('🛠️  ПЕРЕВОД ЗАГОЛОВКОВ КАРТОЧЕК НА СЕМАНТИЧЕСКИЙ H2');
console.log('===============================================================\n');

targets.forEach(rel => {
  const filePath = path.join(__dirname, '..', rel);
  if (!fs.existsSync(filePath)) {
    console.log(`⚠️ Файл не найден: ${rel}`);
    return;
  }

  let content = fs.readFileSync(filePath, 'utf-8');
  let updated = false;

  // 1. Исправление MaDueDiligencePage.tsx и InternalAuditPage.tsx (используют {item.title} и {item.text})
  const patternItem = /<p className="text-body-sm text-start">\s*<strong className="text-\[var\(--text-primary\)\] block mb-2 font-serif italic text-lg tracking-tight">\s*\{item\.title\}\s*<\/strong>\s*\{item\.text\}\s*<\/p>/g;
  if (patternItem.test(content)) {
    content = content.replace(patternItem, 
`<div className="text-start">
                    <h2 className="text-[var(--text-primary)] block mb-2 font-serif italic text-lg tracking-tight">
                      {item.title}
                    </h2>
                    <p className="text-body-sm text-[var(--text-secondary)]">
                      {item.text}
                    </p>
                  </div>`
    );
    updated = true;
  }

  // 2. Исправление ContractReviewPage.tsx (использует {block.title} и {block.text})
  const patternBlock = /<p className="text-body-sm text-start">\s*<strong className="text-\[var\(--text-primary\)\] block mb-2 font-serif italic text-lg tracking-tight">\s*\{block\.title\}\s*<\/strong>\s*\{block\.text\}\s*<\/p>/g;
  if (patternBlock.test(content)) {
    content = content.replace(patternBlock, 
`<div className="text-start">
                    <h2 className="text-[var(--text-primary)] block mb-2 font-serif italic text-lg tracking-tight">
                      {block.title}
                    </h2>
                    <p className="text-body-sm text-[var(--text-secondary)]">
                      {block.text}
                    </p>
                  </div>`
    );
    updated = true;
  }

  if (updated) {
    fs.writeFileSync(filePath, content, 'utf-8');
    console.log(`✅ ${rel}: Заголовки успешно переведены на <h2>`);
  } else {
    console.log(`✨ ${rel}: Заголовки уже используют правильную семантику или не совпали с паттерном.`);
  }
});

console.log('\n===============================================================\n');

const fs = require('fs');
const path = require('path');

const corpPath = path.join(__dirname, '../src/marketing/pages/solutions/CorporateLegalPage.tsx');

if (fs.existsSync(corpPath)) {
  let content = fs.readFileSync(corpPath, 'utf-8');

  // 1. Убираем импорты Reveal, если остались
  content = content.replace(/import\s+.*Reveal.*from\s+["'][^"']+["'];?\n?/g, '');

  // 2. Заменяем теги <Reveal> и <RevealItem> на простые <div>
  content = content.replace(/<Reveal>/g, '<div className="w-full">');
  content = content.replace(/<\/Reveal>/g, '</div>');
  content = content.replace(/<RevealItem key=\{([^}]+)\}>/g, '<div key={$1}>');
  content = content.replace(/<RevealItem>/g, '<div>');
  content = content.replace(/<\/RevealItem>/g, '</div>');

  fs.writeFileSync(corpPath, content, 'utf-8');
  console.log('✅ CorporateLegalPage.tsx: Теги Reveal/RevealItem успешно убраны, JSX чистый!');
}

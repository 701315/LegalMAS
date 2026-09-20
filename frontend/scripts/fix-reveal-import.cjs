const fs = require('fs');
const path = require('path');

const corpPath = path.join(__dirname, '../src/marketing/pages/solutions/CorporateLegalPage.tsx');

// Поиск Reveal в src
function findReveal(dir) {
  const list = fs.readdirSync(dir);
  for (const file of list) {
    const filePath = path.join(dir, file);
    const stat = fs.statSync(filePath);
    if (stat.isDirectory()) {
      const res = findReveal(filePath);
      if (res) return res;
    } else if (file.toLowerCase().includes('reveal')) {
      return filePath;
    }
  }
  return null;
}

const revealPath = findReveal(path.join(__dirname, '../src'));

if (revealPath && fs.existsSync(corpPath)) {
  const pageDir = path.dirname(corpPath);
  let relPath = path.relative(pageDir, revealPath).replace(/\\/g, '/');
  if (!relPath.startsWith('.')) relPath = './' + relPath;
  relPath = relPath.replace(/\.tsx?$/, '');

  let content = fs.readFileSync(corpPath, 'utf-8');
  content = content.replace(/import Reveal, \{ RevealItem \} from "[^"]+";/, `import Reveal, { RevealItem } from "${relPath}";`);

  fs.writeFileSync(corpPath, content, 'utf-8');
  console.log(`✅ Импорт Reveal успешно обновлен на "${relPath}"`);
} else {
  // Если компонента Reveal отдельного нет, заменим обертки Reveal на чистые контейнеры
  let content = fs.readFileSync(corpPath, 'utf-8');
  content = content.replace(/import Reveal, \{ RevealItem \} from "[^"]+";\n?/, '');
  content = content.replace(/<Reveal>/g, '<div>');
  content = content.replace(/<\/Reveal>/g, '</div>');
  content = content.replace(/<RevealItem[^>]*>/g, '<div>');
  content = content.replace(/<\/RevealItem>/g, '</div>');

  fs.writeFileSync(corpPath, content, 'utf-8');
  console.log('✅ Обертки Reveal приведены к чистым HTML-тегам');
}

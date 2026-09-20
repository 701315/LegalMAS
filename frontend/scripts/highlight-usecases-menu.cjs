const fs = require('fs');
const path = require('path');

const SHARED_DIR = path.join(__dirname, '../src/marketing/components/shared');

function findAndFixHeader(dir) {
  if (!fs.existsSync(dir)) return;
  const files = fs.readdirSync(dir);

  for (const file of files) {
    const fullPath = path.join(dir, file);
    if (fs.statSync(fullPath).isDirectory()) {
      findAndFixHeader(fullPath);
      continue;
    }

    if (file.endsWith('.tsx') || file.endsWith('.ts')) {
      let content = fs.readFileSync(fullPath, 'utf-8');

      // Ищем место рендеринга заголовка карточки меню Use Cases
      if (content.includes('nav') || content.includes('useCases') || content.includes('UseCases') || content.includes('menu')) {
        let updated = false;

        // Делаем заголовок каждого пункта черным и жирным
        if (content.includes('font-medium') || content.includes('text-sm')) {
          // Заменяем класс названия пункта меню
          const newContent = content.replace(
            /className=["']([^"']*text-body-sm[^"']*|[^"']*text-sm[^"']*) font-medium ([^"']*)["']/g,
            'className="$1 font-semibold text-[var(--text-primary)] $2"'
          );
          if (newContent !== content) {
            content = newContent;
            updated = true;
          }
        }

        if (updated) {
          fs.writeFileSync(fullPath, content, 'utf-8');
          console.log(`✅ Названия пунктов меню в ${file} успешно обновлены на полужирный черный!`);
        }
      }
    }
  }
}

findAndFixHeader(SHARED_DIR);

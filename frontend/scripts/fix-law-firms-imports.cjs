const fs = require('fs');
const path = require('path');

const lawPath = path.join(__dirname, '../src/marketing/pages/solutions/LawFirmsPage.tsx');

if (fs.existsSync(lawPath)) {
  let content = fs.readFileSync(lawPath, 'utf-8');

  // Исправляем относительно src/marketing/pages/solutions/ -> ../../components/
  content = content.replace(/from "\.\.\/\.\.\/\.\.\/components\//g, 'from "../../components/');

  fs.writeFileSync(lawPath, content, 'utf-8');
  console.log('✅ LawFirmsPage.tsx: Пути импорта успешно исправлены!');
}

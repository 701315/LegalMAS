const fs = require('fs');
const path = require('path');

// 1. Проверяем ContactModalContext
const contextPath = path.join(__dirname, '../src/context/ContactModalContext.tsx');
let hasContext = fs.existsSync(contextPath);
console.log(`ContactModalContext exists: ${hasContext}`);

// 2. Исправляем CounterpartiesPage.tsx
const cpPath = path.join(__dirname, '../src/marketing/pages/solutions/CounterpartiesPage.tsx');
if (fs.existsSync(cpPath)) {
  let content = fs.readFileSync(cpPath, 'utf-8');

  // Заменяем локальное состояние на useContactModal hook или пропсы
  if (content.includes('ContactModal')) {
    // Проверяем как импортируется useContactModal на других страницах
    content = content.replace(
      /import ContactModal from "[^"]+";/g,
      'import { useContactModal } from "../../context/ContactModalContext";'
    );

    content = content.replace(
      /const \[contactModalOpen, setContactModalOpen\] = React\.useState\(false\);[\s\S]*?const closeContactModal = \(\) => setContactModalOpen\(false\);/g,
      'const { openContactModal } = useContactModal();'
    );

    content = content.replace(/onDemo=\{openContactModal\}/g, 'onDemo={openContactModal}');
    content = content.replace(/<ContactModal[\s\S]*?\/>/g, '');

    fs.writeFileSync(cpPath, content, 'utf-8');
    console.log('✅ CounterpartiesPage.tsx исправлен для использования useContactModal()!');
  }
}

// 3. Исправляем RealEstatePage.tsx
const rePath = path.join(__dirname, '../src/marketing/pages/solutions/RealEstatePage.tsx');
if (fs.existsSync(rePath)) {
  let content = fs.readFileSync(rePath, 'utf-8');

  if (content.includes('ContactModal')) {
    content = content.replace(
      /import ContactModal from "[^"]+";/g,
      'import { useContactModal } from "../../context/ContactModalContext";'
    );

    content = content.replace(
      /const \[contactModalOpen, setContactModalOpen\] = React\.useState\(false\);[\s\S]*?const closeContactModal = \(\) => setContactModalOpen\(false\);/g,
      'const { openContactModal } = useContactModal();'
    );

    content = content.replace(/onDemo=\{openContactModal\}/g, 'onDemo={openContactModal}');
    content = content.replace(/<ContactModal[\s\S]*?\/>/g, '');

    fs.writeFileSync(rePath, content, 'utf-8');
    console.log('✅ RealEstatePage.tsx исправлен для использования useContactModal()!');
  }
}

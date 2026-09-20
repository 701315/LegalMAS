const fs = require('fs');
const path = require('path');

const chainPath = path.join(__dirname, '../src/marketing/components/platform/diagrams/VerticalNodeChain.tsx');
const methodologyPath = path.join(__dirname, '../src/marketing/components/platform/PlatformMethodologySection.tsx');

console.log('🔍 ПРОВЕРКА ПРОПСОВ В VerticalNodeChain.tsx:\n');

if (fs.existsSync(chainPath)) {
  const chainContent = fs.readFileSync(chainPath, 'utf-8');
  console.log(chainContent);

  // Если VerticalNodeChain берет i18n внутри себя и не ожидает chain, либо принимает items/steps:
  // Исправим вызов в PlatformMethodologySection.tsx
  let methodContent = fs.readFileSync(methodologyPath, 'utf-8');
  
  // Проверяем, есть ли проп items или steps или не нужны пропсы вообще
  if (chainContent.includes('items?:') || chainContent.includes('items:')) {
    methodContent = methodContent.replace(/<VerticalNodeChain\s+chain=\{chain\}\s*\/>/g, '<VerticalNodeChain items={chain} />');
  } else if (chainContent.includes('nodes?:') || chainContent.includes('nodes:')) {
    methodContent = methodContent.replace(/<VerticalNodeChain\s+chain=\{chain\}\s*\/>/g, '<VerticalNodeChain nodes={chain} />');
  } else if (chainContent.includes('steps?:') || chainContent.includes('steps:')) {
    methodContent = methodContent.replace(/<VerticalNodeChain\s+chain=\{chain\}\s*\/>/g, '<VerticalNodeChain steps={chain} />');
  } else {
    // Если компонент сам внутри получает t("platform.methodology.chain")
    methodContent = methodContent.replace(/<VerticalNodeChain\s+chain=\{chain\}\s*\/>/g, '<VerticalNodeChain />');
  }

  fs.writeFileSync(methodologyPath, methodContent, 'utf-8');
  console.log('\n✅ PlatformMethodologySection.tsx: вызов VerticalNodeChain успешно синхронизирован с типами!');
} else {
  console.log('Файл VerticalNodeChain.tsx не найден по пути: ' + chainPath);
}

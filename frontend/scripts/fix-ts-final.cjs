const fs = require('fs');
const path = require('path');

// 1. Исправление SecurityCTASection.tsx
const secPath = path.join(__dirname, '../src/marketing/components/security/SecurityCTASection.tsx');
if (fs.existsSync(secPath)) {
  let content = fs.readFileSync(secPath, 'utf-8');
  content = content.replace(/\(p:\s*string,\s*idx:\s*number\)/g, '(p: string)');
  content = content.replace(/\(p,\s*idx\)/g, '(p)');
  fs.writeFileSync(secPath, content, 'utf-8');
  console.log('✅ SecurityCTASection.tsx: Неиспользуемый idx убран.');
}

// 2. Исправление FindingsDiagram.tsx
const diagPath = path.join(__dirname, '../src/marketing/components/platform/diagrams/FindingsDiagram.tsx');
if (fs.existsSync(diagPath)) {
  let content = fs.readFileSync(diagPath, 'utf-8');
  
  // Если у FindingsDiagram нет интерфейса или типа пропсов
  if (!content.includes('interface FindingsDiagramProps') && !content.includes('type FindingsDiagramProps')) {
    content = 'interface FindingsDiagramProps {\n  chain?: any[];\n}\n' + content;
    content = content.replace(/React\.FC/g, 'React.FC<FindingsDiagramProps>');
  } else if (!content.includes('chain?:')) {
    content = content.replace(/(interface|type)\s+FindingsDiagramProps[^{]*\{/, '$1 FindingsDiagramProps {\n  chain?: any[];');
  }

  fs.writeFileSync(diagPath, content, 'utf-8');
  console.log('✅ FindingsDiagram.tsx: Добавлен тип chain?: any[].');
}

const fs = require('fs');
const path = require('path');

// 1. Исправление RealEstatePage.tsx (убираем неиспользуемый PathCrumb)
const rePath = path.join(__dirname, '../src/marketing/pages/solutions/RealEstatePage.tsx');
if (fs.existsSync(rePath)) {
  let content = fs.readFileSync(rePath, 'utf-8');
  content = content.replace(/import PathCrumb from "\.\.\/\.\.\/components\/platform\/primitives\/PathCrumb";\n?/g, '');
  fs.writeFileSync(rePath, content, 'utf-8');
  console.log('✅ RealEstatePage.tsx: Неиспользуемый импорт PathCrumb убран.');
}

// 2. Исправление SecurityCTASection.tsx (убираем неиспользуемый индекс i)
const secCtaPath = path.join(__dirname, '../src/marketing/components/security/SecurityCTASection.tsx');
if (fs.existsSync(secCtaPath)) {
  let content = fs.readFileSync(secCtaPath, 'utf-8');
  content = content.replace(/\(p:\s*string,\s*i:\s*number\)/g, '(p: string, idx: number)');
  content = content.replace(/\(p,\s*i\)/g, '(p, idx)');
  // Если idx не используется в key, заменим на (p: string, idx: number) и используем key={idx}
  content = content.replace(/key=\{p\}/g, 'key={idx}');
  fs.writeFileSync(secCtaPath, content, 'utf-8');
  console.log('✅ SecurityCTASection.tsx: Параметр i устранён.');
}

// 3. Исправление FindingsDiagram.tsx / PlatformFindingsSection.tsx (добавляем chain в пропсы FindingsDiagram)
const findingsDiagPath = path.join(__dirname, '../src/marketing/components/platform/diagrams/FindingsDiagram.tsx');
if (fs.existsSync(findingsDiagPath)) {
  let content = fs.readFileSync(findingsDiagPath, 'utf-8');
  if (!content.includes('chain?:')) {
    content = content.replace(
      /interface FindingsDiagramProps \{/g,
      'interface FindingsDiagramProps {\n  chain?: any[];'
    );
    content = content.replace(
      /const FindingsDiagram: React\.FC<FindingsDiagramProps> = \(\{/g,
      'const FindingsDiagram: React.FC<FindingsDiagramProps> = ({ chain,'
    );
    fs.writeFileSync(findingsDiagPath, content, 'utf-8');
    console.log('✅ FindingsDiagram.tsx: Тип пропа chain успешно добавлен.');
  }
}

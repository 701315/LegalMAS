const fs = require('fs');
const path = require('path');

const SEC_DIR = path.join(__dirname, '../src/marketing/components/security');

function processFile(filePath, replacements) {
  if (!fs.existsSync(filePath)) return;
  let content = fs.readFileSync(filePath, 'utf-8');
  replacements.forEach(([regex, repl]) => {
    content = content.replace(regex, repl);
  });
  fs.writeFileSync(filePath, content, 'utf-8');
}

// 1. SecurityCapabilitiesSection.tsx
processFile(path.join(SEC_DIR, 'SecurityCapabilitiesSection.tsx'), [
  [/<span[^>]*className=["'][^"']*eyebrow[^"']*["'][^>]*>/g, '<span className="eyebrow text-start">'],
  [/<h2[^>]*>/g, '<h2 className="mt-4 text-h1 text-[var(--text-primary)] text-start">'],
  [/<h3[^>]*>/g, '<h3 className="text-h3 font-serif text-[var(--text-primary)] text-start">'],
  [/className=["'][^"']*text-body-sm leading-relaxed text-\[var\(--text-secondary\)\][^"']*["']/g, 'className="text-body leading-relaxed text-[var(--text-secondary)] text-start"']
]);

// 2. SecurityDeploymentSection.tsx
processFile(path.join(SEC_DIR, 'SecurityDeploymentSection.tsx'), [
  [/<span[^>]*className=["'][^"']*eyebrow[^"']*["'][^>]*>/g, '<span className="eyebrow text-start">'],
  [/<h2[^>]*>/g, '<h2 className="mt-4 text-h1 text-[var(--text-primary)] text-start">'],
  [/<h3[^>]*>/g, '<h3 className="mt-5 text-h3 font-serif text-[var(--text-primary)] text-start">'],
  [/className=["'][^"']*text-body-sm leading-relaxed text-\[var\(--text-secondary\)\][^"']*["']/g, 'className="text-body leading-relaxed text-[var(--text-secondary)] text-start"']
]);

// 3. SecurityFAQSection.tsx
processFile(path.join(SEC_DIR, 'SecurityFAQSection.tsx'), [
  [/<span[^>]*className=["'][^"']*eyebrow[^"']*["'][^>]*>/g, '<span className="eyebrow text-start">'],
  [/<h2[^>]*>/g, '<h2 className="mt-4 text-h1 text-[var(--text-primary)] text-start">'],
  [/className=["'][^"']*text-body-sm leading-relaxed text-\[var\(--text-secondary\)\][^"']*["']/g, 'className="text-body leading-relaxed text-[var(--text-secondary)] text-start"']
]);

// 4. SecurityCTASection.tsx
processFile(path.join(SEC_DIR, 'SecurityCTASection.tsx'), [
  [/<h2[^>]*>/g, '<h2 className="mt-10 text-h1 text-start">'],
  [/<p[^>]*className=["'][^"']*text-body[^"']*["'][^>]*>/g, '<p className="text-body leading-relaxed text-[var(--text-secondary)] text-start">']
]);

console.log('✅ Раздел SECURITY полностью унифицирован с форматом PLATFORM!');

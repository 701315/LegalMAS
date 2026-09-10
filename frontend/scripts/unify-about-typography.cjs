const fs = require('fs');
const path = require('path');

const ABOUT_DIR = path.join(__dirname, '../src/marketing/components/about');

function processFile(filePath, replacements) {
  if (!fs.existsSync(filePath)) return;
  let content = fs.readFileSync(filePath, 'utf-8');
  replacements.forEach(([regex, repl]) => {
    content = content.replace(regex, repl);
  });
  fs.writeFileSync(filePath, content, 'utf-8');
}

// 1. AboutPhilosophySection.tsx
processFile(path.join(ABOUT_DIR, 'AboutPhilosophySection.tsx'), [
  [/className=["']text-h2 text-3xl mt-4["']/g, 'className="mt-4 text-h2 font-serif text-[var(--text-primary)] text-start"'],
  [/className=["']text-body-sm leading-relaxed text-\[var\(--text-secondary\)\] mt-6["']/g, 'className="mt-6 text-body leading-relaxed text-[var(--text-secondary)] text-start"']
]);

// 2. AboutPrinciplesSection.tsx
processFile(path.join(ABOUT_DIR, 'AboutPrinciplesSection.tsx'), [
  [/className=["']text-h2 text-3xl mb-16 italic["']/g, 'className="text-h1 text-[var(--text-primary)] text-start mb-12"'],
  [/className=["']text-h3 italic mb-3["']/g, 'className="text-h3 font-serif text-[var(--text-primary)] text-start mb-3"'],
  [/className=["']text-body-sm leading-normal text-\[var\(--text-secondary\)\]["']/g, 'className="text-body leading-relaxed text-[var(--text-secondary)] text-start"']
]);

// 3. AboutTeamSection.tsx
processFile(path.join(ABOUT_DIR, 'AboutTeamSection.tsx'), [
  [/className=["']text-h2 text-\[var\(--text-primary\)\] text-start["']/g, 'className="text-h1 text-[var(--text-primary)] text-start"'],
  [/className=["']mt-8 text-h2 text-\[var\(--text-primary\)\]["']/g, 'className="mt-8 text-h2 font-serif text-[var(--text-primary)] text-start"']
]);

// 4. AboutProcessSection.tsx
processFile(path.join(ABOUT_DIR, 'AboutProcessSection.tsx'), [
  [/className=["']text-h3 italic mb-4 text-white\/90["']/g, 'className="text-h3 font-serif mb-4 !text-white text-start"'],
  [/className=["']text-body-sm leading-relaxed text-white\/50 font-light max-w-\[280px\]["']/g, 'className="text-body leading-relaxed !text-[#D6D0C7] text-start max-w-[320px]"']
]);

console.log('✅ Раздел ABOUT успешно приведён к 100% единому стандарту!');
